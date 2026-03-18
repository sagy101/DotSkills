#!/usr/bin/env bash

set -euo pipefail

usage() {
  local _rc
  _rc="${1:-2}"
  echo "Usage: publish_chain.sh [--workspace-dir <workspace-dir>] [--artifact-version <version>] [--target-project <dir>] [--dry-run] <repo-or-path>..." >&2
  exit "$_rc"
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage 0
fi

WORKSPACE_DIR=""
ARTIFACT_VERSION_VALUE=""
TARGET_PROJECT=""
DRY_RUN=false
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"
REPO_SPECS=()

while [ "$#" -gt 0 ]; do
  case "$1" in
    --workspace-dir)
      [ "$#" -ge 2 ] || usage
      WORKSPACE_DIR="$2"
      shift 2
      ;;
    --artifact-version)
      [ "$#" -ge 2 ] || usage
      ARTIFACT_VERSION_VALUE="$2"
      shift 2
      ;;
    --target-project)
      [ "$#" -ge 2 ] || usage
      TARGET_PROJECT="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --help|-h)
      usage 0
      ;;
    *)
      REPO_SPECS+=("$1")
      shift
      ;;
  esac
done

[ ${#REPO_SPECS[@]} -gt 0 ] || usage

if [ -z "$WORKSPACE_DIR" ]; then
  FIRST_SPEC="${REPO_SPECS[0]}"
  if [ -d "$FIRST_SPEC" ] || [ -f "$FIRST_SPEC" ]; then
    FIRST_REPO_ROOT="$(find_repo_root_for_path "$FIRST_SPEC" || true)"
    [ -n "$FIRST_REPO_ROOT" ] || usage
    WORKSPACE_DIR="$(dirname "$FIRST_REPO_ROOT")"
  else
    usage
  fi
fi

WORKSPACE_DIR="$(cd "$WORKSPACE_DIR" && pwd)"
source "$SCRIPT_DIR/resolve_projects.sh"
trap 'rm -f "$_GRAPH_JSON" "$_ORDERED_FILE"' EXIT
_GRAPH_JSON=$(mktemp)
_ORDERED_FILE=$(mktemp)
build_workspace_graph_json "$SCRIPT_DIR" "$WORKSPACE_DIR" "$GROUP_ID" "$_GRAPH_JSON" "${SERVICES[@]}"

python3 - "$_GRAPH_JSON" "${REPO_SPECS[@]}" > "$_ORDERED_FILE" <<'PY'
import json
import sys
from pathlib import Path

graph = json.loads(Path(sys.argv[1]).read_text())
repo_specs = sys.argv[2:]
repos = graph["repos"]
repo_by_name = {repo["name"]: repo for repo in repos}
repo_by_path = {str(Path(repo["path"]).resolve()): repo for repo in repos}
deps = {repo["name"]: set(repo.get("dependencies", [])) for repo in repos}
publish_order = graph.get("publish_order", [])

def resolve_repo(spec):
    path = Path(spec).resolve()
    if str(path) in repo_by_path:
        return repo_by_path[str(path)]["name"]
    if spec in repo_by_name:
        return spec
    if path.name in repo_by_name:
        return path.name
    raise SystemExit(f"ERROR: Could not resolve repo '{spec}' in workspace graph")

selected = set()
stack = [resolve_repo(spec) for spec in repo_specs]
while stack:
    current = stack.pop()
    if current in selected:
        continue
    selected.add(current)
    stack.extend(sorted(deps.get(current, set())))

for name in publish_order:
    if name in selected:
        print(name)
PY

ORDERED_REPOS=()
while IFS= read -r _ordered_repo; do
  [ -n "$_ordered_repo" ] && ORDERED_REPOS+=("$_ordered_repo")
done < "$_ORDERED_FILE"

[ ${#ORDERED_REPOS[@]} -gt 0 ] || { echo "ERROR: No repos selected for publish" >&2; exit 2; }

# ── Collect build files from ALL repos in the publish chain ──────────────────
# Version lookup must search the entire chain, not just the target.
# E.g., service-a -> platform-commons -> shared-models: shared-models' version
# is declared in platform-commons' build files, not service-a's.
_ALL_CHAIN_BUILD_FILES=()
if [ -n "$TARGET_PROJECT" ]; then
  TARGET_PROJECT="$(cd "$TARGET_PROJECT" && pwd)"
fi
# Collect from target project + all repos in the ordered chain
_chain_dirs=()
[ -n "$TARGET_PROJECT" ] && _chain_dirs+=("$TARGET_PROJECT")
for _repo_name in "${ORDERED_REPOS[@]}"; do
  _rpath="$(service_dir_for_repo_name "$_repo_name" "${SERVICES[@]}" || true)"
  [ -n "$_rpath" ] && _chain_dirs+=("$_rpath")
done
for _cdir in "${_chain_dirs[@]}"; do
  while IFS= read -r _f; do
    [ -f "$_f" ] && _ALL_CHAIN_BUILD_FILES+=("$_f")
  done <<< "$(collect_build_files "$_cdir")"
done

_get_repo_version() {
  local _repo_name="$1"
  local _repo_path="$2"

  # If explicit --artifact-version, use it for all
  if [ -n "$ARTIFACT_VERSION_VALUE" ]; then
    echo "$ARTIFACT_VERSION_VALUE"
    return 0
  fi

  # Search all chain build files for the version any repo needs for this repo's artifacts
  if [ ${#_ALL_CHAIN_BUILD_FILES[@]} -gt 0 ]; then
    local _art_names _art_name _ver
    _art_names="$(get_all_artifact_names "$_repo_path")"
    for _art_name in $_art_names; do
      _ver="$(lookup_artifact_version "$_art_name" "${_ALL_CHAIN_BUILD_FILES[@]}" || true)"
      if [ -n "$_ver" ]; then
        echo "$_ver"
        return 0
      fi
    done
  fi

  # Fallback: use the repo's own version from build.sbt
  local _own_ver
  _own_ver="$(extract_project_version "$_repo_path/build.sbt")"
  if [ -n "$_own_ver" ]; then
    echo "$_own_ver"
    return 0
  fi

  return 1
}

echo "=== Publish Chain ==="
echo "Workspace: $WORKSPACE_DIR"
if [ -n "$ARTIFACT_VERSION_VALUE" ]; then
  echo "Artifact version (global): $ARTIFACT_VERSION_VALUE"
elif [ -n "$TARGET_PROJECT" ]; then
  echo "Target project: $TARGET_PROJECT (auto-detecting per-repo versions)"
fi
echo "Dry run: $DRY_RUN"
echo
for index in "${!ORDERED_REPOS[@]}"; do
  repo_name="${ORDERED_REPOS[$index]}"
  repo_path="$(service_dir_for_repo_name "$repo_name" "${SERVICES[@]}" || true)"
  [ -n "$repo_path" ] || continue
  _ver="$(_get_repo_version "$repo_name" "$repo_path" || echo "<unknown>")"
  echo "  $((index + 1)). $repo_name @ $_ver -> $repo_path"
done

echo
for repo_name in "${ORDERED_REPOS[@]}"; do
  repo_path="$(service_dir_for_repo_name "$repo_name" "${SERVICES[@]}" || true)"
  [ -n "$repo_path" ] || continue
  _ver="$(_get_repo_version "$repo_name" "$repo_path" || true)"

  # Clear stale cached artifacts before publishing to avoid Ivy "Attempting to overwrite" issues.
  # Non-SNAPSHOT versions are sticky in the cache; we must remove them first.
  if [ -n "$_ver" ] && [ -n "$GROUP_ID" ] && [ "$DRY_RUN" = false ]; then
    _art_names="$(get_all_artifact_names "$repo_path")"
    for _art_name in $_art_names; do
      _scala_sfx="$(scala_binary_suffix "$(extract_scala_version "$repo_path")")"
      _art_with_sfx="${_art_name}${_scala_sfx}"
      _local_dir="$SBT_BUILD_CACHE_ROOT/local/$GROUP_ID/$_art_with_sfx/$_ver"
      _cache_dir="$SBT_BUILD_CACHE_ROOT/cache/$GROUP_ID/$_art_with_sfx"
      if [ -d "$_local_dir" ]; then
        rm -rf "$_local_dir"
      fi
      if [ -d "$_cache_dir" ]; then
        rm -rf "$_cache_dir"
      fi
    done
  fi

  CMD=(bash "$SCRIPT_DIR/run_sbt_capture.sh" "$repo_path" --workspace-dir "$WORKSPACE_DIR" --label publish)
  if [ -n "$_ver" ]; then
    CMD+=(--artifact-version "$_ver")
  fi
  CMD+=(--tail 40 -- publishLocal)
  if [ "$DRY_RUN" = true ]; then
    printf 'DRY-RUN:'
    printf ' %q' "${CMD[@]}"
    echo
  else
    "${CMD[@]}"
  fi
done
