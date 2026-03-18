#!/usr/bin/env bash
# sbt_refresh.sh — Fix stale state: publish upstreams, clear caches, rebuild
#
# Default: clear caches for the project's artifacts and optionally rebuild.
# With --publish-upstreams: first publish all upstream workspace deps in
# dependency order, then clear caches and optionally rebuild.
#
# Usage:
#   sbt_refresh.sh <project-dir> [options]
#
# Examples:
#   sbt_refresh.sh /path/to/service --publish-upstreams --clean-target --rebuild
#   sbt_refresh.sh /path/to/service --artifact my-lib --version 0.532.0 --clean-target --rebuild
#   sbt_refresh.sh /path/to/service --publish-upstreams --artifact-version 0.532.0 --dry-run

set -euo pipefail

usage() {
  echo "Usage: sbt_refresh.sh <project-dir> [options]" >&2
  echo "" >&2
  echo "Options:" >&2
  echo "  --publish-upstreams          Publish upstream workspace deps in order first" >&2
  echo "  --artifact-version <version> Version for publishLocal (required with --publish-upstreams)" >&2
  echo "  --artifact <name>            Artifact name for targeted cache clearing" >&2
  echo "  --version <version>          Version for targeted cache clearing" >&2
  echo "  --clean-target               Delete project target/ directory" >&2
  echo "  --rebuild                    Rebuild with 'compile' after refresh" >&2
  echo "  --rebuild-arg <sbt-arg>      Explicit SBT arg for rebuild (overrides --rebuild)" >&2
  echo "  --workspace-dir <dir>        Override workspace directory" >&2
  echo "  --dry-run                    Show what would be done without doing it" >&2
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
PUBLISH_UPSTREAMS=false
ARTIFACT_VERSION=""
ARTIFACT_NAME=""
CACHE_VERSION=""
CLEAN_TARGET=false
KILL_SERVER=false
REBUILD=false
REBUILD_ARGS=()
DRY_RUN=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    --kill-server)
      KILL_SERVER=true
      shift
      ;;
    --workspace-dir)
      [ "$#" -ge 2 ] || usage
      WORKSPACE_DIR="$2"
      shift 2
      ;;
    --publish-upstreams)
      PUBLISH_UPSTREAMS=true
      shift
      ;;
    --artifact-version)
      [ "$#" -ge 2 ] || usage
      ARTIFACT_VERSION="$2"
      shift 2
      ;;
    --artifact)
      [ "$#" -ge 2 ] || usage
      ARTIFACT_NAME="$2"
      shift 2
      ;;
    --version)
      [ "$#" -ge 2 ] || usage
      CACHE_VERSION="$2"
      shift 2
      ;;
    --clean-target)
      CLEAN_TARGET=true
      shift
      ;;
    --rebuild)
      REBUILD=true
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
if [ ! -f "$PROJECT_DIR/build.sbt" ]; then
  echo "ERROR: No build.sbt found in $PROJECT_DIR" >&2
  exit 2
fi

WORKSPACE_DIR="$(resolve_workspace_dir "$WORKSPACE_DIR" "$PROJECT_DIR")"

# Default rebuild arg
if [ "$REBUILD" = true ] && [ ${#REBUILD_ARGS[@]} -eq 0 ]; then
  REBUILD_ARGS=(compile)
fi

# ── Kill SBT server if requested or --clean-target is used ─────────────────
if [ "$KILL_SERVER" = true ] || [ "$CLEAN_TARGET" = true ]; then
  _PROJ_NAME="$(basename "$PROJECT_DIR")"
  if [ "$DRY_RUN" = true ]; then
    echo "[dry-run] Would attempt to shut down SBT server for $_PROJ_NAME"
  else
    echo "=== Shutting down SBT server for $_PROJ_NAME ==="
    # Try graceful shutdown first via sbt --client
    if (cd "$PROJECT_DIR" && sbt --client shutdown 2>/dev/null); then
      echo "  SBT server shut down gracefully."
    else
      # Fallback: kill any sbt process associated with this project
      _KILLED=false
      for _pid in $(pgrep -f "sbt.*$(basename "$PROJECT_DIR")" 2>/dev/null || true); do
        if kill "$_pid" 2>/dev/null; then
          echo "  Killed SBT process $_pid"
          _KILLED=true
        fi
      done
      if [ "$_KILLED" = false ]; then
        echo "  No active SBT server found."
      fi
    fi
    echo ""
  fi
fi

# ── Phase 1: Publish upstream deps ──────────────────────────────────────────
if [ "$PUBLISH_UPSTREAMS" = true ]; then
  PUBLISH_CMD=(bash "$SCRIPT_DIR/publish_chain.sh" --workspace-dir "$WORKSPACE_DIR" --target-project "$PROJECT_DIR")
  if [ -n "$ARTIFACT_VERSION" ]; then
    PUBLISH_CMD+=(--artifact-version "$ARTIFACT_VERSION")
  fi
  if [ "$DRY_RUN" = true ]; then
    PUBLISH_CMD+=(--dry-run)
  fi
  PUBLISH_CMD+=("$PROJECT_DIR")

  echo "=== Phase 1: Publish Upstream Dependencies ==="
  echo ""
  "${PUBLISH_CMD[@]}"
  echo ""
fi

# ── Phase 2: Refresh downstream caches ──────────────────────────────────────
REFRESH_CMD=(bash "$SCRIPT_DIR/refresh_downstream.sh" "$PROJECT_DIR" --workspace-dir "$WORKSPACE_DIR")
if [ -n "$ARTIFACT_NAME" ]; then
  REFRESH_CMD+=(--artifact "$ARTIFACT_NAME")
fi
if [ -n "$CACHE_VERSION" ]; then
  REFRESH_CMD+=(--version "$CACHE_VERSION")
fi
if [ "$CLEAN_TARGET" = true ]; then
  REFRESH_CMD+=(--clean-target)
fi
if [ ${#REBUILD_ARGS[@]} -gt 0 ]; then
  for arg in "${REBUILD_ARGS[@]}"; do
    REFRESH_CMD+=(--rebuild-arg "$arg")
  done
fi
if [ "$DRY_RUN" = true ]; then
  REFRESH_CMD+=(--dry-run)
fi

if [ "$PUBLISH_UPSTREAMS" = true ]; then
  echo "=== Phase 2: Refresh Caches ==="
else
  echo "=== Refresh Caches ==="
fi
echo ""
"${REFRESH_CMD[@]}"
