#!/usr/bin/env bash
# sbt_build.sh — Compile, test, or publishLocal one, several, or all projects
#
# Accepts one or more project directories (or --all for the entire workspace).
# Automatically handles preflight, dependency publishing, log capture, and
# JUnit XML test report parsing.
#
# Usage:
#   sbt_build.sh <project-dir>... [options] -- <sbt-commands>
#   sbt_build.sh --all [options] -- <sbt-commands>
#
# Examples:
#   sbt_build.sh /path/to/service -- compile
#   sbt_build.sh /path/to/service -- test
#   sbt_build.sh /path/to/service -- "core / test"
#   sbt_build.sh /path/to/svc-a /path/to/svc-b -- compile
#   sbt_build.sh --all -- compile
#   sbt_build.sh --all --auto-publish-deps -- test
#   sbt_build.sh /path/to/service --auto-publish-deps -- compile
#   sbt_build.sh /path/to/library --artifact-version 0.532.0 -- publishLocal

set -euo pipefail

usage() {
  echo "Usage: sbt_build.sh <project-dir>... [options] -- <sbt-commands>" >&2
  echo "       sbt_build.sh --all [options] -- <sbt-commands>" >&2
  echo "" >&2
  echo "Options:" >&2
  echo "  --all                        Build all workspace projects in dependency order" >&2
  echo "  --workspace-dir <dir>        Override workspace directory" >&2
  echo "  --artifact-version <version> Set ARTIFACT_VERSION for publishLocal" >&2
  echo "  --sbt-env <value>            Pass -Dsbt_env=<value> to SBT" >&2
  echo "  --tail <lines>               Lines of log tail to show (default: 60)" >&2
  echo "  --auto-publish-deps          Auto-publishLocal missing/stale workspace deps" >&2
  echo "  --continue-on-error          Keep going when a project fails (for --all)" >&2
  echo "  --coverage                   Run scoverage for the requested SBT command" >&2
  echo "  --no-remote-cache            Disable remote-cache pulls for this run" >&2
  echo "  --skip-preflight             Skip Java/cache pre-check" >&2
  exit 2
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage
fi

[ "$#" -ge 2 ] || usage

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# ── Parse arguments: collect project dirs, then options, then -- sbt-args ────
PROJECT_DIRS=()
BUILD_ALL=false
WORKSPACE_DIR=""
TAIL_LINES=60
SKIP_PREFLIGHT=false
AUTO_PUBLISH=false
CONTINUE_ON_ERROR=false
CAPTURE_ARGS=()
FRESH_MODE=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    --all)
      BUILD_ALL=true
      shift
      ;;
    --fresh)
      FRESH_MODE=true
      shift
      ;;
    --workspace-dir)
      [ "$#" -ge 2 ] || usage
      WORKSPACE_DIR="$2"
      CAPTURE_ARGS+=(--workspace-dir "$2")
      shift 2
      ;;
    --artifact-version)
      [ "$#" -ge 2 ] || usage
      CAPTURE_ARGS+=(--artifact-version "$2")
      shift 2
      ;;
    --sbt-env)
      [ "$#" -ge 2 ] || usage
      CAPTURE_ARGS+=(--sbt-env "$2")
      shift 2
      ;;
    --tail)
      [ "$#" -ge 2 ] || usage
      TAIL_LINES="$2"
      shift 2
      ;;
    --label)
      [ "$#" -ge 2 ] || usage
      CAPTURE_ARGS+=(--label "$2")
      shift 2
      ;;
    --log-file)
      [ "$#" -ge 2 ] || usage
      CAPTURE_ARGS+=(--log-file "$2")
      shift 2
      ;;
    --auto-publish-deps)
      AUTO_PUBLISH=true
      CAPTURE_ARGS+=(--auto-publish-deps)
      shift
      ;;
    --skip-preflight)
      SKIP_PREFLIGHT=true
      shift
      ;;
    --coverage)
      CAPTURE_ARGS+=(--coverage)
      shift
      ;;
    --no-remote-cache)
      CAPTURE_ARGS+=(--no-remote-cache)
      shift
      ;;
    --continue-on-error)
      CONTINUE_ON_ERROR=true
      shift
      ;;
    --strict)
      CAPTURE_ARGS+=(--strict)
      shift
      ;;
    --)
      shift
      break
      ;;
    -*)
      usage
      ;;
    *)
      # Positional arg = project directory
      PROJECT_DIRS+=("$1")
      shift
      ;;
  esac
