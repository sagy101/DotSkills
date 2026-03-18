#!/usr/bin/env bash
# sbt_status.sh — Single command for dependency discovery, workspace state, and diagnostics
#
# Modes (mutually exclusive):
#   Default:          Run discover_deps.sh on the target project
#   --workspace:      Run full preflight_check.sh + discover_workspace.sh
#   --plan-change:    Run plan_change.sh for (changed-repo -> target project)
#   --verify:         Run verify_local_resolution.sh for an artifact
#
# Usage:
#   sbt_status.sh <project-dir> [options]
#
# Examples:
#   sbt_status.sh /path/to/service
#   sbt_status.sh /path/to/service --workspace
#   sbt_status.sh /path/to/service --plan-change /path/to/changed-repo
#   sbt_status.sh /path/to/service --verify artifact-name

set -euo pipefail

usage() {
  echo "Usage: sbt_status.sh <project-dir> [options]" >&2
  echo "" >&2
  echo "Modes (pick one, default is single-repo discovery):" >&2
  echo "  --workspace                  Full workspace preflight + dependency graph" >&2
  echo "  --plan-change <changed-repo> Plan a cross-repo change impact" >&2
  echo "  --verify <artifact-name>     Verify artifact resolution source" >&2
  echo "" >&2
  echo "Options:" >&2
  echo "  --workspace-dir <dir>        Override workspace directory" >&2
  echo "  --json                       JSON output (workspace and plan-change modes)" >&2
  exit 2
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage
fi

[ "$#" -ge 1 ] || usage

PROJECT_DIR="$1"
shift

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"
WORKSPACE_DIR=""
MODE="discover"
CHANGED_REPO=""
VERIFY_ARTIFACT=""
JSON_FLAG=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --workspace-dir)
      [ "$#" -ge 2 ] || usage
      WORKSPACE_DIR="$2"
      shift 2
      ;;
    --workspace)
      MODE="workspace"
      shift
      ;;
    --plan-change)
      [ "$#" -ge 2 ] || usage
      MODE="plan-change"
      CHANGED_REPO="$2"
      shift 2
      ;;
    --verify)
      [ "$#" -ge 2 ] || usage
      MODE="verify"
      VERIFY_ARTIFACT="$2"
      shift 2
      ;;
    --json)
      JSON_FLAG="--json"
      shift
      ;;
    *)
      usage
      ;;
  esac
done

PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"
if [ ! -f "$PROJECT_DIR/build.sbt" ]; then
  echo "ERROR: No build.sbt found in $PROJECT_DIR" >&2
  exit 2
fi

WORKSPACE_DIR="$(resolve_workspace_dir "$WORKSPACE_DIR" "$PROJECT_DIR")"

case "$MODE" in
  discover)
    exec bash "$SCRIPT_DIR/discover_deps.sh" "$PROJECT_DIR"
    ;;
  workspace)
    bash "$SCRIPT_DIR/preflight_check.sh" "$WORKSPACE_DIR"
    echo ""
    WORKSPACE_ARGS=("$WORKSPACE_DIR")
    [ -n "$JSON_FLAG" ] && WORKSPACE_ARGS+=("$JSON_FLAG")
    exec bash "$SCRIPT_DIR/discover_workspace.sh" "${WORKSPACE_ARGS[@]}"
    ;;
  plan-change)
    PLAN_ARGS=("$CHANGED_REPO" "$PROJECT_DIR" --workspace-dir "$WORKSPACE_DIR")
    [ -n "$JSON_FLAG" ] && PLAN_ARGS+=("$JSON_FLAG")
    exec bash "$SCRIPT_DIR/plan_change.sh" "${PLAN_ARGS[@]}"
    ;;
  verify)
    exec bash "$SCRIPT_DIR/verify_local_resolution.sh" "$PROJECT_DIR" "$VERIFY_ARTIFACT" --workspace-dir "$WORKSPACE_DIR"
    ;;
esac
