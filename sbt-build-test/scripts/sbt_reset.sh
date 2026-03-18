#!/usr/bin/env bash
# sbt_reset.sh — Wipe the isolated build cache and return to clean state
#
# After reset, all builds will resolve from remote (Artifactory/Maven Central)
# as they normally would. No local publishes will remain.
#
# Usage:
#   sbt_reset.sh [options]
#
# Examples:
#   sbt_reset.sh                    # Wipe everything in ~/.sbt-build-cache
#   sbt_reset.sh --local-only       # Only wipe local publishes, keep downloaded cache
#   sbt_reset.sh --dry-run          # Show what would be deleted

set -euo pipefail

usage() {
  echo "Usage: sbt_reset.sh [--local-only] [--dry-run]" >&2
  echo "" >&2
  echo "Options:" >&2
  echo "  --local-only   Only wipe local publishes (~/.sbt-build-cache/local/)" >&2
  echo "  --dry-run      Show what would be deleted without deleting" >&2
  exit 2
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

LOCAL_ONLY=false
DRY_RUN=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    --local-only) LOCAL_ONLY=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    *) usage ;;
  esac
done

echo "=== SBT Build Cache Reset ==="
echo "Cache root: $SBT_BUILD_CACHE_ROOT"
echo ""

if [ ! -d "$SBT_BUILD_CACHE_ROOT" ]; then
  echo "Cache does not exist. Nothing to reset."
  exit 0
fi

if [ "$LOCAL_ONLY" = true ]; then
  TARGET="$SBT_BUILD_CACHE_ROOT/local"
  echo "Mode: local publishes only"
else
  TARGET="$SBT_BUILD_CACHE_ROOT"
  echo "Mode: full cache wipe"
fi

if [ ! -d "$TARGET" ]; then
  echo "Target directory does not exist: $TARGET"
  echo "Nothing to reset."
  exit 0
fi

SIZE=$(du -sh "$TARGET" 2>/dev/null | cut -f1 || echo "unknown")
echo "Size: $SIZE"
echo ""

if [ "$LOCAL_ONLY" = true ]; then
  echo "Will delete: $TARGET/"
else
  echo "Will delete:"
  echo "  $SBT_BUILD_CACHE_ROOT/local/   (local publishes)"
  echo "  $SBT_BUILD_CACHE_ROOT/cache/   (downloaded artifacts)"
  echo "  $SBT_BUILD_CACHE_ROOT/logs/    (build logs)"
  echo "  $SBT_BUILD_CACHE_ROOT/locks/   (lock files)"
fi

echo ""
if [ "$DRY_RUN" = true ]; then
  echo "DRY RUN — nothing deleted."
  exit 0
fi

rm -rf "$TARGET"
echo "Deleted: $TARGET"

if [ "$LOCAL_ONLY" = false ]; then
  # Recreate the directory structure
  ensure_sbt_skill_dirs
  echo "Recreated empty cache structure."
fi

echo ""
echo "Reset complete. All builds will now resolve from remote repositories."
echo "Use sbt_build.sh --auto-publish-deps to re-publish workspace deps as needed."
