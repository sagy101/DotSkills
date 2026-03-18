#!/usr/bin/env bash
# check_workspace_deps.sh — Pre-check that workspace dependencies are in the isolated cache
#
# Usage: check_workspace_deps.sh <project-dir> [--workspace-dir <dir>] [--strict]
#
# Two-pass check:
#   Pass 1 (ProjectRef): Scans build.sbt for ProjectRef entries, identifies the
#     published artifact version, and verifies it exists in the isolated cache.
#   Pass 2 (libraryDependencies): Scans build.sbt and project/*.scala for
#     artifacts whose name matches a workspace repo. If the producing repo is
#     on a feature branch but no local publish exists at the required version,
#     flags it as STALE (likely outdated artifact).
#
# Exit codes:
#   0 — all workspace deps found (or no workspace deps detected)
#   1 — one or more workspace deps missing or stale
#   2 — usage error

set -uo pipefail

PROJECT_DIR="${1:?Usage: check_workspace_deps.sh <project-dir> [--workspace-dir <dir>] [--strict]}"
shift

WORKSPACE_DIR=""
STRICT_STALE=false
while [ "$#" -gt 0 ]; do
  case "$1" in
    --workspace-dir)
      [ "$#" -ge 2 ] || { echo "Usage: check_workspace_deps.sh <project-dir> [--workspace-dir <dir>] [--strict]" >&2; exit 2; }
      WORKSPACE_DIR="$2"
      shift 2
      ;;
    --strict)
      STRICT_STALE=true
      shift
      ;;
    *) shift ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"
if [ ! -f "$PROJECT_DIR/build.sbt" ]; then
  echo "ERROR: No build.sbt found in $PROJECT_DIR" >&2
  exit 2
fi

WORKSPACE_DIR="$(resolve_workspace_dir "$WORKSPACE_DIR" "$PROJECT_DIR")"
source "$SCRIPT_DIR/resolve_projects.sh"

if [ -z "$GROUP_ID" ]; then
  exit 0
fi

# Detect Scala binary version
SCALA_FULL="$(extract_scala_version "$PROJECT_DIR")"
SCALA_SUFFIX="$(scala_binary_suffix "$SCALA_FULL")"

# Collect build files for version lookups
BUILD_FILES_STR="$(collect_build_files "$PROJECT_DIR")"
BUILD_FILES=()
while IFS= read -r _bf; do
  [ -f "$_bf" ] && BUILD_FILES+=("$_bf")
done <<< "$BUILD_FILES_STR"

# Find ProjectRef entries (Pass 1 — dev mode)
PROJ_REFS="$(extract_project_refs "$PROJECT_DIR/build.sbt")"

MISSING_COUNT=0

