#!/usr/bin/env bash

set -euo pipefail

usage() {
  local _rc
  _rc="${1:-2}"
  echo "Usage: refresh_downstream.sh <project-dir> [--workspace-dir <workspace-dir>] [--artifact <artifact-name>] [--group-id <group-id>] [--version <version>] [--clean-target] [--rebuild-arg <sbt-arg>] [--dry-run]" >&2
  exit "$_rc"
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage 0
fi

[ "$#" -ge 1 ] || usage
PROJECT_DIR="$1"
shift
WORKSPACE_DIR=""
ARTIFACT_NAME=""
GROUP_ID_OVERRIDE=""
VERSION_VALUE=""
CLEAN_TARGET=false
DRY_RUN=false
REBUILD_ARGS=()
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --workspace-dir)
      [ "$#" -ge 2 ] || usage
      WORKSPACE_DIR="$2"
      shift 2
      ;;
    --artifact)
      [ "$#" -ge 2 ] || usage
      ARTIFACT_NAME="$2"
      shift 2
      ;;
    --group-id)
      [ "$#" -ge 2 ] || usage
      GROUP_ID_OVERRIDE="$2"
      shift 2
      ;;
    --version)
      [ "$#" -ge 2 ] || usage
      VERSION_VALUE="$2"
      shift 2
      ;;
    --clean-target)
      CLEAN_TARGET=true
      shift
      ;;
    --rebuild-arg)
      [ "$#" -ge 2 ] || usage
      REBUILD_ARGS+=("$2")
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    *)
      usage
      ;;
  esac
done

PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"
[ -f "$PROJECT_DIR/build.sbt" ] || { echo "ERROR: No build.sbt found in $PROJECT_DIR" >&2; exit 2; }

if [ -z "$WORKSPACE_DIR" ]; then
  WORKSPACE_DIR="$(dirname "$PROJECT_DIR")"
fi
WORKSPACE_DIR="$(cd "$WORKSPACE_DIR" && pwd)"
source "$SCRIPT_DIR/resolve_projects.sh"

if [ -z "$GROUP_ID_OVERRIDE" ]; then
  GROUP_ID_OVERRIDE="$GROUP_ID"
fi

if [ -z "$ARTIFACT_NAME" ]; then
  ARTIFACT_NAME="$(infer_artifact_name_from_repo "$PROJECT_DIR")"
fi

[ -n "$ARTIFACT_NAME" ] || { echo "ERROR: Could not determine artifact name. Pass --artifact explicitly." >&2; exit 2; }

ACTIONS=()
if [ -n "$GROUP_ID_OVERRIDE" ]; then
  ACTIONS+=("rm -rf $(isolated_cache_artifact_dir "$GROUP_ID_OVERRIDE" "$ARTIFACT_NAME")")
  ACTIONS+=("rm -rf $(isolated_local_artifact_dir "$GROUP_ID_OVERRIDE" "$ARTIFACT_NAME")")
fi
if [ -n "$VERSION_VALUE" ]; then
  ACTIONS+=("find $(coursier_cache_root) -path '*/$ARTIFACT_NAME/*/$VERSION_VALUE' -type d -prune -exec rm -rf {} +")
else
  ACTIONS+=("find $(coursier_cache_root) -path '*/$ARTIFACT_NAME/*' -type d -prune -exec rm -rf {} +")
fi
if [ "$CLEAN_TARGET" = true ]; then
  ACTIONS+=("rm -rf $PROJECT_DIR/target")
fi

REBUILD_CMD=()
if [ ${#REBUILD_ARGS[@]} -gt 0 ]; then
  REBUILD_CMD=(bash "$SCRIPT_DIR/run_sbt_capture.sh" "$PROJECT_DIR" --workspace-dir "$WORKSPACE_DIR" --label rebuild --tail 60 --)
  for arg in "${REBUILD_ARGS[@]}"; do
    REBUILD_CMD+=("$arg")
  done
fi

echo "=== Downstream Refresh ==="
echo "Project: $PROJECT_DIR"
echo "Artifact: $ARTIFACT_NAME"
if [ -n "$GROUP_ID_OVERRIDE" ]; then
  echo "Group: $GROUP_ID_OVERRIDE"
fi
if [ -n "$VERSION_VALUE" ]; then
  echo "Version: $VERSION_VALUE"
fi
echo "Dry run: $DRY_RUN"
echo
for action in "${ACTIONS[@]}"; do
  echo "  $action"
done
if [ ${#REBUILD_CMD[@]} -gt 0 ]; then
  printf '  '
  printf '%q ' "${REBUILD_CMD[@]}"
  echo
fi

echo
if [ "$DRY_RUN" = false ]; then
  for action in "${ACTIONS[@]}"; do
    bash -lc "$action"
  done
  if [ ${#REBUILD_CMD[@]} -gt 0 ]; then
    "${REBUILD_CMD[@]}"
  fi
fi
