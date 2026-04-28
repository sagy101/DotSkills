#!/usr/bin/env bash
# preflight_check.sh — Pre-flight checks for build sessions
#
# Usage: preflight_check.sh <workspace-dir>
#
# Performs the following checks:
#   1. Requested Java availability
#   2. python3 availability for JUnit XML parsing
#   3. ~/.ivy2/.credentials existence
#   4. ~/.sbt-build-cache/ setup (isolated Ivy home for skill builds)
#   5. Branch report for all SBT repos in the workspace
#   6. Stale local publish detection in ~/.sbt-build-cache/
#   7. Default Ivy local contamination detection
#   8. Resolver and remote-cache risk detection
#
# Exit codes:
#   0 — all checks passed (warnings may still be present)
#   1 — fatal error (e.g., Java not found)
#   2 — usage error

set -uo pipefail

WORKSPACE_DIR="${1:?Usage: preflight_check.sh <workspace-dir>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"
SBT_BUILD_CACHE="$SBT_BUILD_CACHE_ROOT"

# Resolve all SBT projects (auto-scan + config overrides)
source "$SCRIPT_DIR/resolve_projects.sh"

WARN_COUNT=0
warn() { echo "  WARN: $*"; WARN_COUNT=$((WARN_COUNT + 1)); }
ok()   { echo "  OK: $*"; }
fail() { echo "  FAIL: $*"; }

# ─── 1. Java ──────────────────────────────────────────────────────────────────

echo "=== Pre-flight Check ==="
echo ""
echo "--- Java $JAVA_VERSION ---"

JAVA_HOME_RESOLVED="$(resolve_java_home_for_version "$JAVA_VERSION")"
if [ -z "$JAVA_HOME_RESOLVED" ]; then
  fail "Java $JAVA_VERSION not found. Install a matching JDK or set .java_version in .sbt-workspace.conf."
  echo ""
  echo "=== Pre-flight FAILED ==="
  exit 1
else
  JAVA_VER=$("$JAVA_HOME_RESOLVED/bin/java" -version 2>&1 | head -1)
  ok "Java $JAVA_VERSION found: $JAVA_VER"
  echo "  JAVA_HOME=$JAVA_HOME_RESOLVED"
fi

echo ""

# ─── 2. Python 3 ──────────────────────────────────────────────────────────────

echo "--- Python 3 ---"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_VER=$(python3 --version 2>&1 | head -1)
  PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)' 2>/dev/null || echo "0")
  if [ "$PYTHON_MINOR" -ge 10 ] 2>/dev/null; then
    ok "$PYTHON_VER (>= 3.10)"
  else
    warn "$PYTHON_VER — 3.10+ recommended for full compatibility"
  fi
  echo "  Required by parse_test_reports.sh for XML parsing"
else
  warn "python3 not found — parse_test_reports.sh will not work"
  echo "  Agent action: ask the user to install python3 before parsing test reports"
  echo "  Do not auto-install system dependencies without user approval"
fi

echo ""

# ─── 3. Credentials ───────────────────────────────────────────────────────────

echo "--- Credentials ---"

if [ -f "$HOME/.ivy2/.credentials" ]; then
  ok "~/.ivy2/.credentials exists"
else
  warn "~/.ivy2/.credentials not found — Artifactory resolution will fail, local builds still work"
fi

echo ""

# ─── 4. Isolated Build Cache ──────────────────────────────────────────────────

echo "--- Isolated Build Cache ---"

if [ -d "$SBT_BUILD_CACHE" ]; then
  CACHE_SIZE=$(du -sh "$SBT_BUILD_CACHE" 2>/dev/null | cut -f1)
  ok "$SBT_BUILD_CACHE exists (size: $CACHE_SIZE)"
else
  mkdir -p "$SBT_BUILD_CACHE"
  ok "$SBT_BUILD_CACHE created (first use)"
fi

echo "  All publishLocal and sbt commands should use:"
echo "    -Dsbt.ivy.home=$SBT_BUILD_CACHE"
echo ""

# ─── 5. Branch Report ─────────────────────────────────────────────────────────

echo "--- Repository Branches ---"

if [ -f "$WORKSPACE_DIR/.sbt-workspace.conf" ]; then
  echo "  (using overrides from .sbt-workspace.conf)"