while IFS= read -r ref_line; do
  [ -z "$ref_line" ] && continue

  REF_PATH=$(echo "$ref_line" | sed 's/.*file("\([^"]*\)".*/\1/')
  REF_NAME=$(echo "$ref_line" | sed 's/.*,[ ]*"\([^"]*\)".*/\1/')

  REF_ABS=""
  if [[ "$REF_PATH" == /* ]]; then
    REF_ABS="$REF_PATH"
  else
    REF_ABS="$(cd "$PROJECT_DIR" && cd "$REF_PATH" 2>/dev/null && pwd || true)"
  fi

  if [ -z "$REF_ABS" ] || [ ! -f "$REF_ABS/build.sbt" ]; then
    continue
  fi

  ARTIFACT_NAME="$(get_primary_artifact_name "$REF_ABS")"
  [ -z "$ARTIFACT_NAME" ] && ARTIFACT_NAME="$REF_NAME"

  REQUIRED_VERSION="$(lookup_artifact_version "$ARTIFACT_NAME" "${BUILD_FILES[@]}" || true)"

  if [ -z "$REQUIRED_VERSION" ]; then
    continue
  fi

  ARTIFACT_WITH_SUFFIX="${ARTIFACT_NAME}${SCALA_SUFFIX}"
  IVY_FILE="$SBT_BUILD_CACHE_ROOT/local/$GROUP_ID/$ARTIFACT_WITH_SUFFIX/$REQUIRED_VERSION/ivys/ivy.xml"

  if [ ! -f "$IVY_FILE" ]; then
    if [ "$MISSING_COUNT" -eq 0 ]; then
      echo "=== Missing Workspace Dependencies ==="
      echo ""
    fi
    MISSING_COUNT=$((MISSING_COUNT + 1))
    echo "  MISSING: $ARTIFACT_WITH_SUFFIX @ $REQUIRED_VERSION"
    echo "    Not in isolated cache: $IVY_FILE"
    echo "    Fix: bash $SCRIPT_DIR/run_sbt_capture.sh $REF_ABS --artifact-version $REQUIRED_VERSION --tail 10 -- publishLocal"
    echo ""
  fi
done <<< "$PROJ_REFS"

# ─── Pass 2: libraryDependencies cross-check against workspace repos ─────────

STALE_COUNT=0

_get_branch() {
  local _dir="$1"
  [ -d "$_dir/.git" ] && git -C "$_dir" branch --show-current 2>/dev/null || echo ""
}

if [ -n "$GROUP_ID" ]; then
  for _ws_repo_dir in "$WORKSPACE_DIR"/*/; do
    [ -f "$_ws_repo_dir/build.sbt" ] || continue
    _ws_repo_dir="$(cd "$_ws_repo_dir" && pwd)"
    [ "$_ws_repo_dir" = "$PROJECT_DIR" ] && continue

    _ws_repo_branch="$(_get_branch "$_ws_repo_dir")"
    [ -z "$_ws_repo_branch" ] && continue
    [ "$_ws_repo_branch" = "master" ] || [ "$_ws_repo_branch" = "main" ] && continue

    # Collect all artifact names from this workspace repo
    _ws_artifacts_str="$(get_all_artifact_names "$_ws_repo_dir")"
    [ -z "$_ws_artifacts_str" ] && continue
    _ws_artifacts=()
    while IFS= read -r _name; do
      [ -n "$_name" ] && _ws_artifacts+=("$_name")
    done <<< "$_ws_artifacts_str"
    [ ${#_ws_artifacts[@]} -eq 0 ] && continue

    for _art in "${_ws_artifacts[@]}"; do
      _dep_version="$(lookup_artifact_version "$_art" "${BUILD_FILES[@]}" || true)"
      [ -z "$_dep_version" ] && continue

      _art_with_suffix="${_art}${SCALA_SUFFIX}"
      _ivy_file="$SBT_BUILD_CACHE_ROOT/local/$GROUP_ID/$_art_with_suffix/$_dep_version/ivys/ivy.xml"

      if [ ! -f "$_ivy_file" ]; then
        if [ "$STALE_COUNT" -eq 0 ] && [ "$MISSING_COUNT" -eq 0 ]; then
          echo "=== Stale Workspace Dependencies ==="
          echo ""
        elif [ "$STALE_COUNT" -eq 0 ]; then
          echo ""
        fi
        STALE_COUNT=$((STALE_COUNT + 1))
        echo "  STALE: $_art_with_suffix @ $_dep_version"
        echo "    Upstream repo $(basename "$_ws_repo_dir") is on branch: $_ws_repo_branch"
        echo "    No local publish at: $_ivy_file"
        echo "    The resolved artifact may be outdated (risk: NoSuchMethodError, missing classes)"
        echo "    Fix: bash $SCRIPT_DIR/run_sbt_capture.sh $_ws_repo_dir --tail 10 -- 'set every version := \"$_dep_version\"' publishLocal"
        echo ""
      fi
    done
  done
fi

if [ "$MISSING_COUNT" -gt 0 ]; then
  echo "  $MISSING_COUNT workspace dependency(ies) missing from isolated cache."
  echo "  Publish them before running the build."
  echo ""
  exit 1
fi
if [ "$STALE_COUNT" -gt 0 ]; then
  echo "  WARN: $STALE_COUNT workspace dependency(ies) likely stale (upstream on feature branch, no local publish)."
  echo "  The build may still succeed if upstream API hasn't changed."
  echo "  Use --strict to treat stale deps as errors."
  echo ""
  if [ "$STRICT_STALE" = true ]; then
    exit 1
  fi
fi

exit 0
