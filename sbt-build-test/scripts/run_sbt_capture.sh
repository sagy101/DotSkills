#!/usr/bin/env bash

set -euo pipefail

usage() {
  local _rc
  _rc="${1:-2}"
  echo "Usage: run_sbt_capture.sh <project-dir> [--workspace-dir <workspace-dir>] [--artifact-version <version>] [--sbt-env <value>] [--label <label>] [--log-file <path>] [--tail <lines>] -- <sbt-arg>..." >&2
  exit "$_rc"
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage 0
fi

if [ "$#" -lt 3 ]; then
  usage
fi

PROJECT_DIR="$1"
shift

WORKSPACE_DIR=""
ARTIFACT_VERSION_VALUE=""
SBT_ENV_VALUE=""
LOG_LABEL="sbt"
LOG_FILE=""
TAIL_LINES=0
AUTO_PUBLISH_DEPS=false
FORCE_BATCH=false
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

_START_TIME=$(date '+%s')

while [ "$#" -gt 0 ]; do
  case "$1" in
    --batch)
      FORCE_BATCH=true
      shift
      ;;
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
    --label)
      [ "$#" -ge 2 ] || usage
      LOG_LABEL="$2"
      shift 2
      ;;
    --log-file)
      [ "$#" -ge 2 ] || usage
      LOG_FILE="$2"
      shift 2
      ;;
    --tail)
      [ "$#" -ge 2 ] || usage
      TAIL_LINES="$2"
      shift 2
      ;;
    --auto-publish-deps)
      AUTO_PUBLISH_DEPS=true
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
ensure_sbt_skill_dirs

if [ -z "$LOG_FILE" ]; then
  LOG_FILE="$(skill_log_file "$PROJECT_DIR" "$LOG_LABEL")"
fi
mkdir -p "$(dirname "$LOG_FILE")"

