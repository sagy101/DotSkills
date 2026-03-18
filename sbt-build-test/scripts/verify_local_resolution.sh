#!/usr/bin/env bash

set -euo pipefail

usage() {
  local _rc
  _rc="${1:-2}"
  echo "Usage: verify_local_resolution.sh <project-dir> <artifact-name> [--workspace-dir <workspace-dir>] [--group-id <group-id>] [--tail <lines>]" >&2
  exit "$_rc"
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage 0
fi

[ "$#" -ge 2 ] || usage
PROJECT_DIR="$1"
ARTIFACT_NAME="$2"
shift 2
WORKSPACE_DIR=""
GROUP_ID_OVERRIDE=""
TAIL_LINES=40
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --workspace-dir)
      [ "$#" -ge 2 ] || usage
      WORKSPACE_DIR="$2"
      shift 2
      ;;
    --group-id)
      [ "$#" -ge 2 ] || usage
      GROUP_ID_OVERRIDE="$2"
      shift 2
      ;;
    --tail)
      [ "$#" -ge 2 ] || usage
      TAIL_LINES="$2"
      shift 2
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

LOG_FILE="$(skill_log_file "$PROJECT_DIR" "verify-resolution")"
bash "$SCRIPT_DIR/run_sbt_capture.sh" "$PROJECT_DIR" --workspace-dir "$WORKSPACE_DIR" --label verify-resolution --log-file "$LOG_FILE" --tail "$TAIL_LINES" -- "show externalDependencyClasspath" >/dev/null

MATCHES=$(grep -F "$ARTIFACT_NAME" "$LOG_FILE" || true)
COURIER_ROOT="$(coursier_cache_root)"

echo "=== Local Resolution Verification ==="
echo "Project: $PROJECT_DIR"
echo "Artifact: $ARTIFACT_NAME"
if [ -n "$GROUP_ID_OVERRIDE" ]; then
  echo "Group: $GROUP_ID_OVERRIDE"
fi
echo "Log: $LOG_FILE"
echo

if [ -n "$MATCHES" ]; then
  echo "--- Classpath Matches ---"
  echo "$MATCHES" | sed 's/^/  /'
else
  echo "--- Classpath Matches ---"
  echo "  (no classpath lines matched $ARTIFACT_NAME)"
fi

echo
echo "--- Resolution Source Assessment ---"
SOURCE_COUNT=0
if [ -n "$MATCHES" ]; then
  if echo "$MATCHES" | grep -Fq "$SBT_BUILD_CACHE_ROOT/local/"; then
    echo "  - isolated local publish"
    SOURCE_COUNT=$((SOURCE_COUNT + 1))
  fi
  if echo "$MATCHES" | grep -Fq "$HOME/.ivy2/local/"; then
    echo "  - default Ivy local"
    SOURCE_COUNT=$((SOURCE_COUNT + 1))
  fi
  if echo "$MATCHES" | grep -Fq "$COURIER_ROOT"; then
    echo "  - Coursier cache (remote or previously cached resolution)"
    SOURCE_COUNT=$((SOURCE_COUNT + 1))
  fi
  if echo "$MATCHES" | grep -Fq "$SBT_BUILD_CACHE_ROOT/cache/"; then
    echo "  - isolated Ivy cache"
    SOURCE_COUNT=$((SOURCE_COUNT + 1))
  fi
fi
if [ "$SOURCE_COUNT" -eq 0 ]; then
  echo "  (could not classify a source from the current classpath output)"
fi

echo
echo "--- Local Publish Candidates ---"
LOCAL_PUBLISH_DIR=""
if [ -n "$GROUP_ID_OVERRIDE" ]; then
  LOCAL_PUBLISH_DIR="$(isolated_local_artifact_dir "$GROUP_ID_OVERRIDE" "$ARTIFACT_NAME" || true)"
fi
if [ -n "$LOCAL_PUBLISH_DIR" ] && [ -d "$LOCAL_PUBLISH_DIR" ]; then
  find "$LOCAL_PUBLISH_DIR" -mindepth 1 -maxdepth 2 -type d | sed 's/^/  /'
else
  echo "  (no isolated local publish found for $ARTIFACT_NAME)"
fi

IVY_LOCAL_DIR=""
if [ -n "$GROUP_ID_OVERRIDE" ]; then
  IVY_LOCAL_DIR="$(ivy_local_group_dir "$GROUP_ID_OVERRIDE" || true)"
  echo
  echo "--- Default Ivy Local Candidates ---"
  if [ -n "$IVY_LOCAL_DIR" ] && [ -d "$IVY_LOCAL_DIR/$ARTIFACT_NAME" ]; then
    find "$IVY_LOCAL_DIR/$ARTIFACT_NAME" -mindepth 1 -maxdepth 2 -type d | sed 's/^/  /'
  else
    echo "  (no default Ivy local publish found for $ARTIFACT_NAME)"
  fi
fi

echo
echo "--- Guidance ---"
if [ -n "$LOCAL_PUBLISH_DIR" ] && [ -d "$LOCAL_PUBLISH_DIR" ] && ! echo "$MATCHES" | grep -Fq "$SBT_BUILD_CACHE_ROOT/local/"; then
  echo "  Local publish exists but is not visible in the current classpath output. A downstream cache refresh may still be required."
elif [ -n "$IVY_LOCAL_DIR" ] && [ -d "$IVY_LOCAL_DIR/$ARTIFACT_NAME" ] && echo "$MATCHES" | grep -Fq "$HOME/.ivy2/local/"; then
  echo "  Default Ivy local appears to be winning resolution. Clean ~/.ivy2/local entries if you want isolated-cache resolution only."
elif echo "$MATCHES" | grep -Fq "$COURIER_ROOT"; then
  echo "  Resolution currently appears to come from Coursier cache. Use refresh_downstream.sh if you expected a freshly published local artifact."
else
  echo "  No additional action suggested from current evidence."
fi