fi

if [ ${#SERVICES[@]} -eq 0 ]; then
  warn "No SBT projects found"
else
  for dir in "${SERVICES[@]}"; do
    REPO_NAME=$(basename "$dir")

    if [ -d "$dir/.git" ]; then
      BRANCH=$(git -C "$dir" branch --show-current 2>/dev/null || echo "<detached>")
      DIRTY=""
      if [ -n "$(git -C "$dir" status --porcelain 2>/dev/null)" ]; then
        DIRTY=" [dirty]"
      fi
      printf "  %-25s %s%s\n" "$REPO_NAME" "$BRANCH" "$DIRTY"
    else
      printf "  %-25s %s\n" "$REPO_NAME" "(no git repo)"
    fi
  done
fi

echo ""

# ─── 5b. Branch Alignment ───────────────────────────────────────────────────

echo "--- Branch Alignment ---"

_FEATURE_COUNT=0
if [ ${#SERVICES[@]} -gt 0 ]; then
  for dir in "${SERVICES[@]}"; do
    if [ -d "$dir/.git" ]; then
      BRANCH=$(git -C "$dir" branch --show-current 2>/dev/null || echo "")
      if [ -n "$BRANCH" ] && [ "$BRANCH" != "master" ] && [ "$BRANCH" != "main" ]; then
        _FEATURE_COUNT=$((_FEATURE_COUNT + 1))
      fi
    fi
  done
fi

if [ "$_FEATURE_COUNT" -gt 0 ]; then
  warn "$_FEATURE_COUNT repo(s) on feature branches (see branch report above)"
  echo "  Repos on feature branches have likely diverged from the Artifactory"
  echo "  artifact (built from master). Downstream consumers may resolve stale"
  echo "  artifacts (risk: NoSuchMethodError, missing classes)."
  echo "  Use check_workspace_deps.sh <target-repo> to detect stale dependencies."
else
  ok "All repos on master/main — no stale artifact risk"
fi

echo ""

# ─── 6. Stale Local Publishes ─────────────────────────────────────────────────

echo "--- Stale Local Publishes ---"

LOCAL_DIR="$SBT_BUILD_CACHE/local"
STALE_COUNT=0

if [ -z "$GROUP_ID" ]; then
  warn "Workspace group ID could not be inferred — skipping stale local publish scan"
elif [ -d "$LOCAL_DIR/$GROUP_ID" ]; then
  while IFS= read -r artifact_dir; do
    [ -d "$artifact_dir" ] || continue
    ART_NAME=$(basename "$artifact_dir")
    # Find versions published locally
    for ver_dir in "$artifact_dir"/*/; do
      [ -d "$ver_dir" ] || continue
      VER=$(basename "$ver_dir")
      AGE=""
      # Find the newest file in the version dir to estimate age
      NEWEST=$(find "$ver_dir" -type f -newer "$ver_dir" -print -quit 2>/dev/null || true)
      if [ -z "$NEWEST" ]; then
        # Use the dir itself
        if stat -f %Sm -t "%Y-%m-%d %H:%M" "$ver_dir" >/dev/null 2>&1; then
          AGE=" (published: $(stat -f %Sm -t '%Y-%m-%d %H:%M' "$ver_dir"))"
        fi
      fi
      echo "  $ART_NAME @ $VER$AGE"
      STALE_COUNT=$((STALE_COUNT + 1))
    done
  done < <(find "$LOCAL_DIR/$GROUP_ID" -mindepth 1 -maxdepth 1 -type d 2>/dev/null)
fi

if [ -z "$GROUP_ID" ]; then
  :
elif [ "$STALE_COUNT" -eq 0 ]; then
  ok "No local publishes found in $SBT_BUILD_CACHE — clean state"
else
  warn "$STALE_COUNT locally published artifact(s) found in $SBT_BUILD_CACHE"
  echo ""
  echo "  To clean: rm -rf $LOCAL_DIR/$GROUP_ID"
  echo "  These artifacts are isolated and do NOT affect normal sbt builds."
  echo "  Clean them if starting fresh or if versions may be stale."
fi

echo ""

# ─── 7. Default Ivy Local Contamination ────────────────────────────────────────

echo "--- Default Ivy Local Contamination ---"

IVY_LOCAL_GROUP_DIR=""
if [ -z "$GROUP_ID" ]; then
  warn "Workspace group ID could not be inferred — skipping default Ivy local scan"
else
  IVY_LOCAL_GROUP_DIR="$(ivy_local_group_dir "$GROUP_ID" || true)"
  if [ -n "$IVY_LOCAL_GROUP_DIR" ] && [ -d "$IVY_LOCAL_GROUP_DIR" ]; then
    IVY_LOCAL_COUNT=$(find "$IVY_LOCAL_GROUP_DIR" -mindepth 1 -maxdepth 2 -type d 2>/dev/null | wc -l | tr -d ' ')
    warn "Default Ivy local artifacts detected under $IVY_LOCAL_GROUP_DIR"
    echo "  These can override or conflict with isolated-cache publishLocal flows"
    echo "  Consider cleaning only the affected artifact versions before cross-repo validation"
    echo "  Entries detected: $IVY_LOCAL_COUNT"
  else
    ok "No workspace artifacts found under ~/.ivy2/local for ${GROUP_ID}"
  fi
fi

echo ""

# ─── 8. Resolver and Remote Cache Risks ────────────────────────────────────────

echo "--- Resolver and Remote Cache Risks ---"

BUILD_SCAN_FILES=()
for dir in "${SERVICES[@]}"; do
  [ -f "$dir/build.sbt" ] && BUILD_SCAN_FILES+=("$dir/build.sbt")
  for file in "$dir"/project/*.scala; do
    [ -f "$file" ] && BUILD_SCAN_FILES+=("$file")
  done
done

INTERNAL_HOSTS=$(grep -hE 'https://[^" )]+' "${BUILD_SCAN_FILES[@]}" 2>/dev/null | sed -E 's#.*https://([^/" )]+).*#\1#' | sort -u || true)
if [ -n "$INTERNAL_HOSTS" ]; then
  echo "  Resolver hosts detected:"
  echo "$INTERNAL_HOSTS" | sed 's/^/    - /'
  if [ ! -f "$HOME/.ivy2/.credentials" ]; then
    warn "Remote resolver hosts are configured but ~/.ivy2/.credentials is missing"
    echo "  Published artifact resolution may fail even when local builds partly work"
  fi
else
  ok "No explicit HTTPS resolver hosts detected in local build files"
fi

ROOT_PATH_REPOS=$(grep -l 'rootPaths[[:space:]]*+=' "${BUILD_SCAN_FILES[@]}" 2>/dev/null | sed 's#/build.sbt##' | sed 's#/project/.*##' | xargs -n1 basename 2>/dev/null | sort -u || true)
REMOTE_CACHE_REPOS=$(grep -lE 'pushRemoteCache|pullRemoteCache|RemoteCache' "${BUILD_SCAN_FILES[@]}" 2>/dev/null | sed 's#/build.sbt##' | sed 's#/project/.*##' | xargs -n1 basename 2>/dev/null | sort -u || true)
if [ -n "$ROOT_PATH_REPOS" ]; then
  echo "  rootPaths detected in:"
  echo "$ROOT_PATH_REPOS" | sed 's/^/    - /'
fi
if [ -n "$REMOTE_CACHE_REPOS" ]; then
  echo "  remote-cache settings detected in:"
  echo "$REMOTE_CACHE_REPOS" | sed 's/^/    - /'
fi
if [ -n "$ROOT_PATH_REPOS" ] && [ -n "$REMOTE_CACHE_REPOS" ]; then
  if { [ -n "$IVY_LOCAL_GROUP_DIR" ] && [ -d "$IVY_LOCAL_GROUP_DIR" ]; } || { [ -n "$GROUP_ID" ] && [ -d "$LOCAL_DIR/$GROUP_ID" ]; }; then
    warn "Potential root-path mapping conflict risk detected"
    echo "  Local published artifacts plus rootPaths/remote-cache settings can trigger 'cannot be mapped using the root paths' failures"
    echo "  Prefer isolated publishLocal flows and clean stale default Ivy local artifacts before validation"
  fi
fi

echo ""

# ─── Summary ──────────────────────────────────────────────────────────────────

echo "=== Pre-flight Complete ($WARN_COUNT warning(s)) ==="
