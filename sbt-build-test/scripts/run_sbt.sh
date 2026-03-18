#!/usr/bin/env bash
# run_sbt.sh — Shared wrapper for SBT commands used by this skill
#
# Usage:
#   run_sbt.sh <project-dir> [--workspace-dir <workspace-dir>] [--artifact-version <version>] [--sbt-env <value>] -- <sbt-arg>...
#
# Examples:
#   run_sbt.sh /path/to/service -- compile
#   run_sbt.sh /path/to/multi-project-root -- "core / test"
#   run_sbt.sh /path/to/library -- --error publishLocal

set -euo pipefail

usage() {
  echo "Usage: run_sbt.sh <project-dir> [--workspace-dir <workspace-dir>] [--artifact-version <version>] [--sbt-env <value>] -- <sbt-arg>..." >&2
  exit 2
}

if [ "$#" -lt 3 ]; then
  usage
fi

PROJECT_DIR="$1"
shift

WORKSPACE_DIR=""
ARTIFACT_VERSION_VALUE="${ARTIFACT_VERSION:-}"
SBT_ENV_VALUE="${SBT_ENV:-}"
FORCE_BATCH=false
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

source "$SCRIPT_DIR/common.sh"

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
    --sbt-env)
      [ "$#" -ge 2 ] || usage
      SBT_ENV_VALUE="$2"
      shift 2
      ;;
    --batch)
      FORCE_BATCH=true
      shift
      ;;
    --)
      shift
      break
      ;;
    *)
      usage
      ;;
  esac
done

[ "$#" -gt 0 ] || usage

PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"
if [ ! -f "$PROJECT_DIR/build.sbt" ]; then
  echo "ERROR: No build.sbt found in $PROJECT_DIR" >&2
  exit 2
fi

if [ -z "$WORKSPACE_DIR" ]; then
  WORKSPACE_DIR="$(dirname "$PROJECT_DIR")"
fi
WORKSPACE_DIR="$(cd "$WORKSPACE_DIR" && pwd)"

source "$SCRIPT_DIR/resolve_projects.sh"
ensure_sbt_skill_dirs

JAVA_HOME_RESOLVED="$(resolve_java_home_for_version "$JAVA_VERSION")"
if [ -z "$JAVA_HOME_RESOLVED" ]; then
  echo "ERROR: Java $JAVA_VERSION not found. Update .sbt-workspace.conf or install a matching JDK." >&2
  exit 1
fi

SBT_HEAP_ARGS=()
if [ -z "${SBT_OPTS:-}" ]; then
  SBT_HEAP_ARGS=(-J-Xmx4g)
fi

NEEDS_TEST_LOCK=false
for sbt_arg in "$@"; do
  case "$sbt_arg" in
    *testOnly*|*" / test"*|test|*"/test"*|coverage)
      NEEDS_TEST_LOCK=true
      break
      ;;
  esac
done

LOCK_FILE=""
cleanup() {
  if [ -n "$LOCK_FILE" ] && [ -f "$LOCK_FILE" ]; then
    rm -f "$LOCK_FILE"
  fi
}
trap cleanup EXIT

if [ "$NEEDS_TEST_LOCK" = true ]; then
  LOCK_FILE="$(test_activity_lock_file "$PROJECT_DIR")"
  if [ -f "$LOCK_FILE" ]; then
    # Check if the lock holder is still alive
    _LOCK_PID=$(grep -oE '^pid=[0-9]+' "$LOCK_FILE" 2>/dev/null | cut -d= -f2 || true)
    _LOCK_STALE=false
    if [ -n "$_LOCK_PID" ]; then
      if ! kill -0 "$_LOCK_PID" 2>/dev/null; then
        _LOCK_STALE=true
      fi
    fi
    # Also treat locks older than 2 hours as stale regardless of PID
    if [ "$_LOCK_STALE" = false ] && [ -f "$LOCK_FILE" ]; then
      _LOCK_AGE_LIMIT=$((2 * 60 * 60))
      _LOCK_MTIME=$(stat -f '%m' "$LOCK_FILE" 2>/dev/null || stat -c '%Y' "$LOCK_FILE" 2>/dev/null || echo 0)
      _NOW=$(date '+%s')
      if [ $((_NOW - _LOCK_MTIME)) -ge "$_LOCK_AGE_LIMIT" ]; then
        _LOCK_STALE=true
      fi
    fi
    if [ "$_LOCK_STALE" = true ]; then
      echo "WARNING: Stale lock file detected (PID ${_LOCK_PID:-unknown} is no longer running). Removing." >&2
      rm -f "$LOCK_FILE"
    else
      echo "ERROR: Another test-oriented sbt command is already active for $PROJECT_DIR" >&2
      echo "Hint: wait for the active sbt test run to finish before starting another test or parsing reports for this repo." >&2
      exit 2
    fi
  fi
  {
    echo "pid=$$"
    echo "project=$PROJECT_DIR"
    echo "started_at=$(date '+%Y-%m-%d %H:%M:%S')"
    printf 'command='
    printf '%s ' "$@"
    echo
  } > "$LOCK_FILE"
fi

SBT_CMD=(sbt "${SBT_HEAP_ARGS[@]}" "-Dsbt.ivy.home=$SBT_BUILD_CACHE_ROOT")
# Use --batch for test commands to force a fresh SBT process (avoids stale incremental state from SBT server)
if [ "$FORCE_BATCH" = true ] || [ "$NEEDS_TEST_LOCK" = true ]; then
  SBT_CMD+=(--batch)
fi
if [ -n "$SBT_ENV_VALUE" ]; then
  SBT_CMD+=("-Dsbt_env=$SBT_ENV_VALUE")
fi
for sbt_arg in "$@"; do
  SBT_CMD+=("$sbt_arg")
done

cd "$PROJECT_DIR"
if [ -n "$ARTIFACT_VERSION_VALUE" ]; then
  export ARTIFACT_VERSION="$ARTIFACT_VERSION_VALUE"
fi
if env JAVA_HOME="$JAVA_HOME_RESOLVED" "${SBT_CMD[@]}"; then
  SBT_RC=0
else
  SBT_RC=$?
fi
exit "$SBT_RC"