# ── rootPaths conflict detection ──────────────────────────────────────────────
# When dev mode uses ProjectRef to an external repo AND the project has
# rootPaths/remote-cache configured, the external repo's target/classes path
# can't be mapped. Detect this and auto-fallback to non-dev mode.
if [ -n "$SBT_ENV_VALUE" ]; then
  _HAS_ROOT_PATHS=false
  if grep -qE 'rootPaths|bspEnabled|remoteCache' "$PROJECT_DIR/build.sbt" "$PROJECT_DIR"/project/*.scala 2>/dev/null; then
    _HAS_ROOT_PATHS=true
  fi
  _HAS_EXTERNAL_PROJREF=false
  if grep -qE 'ProjectRef\(file\("\.\./' "$PROJECT_DIR/build.sbt" 2>/dev/null; then
    _HAS_EXTERNAL_PROJREF=true
  fi
  if [ "$_HAS_ROOT_PATHS" = true ] && [ "$_HAS_EXTERNAL_PROJREF" = true ]; then
    echo "=== rootPaths Conflict Detected ==="
    echo "  Project has rootPaths/remote-cache AND external ProjectRef entries."
    echo "  Dev mode (sbt_env=$SBT_ENV_VALUE) would cause 'cannot be mapped' errors."
    echo "  Auto-falling back to non-dev mode (published artifacts)."
    echo ""
    SBT_ENV_VALUE=""
  fi
fi

RUN_CMD=(bash "$SCRIPT_DIR/run_sbt.sh" "$PROJECT_DIR")
if [ -n "$WORKSPACE_DIR" ]; then
  RUN_CMD+=(--workspace-dir "$WORKSPACE_DIR")
fi
if [ -n "$ARTIFACT_VERSION_VALUE" ]; then
  RUN_CMD+=(--artifact-version "$ARTIFACT_VERSION_VALUE")
fi
if [ -n "$SBT_ENV_VALUE" ]; then
  RUN_CMD+=(--sbt-env "$SBT_ENV_VALUE")
fi
if [ "$FORCE_BATCH" = true ]; then
  RUN_CMD+=(--batch)
fi
RUN_CMD+=(--)
for arg in "$@"; do
  RUN_CMD+=("$arg")
done

# ── Pre-check: verify workspace dependencies are in the isolated cache ────────
_DEP_CHECK_WORKSPACE_ARG=""
if [ -n "$WORKSPACE_DIR" ]; then
  _DEP_CHECK_WORKSPACE_ARG="--workspace-dir $WORKSPACE_DIR"
fi

_DEP_CHECK_OUTPUT=""
_DEP_CHECK_RC=0
_DEP_CHECK_OUTPUT=$(bash "$SCRIPT_DIR/check_workspace_deps.sh" "$PROJECT_DIR" $_DEP_CHECK_WORKSPACE_ARG 2>&1) || _DEP_CHECK_RC=$?

if [ "$_DEP_CHECK_RC" -ne 0 ]; then
  if [ "$AUTO_PUBLISH_DEPS" = true ]; then
    echo "=== Auto-Publishing Missing Dependencies ==="
    # Extract publishLocal fix commands from check output and run them
    _FIX_CMDS=$(echo "$_DEP_CHECK_OUTPUT" | grep -oE 'Fix: bash .* publishLocal' | sed 's/^Fix: //')
    if [ -n "$_FIX_CMDS" ]; then
      while IFS= read -r _fix_cmd; do
        echo "  Running: $_fix_cmd"
        if ! eval "$_fix_cmd"; then
          echo "  FAILED: $_fix_cmd"
          echo ""
          echo "$_DEP_CHECK_OUTPUT"
          echo ""
          echo "Auto-publish failed. Resolve manually, then re-run."
          exit 1
        fi
        echo "  OK"
      done <<< "$_FIX_CMDS"
      echo ""
      # Re-check after auto-publish
      if ! bash "$SCRIPT_DIR/check_workspace_deps.sh" "$PROJECT_DIR" $_DEP_CHECK_WORKSPACE_ARG; then
        echo ""
        echo "Dependencies still missing after auto-publish. Resolve manually."
        exit 1
      fi
    else
      echo "$_DEP_CHECK_OUTPUT"
      echo ""
      echo "Resolve the missing dependencies above, then re-run this command."
      exit 1
    fi
  else
    echo "$_DEP_CHECK_OUTPUT"
    echo ""
    echo "Resolve the missing dependencies above, then re-run this command."
    echo "Hint: use --auto-publish-deps on sbt_build.sh to auto-fix missing dependencies."
    exit 1
  fi
else
  # RC=0 but there may be STALE warnings with Fix commands
  if [ -n "$_DEP_CHECK_OUTPUT" ]; then
    _STALE_FIX_CMDS=$(echo "$_DEP_CHECK_OUTPUT" | grep -oE 'Fix: bash .*' | sed 's/^Fix: //' || true)
    if [ -n "$_STALE_FIX_CMDS" ] && [ "$AUTO_PUBLISH_DEPS" = true ]; then
      echo "=== Auto-Publishing Stale Dependencies ==="
      while IFS= read -r _fix_cmd; do
        [ -z "$_fix_cmd" ] && continue
        echo "  Running: $_fix_cmd"
        if ! eval "$_fix_cmd"; then
          echo "  FAILED: $_fix_cmd"
          echo "  (continuing — stale deps are best-effort)"
        else
          echo "  OK"
        fi
      done <<< "$_STALE_FIX_CMDS"
      echo ""
    else
      echo "$_DEP_CHECK_OUTPUT"
      echo ""
    fi
  fi
fi

if "${RUN_CMD[@]}" >"$LOG_FILE" 2>&1; then
  RUN_RC=0
else
  RUN_RC=$?
fi

# ── Check log freshness ────────────────────────────────────────────────────
_LOG_MTIME=$(stat -f '%m' "$LOG_FILE" 2>/dev/null || stat -c '%Y' "$LOG_FILE" 2>/dev/null || echo 0)
if [ "$_LOG_MTIME" -lt "$_START_TIME" ] && [ "$_LOG_MTIME" -gt 0 ]; then
  echo ""
  echo "WARNING: Log file is from a previous run (mtime predates this invocation)."
  echo "This may indicate the SBT command did not execute. Check for lock contention or server issues."
  echo ""
fi

echo "=== SBT Run Summary ==="
echo "Project: $PROJECT_DIR"
printf 'Command:'
printf ' %q' "${RUN_CMD[@]}"
echo
echo "Log: $LOG_FILE"

# Human-readable exit code explanation
case "$RUN_RC" in
  0) echo "Exit code: 0 (SUCCESS)" ;;
  1) echo "Exit code: 1 (SBT error — compilation failure, test failure, or resolution error)" ;;
  2) echo "Exit code: 2 (Infrastructure error — lock contention, missing Java, missing config)" ;;
  *) echo "Exit code: $RUN_RC" ;;
esac

if [ "$RUN_RC" -eq 0 ]; then
  echo "Result: SUCCESS"
  if [ "$TAIL_LINES" -gt 0 ]; then
    echo
    echo "--- Log tail ---"
    tail -n "$TAIL_LINES" "$LOG_FILE"
  fi
  exit 0
fi

echo "Result: FAILED"
echo
echo "--- Error Summary ---"
if ! grep -E '^\[error\]|SSLHandshakeException|cannot be mapped using the root paths|ResolveException|Credentials file|not a valid command|OutOfMemoryError|NoSuchMethodError|NoSuchFieldError|Exception:|unresolved dependency|not found: .*ivy\.xml' "$LOG_FILE" | head -n 25; then
  echo "(no structured error lines found; inspect the full log)"
fi

echo
echo "--- Suggested Next Actions ---"
GUIDANCE_COUNT=0
if grep -q 'cannot be mapped using the root paths' "$LOG_FILE"; then
  echo "- rootPaths conflict detected: prefer isolated publishLocal flows, avoid dev-mode source rewiring for this validation path, and clear stale local artifacts before retrying"
  GUIDANCE_COUNT=$((GUIDANCE_COUNT + 1))
fi
if grep -q 'SSLHandshakeException' "$LOG_FILE"; then
  echo "- TLS or trust failure detected: verify JVM trust settings and private repository connectivity"
  GUIDANCE_COUNT=$((GUIDANCE_COUNT + 1))
fi
if grep -q 'ResolveException' "$LOG_FILE"; then
  echo "- dependency resolution failed: check ~/.ivy2/.credentials and confirm the required artifact/version is actually published or locally available"
  GUIDANCE_COUNT=$((GUIDANCE_COUNT + 1))
fi
if grep -Eq 'Credentials file|~/.ivy2/.credentials' "$LOG_FILE"; then
  echo "- credentials appear to be missing: create ~/.ivy2/.credentials if private resolver access is required"
  GUIDANCE_COUNT=$((GUIDANCE_COUNT + 1))
fi
if grep -Eq 'not found: .*ivy\.xml|unresolved dependency' "$LOG_FILE"; then
  echo "- missing Ivy metadata suggests a stale or missing local publish: verify the published version and use sbt_refresh.sh or sbt_status.sh --verify if downstream still resolves an older artifact"
  GUIDANCE_COUNT=$((GUIDANCE_COUNT + 1))
fi
if grep -Eq 'NoSuchMethodError|NoSuchFieldError' "$LOG_FILE"; then
  echo "- stale artifact detected: a class on the classpath references a method/field that no longer exists in the resolved dependency"
  echo "  This typically means an upstream workspace repo was changed but the downstream artifact was not republished"
  echo "  Fix: use sbt_refresh.sh --publish-upstreams --clean-target --rebuild"
  echo "  Use sbt_status.sh --workspace to identify which workspace artifacts need republishing"
  GUIDANCE_COUNT=$((GUIDANCE_COUNT + 1))
fi
if [ "$GUIDANCE_COUNT" -eq 0 ]; then
  echo "- no specific guidance matched; inspect the full log for the first meaningful failure"
fi

if [ "$TAIL_LINES" -gt 0 ]; then
  echo
  echo "--- Log tail ---"
  tail -n "$TAIL_LINES" "$LOG_FILE"
fi

exit "$RUN_RC"