done

[ "$#" -gt 0 ] || usage
SBT_ARGS=("$@")

# Pass --fresh mode as --batch to capture/run scripts
if [ "$FRESH_MODE" = true ]; then
  CAPTURE_ARGS+=(--batch)
fi

# ── Resolve workspace ────────────────────────────────────────────────────────
if [ ${#PROJECT_DIRS[@]} -gt 0 ]; then
  _first_dir="$(cd "${PROJECT_DIRS[0]}" && pwd)"
  WORKSPACE_DIR="$(resolve_workspace_dir "$WORKSPACE_DIR" "$_first_dir")"
elif [ "$BUILD_ALL" = true ] && [ -n "$WORKSPACE_DIR" ]; then
  WORKSPACE_DIR="$(cd "$WORKSPACE_DIR" && pwd)"
elif [ "$BUILD_ALL" = true ]; then
  WORKSPACE_DIR="$(pwd)"
else
  usage
fi

# ── Resolve project list ─────────────────────────────────────────────────────
if [ "$BUILD_ALL" = true ]; then
  source "$SCRIPT_DIR/resolve_projects.sh"
  # Use workspace graph to get dependency-ordered list
  _GRAPH_JSON=$(mktemp)
  _ORDER_FILE=$(mktemp)
  trap 'rm -f "$_GRAPH_JSON" "$_ORDER_FILE"' EXIT
  build_workspace_graph_json "$SCRIPT_DIR" "$WORKSPACE_DIR" "$GROUP_ID" "$_GRAPH_JSON" "${SERVICES[@]}"
  python3 -c "
import json, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text())
repo_by_name = {r['name']: r['path'] for r in data['repos']}
for name in data.get('publish_order', []):
    if name in repo_by_name:
        print(repo_by_name[name])
" "$_GRAPH_JSON" > "$_ORDER_FILE"
  PROJECT_DIRS=()
  while IFS= read -r _p; do
    [ -n "$_p" ] && PROJECT_DIRS+=("$_p")
  done < "$_ORDER_FILE"
  rm -f "$_GRAPH_JSON" "$_ORDER_FILE"
  trap - EXIT
  if [ ${#PROJECT_DIRS[@]} -eq 0 ]; then
    echo "ERROR: No SBT projects found in $WORKSPACE_DIR" >&2
    exit 2
  fi
  echo "=== Building ${#PROJECT_DIRS[@]} projects in dependency order ==="
  for _i in "${!PROJECT_DIRS[@]}"; do
    echo "  $((_i + 1)). $(basename "${PROJECT_DIRS[$_i]}")"
  done
  echo ""
else
  # Resolve each provided dir
  _resolved=()
  for _d in "${PROJECT_DIRS[@]}"; do
    _abs="$(cd "$_d" && pwd)"
    if [ ! -f "$_abs/build.sbt" ]; then
      echo "ERROR: No build.sbt found in $_abs" >&2
      exit 2
    fi
    _resolved+=("$_abs")
  done
  PROJECT_DIRS=("${_resolved[@]}")
fi

# ── Lightweight preflight ────────────────────────────────────────────────────
if [ "$SKIP_PREFLIGHT" = false ]; then
  if [ "$BUILD_ALL" != true ]; then
    source "$SCRIPT_DIR/resolve_projects.sh"
  fi
  JAVA_HOME_RESOLVED="$(resolve_java_home_for_version "$JAVA_VERSION")"
  if [ -z "$JAVA_HOME_RESOLVED" ]; then
    echo "ERROR: Java $JAVA_VERSION not found. Install a matching JDK or set .java_version in .sbt-workspace.conf." >&2
    exit 1
  fi
  ensure_sbt_skill_dirs
fi

# ── For multi-project: publish upstream deps (NOT the targets themselves) ─────
if [ ${#PROJECT_DIRS[@]} -gt 1 ] && [ "$AUTO_PUBLISH" = true ]; then
  # Compute upstream-only repos by excluding the target projects from the chain.
  # publish_chain.sh walks deps transitively, so we pass all targets but then
  # filter out the targets from the publish list via a temp exclusion file.
  _UPSTREAM_REPOS=()
  _target_set=""
  for _td in "${PROJECT_DIRS[@]}"; do
    _target_set="${_target_set}|$(basename "$_td")"
  done
  _target_set="${_target_set#|}"

  # Get the full chain for all targets, then exclude the targets themselves
  _CHAIN_JSON=$(mktemp)
  _CHAIN_ORDER=$(mktemp)
  trap 'rm -f "$_CHAIN_JSON" "$_CHAIN_ORDER"' EXIT
  if [ "$BUILD_ALL" != true ]; then
    source "$SCRIPT_DIR/resolve_projects.sh" 2>/dev/null || true
  fi
  build_workspace_graph_json "$SCRIPT_DIR" "$WORKSPACE_DIR" "${GROUP_ID:-}" "$_CHAIN_JSON" "${SERVICES[@]}" 2>/dev/null || true

  if [ -s "$_CHAIN_JSON" ]; then
    python3 -c "
import json, sys
from pathlib import Path
graph = json.loads(Path(sys.argv[1]).read_text())
targets = set(sys.argv[2].split('|'))
repo_by_name = {r['name']: r for r in graph['repos']}
deps = {r['name']: set(r.get('dependencies', [])) for r in graph['repos']}
# Walk all upstream deps of all targets
needed = set()
stack = []
for t in targets:
    stack.extend(sorted(deps.get(t, set())))
while stack:
    c = stack.pop()
    if c in needed:
        continue
    needed.add(c)
    stack.extend(sorted(deps.get(c, set())))
# Exclude targets themselves
upstream_only = [n for n in graph.get('publish_order', []) if n in needed and n not in targets]
for name in upstream_only:
    r = repo_by_name.get(name)
    if r:
        print(r['path'])
" "$_CHAIN_JSON" "$_target_set" > "$_CHAIN_ORDER"

    while IFS= read -r _up; do
      [ -n "$_up" ] && _UPSTREAM_REPOS+=("$_up")
    done < "$_CHAIN_ORDER"
  fi
  rm -f "$_CHAIN_JSON" "$_CHAIN_ORDER"
  trap - EXIT

  if [ ${#_UPSTREAM_REPOS[@]} -gt 0 ]; then
    echo "=== Publishing ${#_UPSTREAM_REPOS[@]} upstream dependencies ==="
    bash "$SCRIPT_DIR/publish_chain.sh" --workspace-dir "$WORKSPACE_DIR" \
      --target-project "${PROJECT_DIRS[0]}" "${_UPSTREAM_REPOS[@]}"
    echo ""
  fi
fi

# ── Detect test commands for auto-report-parsing ─────────────────────────────
IS_TEST_CMD=false
for sbt_arg in "${SBT_ARGS[@]}"; do
  case "$sbt_arg" in
    *testOnly*|*" / test"*|test|*"/test"*|coverage)
      IS_TEST_CMD=true
      break
      ;;
  esac
done

# ── Pre-check: report stale locks (visible to user, not hidden in log) ──────
if [ "$IS_TEST_CMD" = true ]; then
  for _check_dir in "${PROJECT_DIRS[@]}"; do
    _check_lock="$(test_activity_lock_file "$_check_dir")"
    if [ -f "$_check_lock" ]; then
      _check_pid=$(grep -oE '^pid=[0-9]+' "$_check_lock" 2>/dev/null | cut -d= -f2 || true)
      _check_stale=false
      if [ -n "$_check_pid" ] && ! kill -0 "$_check_pid" 2>/dev/null; then
        _check_stale=true
      fi
      if [ "$_check_stale" = false ] && [ -f "$_check_lock" ]; then
        _check_age_limit=$((2 * 60 * 60))
        _check_mtime=$(stat -f '%m' "$_check_lock" 2>/dev/null || stat -c '%Y' "$_check_lock" 2>/dev/null || echo 0)
        _check_now=$(date '+%s')
        if [ $((_check_now - _check_mtime)) -ge "$_check_age_limit" ]; then
          _check_stale=true
        fi
      fi
      if [ "$_check_stale" = true ]; then
        echo "WARNING: Stale lock detected for $(basename "$_check_dir") (PID ${_check_pid:-unknown} is dead). Will auto-clear."
      fi
    fi
  done
fi

# ── Build each project ───────────────────────────────────────────────────────
OVERALL_RC=0
RESULTS=()

for PROJECT_DIR in "${PROJECT_DIRS[@]}"; do
  _name="$(basename "$PROJECT_DIR")"

  if [ ${#PROJECT_DIRS[@]} -gt 1 ]; then
    echo ""
    echo "================================================================"
    echo "=== Building: $_name"
    echo "================================================================"
  fi

  # Build the capture command
  _PROJ_CAPTURE_ARGS=()
  if [ ${#CAPTURE_ARGS[@]} -gt 0 ]; then
    _PROJ_CAPTURE_ARGS=("${CAPTURE_ARGS[@]}")
  fi
  _PROJ_CAPTURE_ARGS+=(--tail "$TAIL_LINES")

  # For single-project, pass auto-publish as-is.
  # For multi-project, upstreams were published upfront; skip per-project auto-publish
  # but still pass it for stale dep detection.
  CAPTURE_CMD=(bash "$SCRIPT_DIR/run_sbt_capture.sh" "$PROJECT_DIR" "${_PROJ_CAPTURE_ARGS[@]}" --)
  for arg in "${SBT_ARGS[@]}"; do
    CAPTURE_CMD+=("$arg")
  done

  if "${CAPTURE_CMD[@]}"; then
    SBT_RC=0
  else
    SBT_RC=$?
  fi

  # Auto-parse test reports (search up to 3 levels deep for multi-project builds)
  if [ "$IS_TEST_CMD" = true ] && [ "$SBT_RC" -le 1 ]; then
    REPORT_DIRS=()
    while IFS= read -r _report_dir; do
      [ -n "$_report_dir" ] && REPORT_DIRS+=("$(dirname "$_report_dir")")
    done < <(find "$PROJECT_DIR" -maxdepth 4 -path "*/target/test-reports" -type d 2>/dev/null | sort)

    if [ ${#REPORT_DIRS[@]} -gt 0 ]; then
      echo ""
      echo "=== Test Report Parsing ==="
      for report_target in "${REPORT_DIRS[@]}"; do
        bash "$SCRIPT_DIR/parse_test_reports.sh" "$report_target" || true
      done
    fi
  fi

  if [ "$SBT_RC" -ne 0 ]; then
    OVERALL_RC="$SBT_RC"
    RESULTS+=("FAIL: $_name (exit $SBT_RC)")
    if [ "$CONTINUE_ON_ERROR" = false ] && [ ${#PROJECT_DIRS[@]} -gt 1 ]; then
      echo ""
      echo "Stopping on first failure. Use --continue-on-error to keep going."
      break
    fi
  else
    RESULTS+=("OK:   $_name")
  fi
done

# ── Summary for multi-project builds ─────────────────────────────────────────
if [ ${#PROJECT_DIRS[@]} -gt 1 ]; then
  echo ""
  echo "================================================================"
  echo "=== Build Summary ==="
  echo "================================================================"
  for _result in "${RESULTS[@]}"; do
    echo "  $_result"
  done
  echo ""
  if [ "$OVERALL_RC" -eq 0 ]; then
    echo "All ${#PROJECT_DIRS[@]} projects succeeded."
  else
    echo "One or more projects failed."
  fi
fi

exit "$OVERALL_RC"
