#!/usr/bin/env bash
# discover_deps.sh — Discover cross-repo dependencies for any SBT service
#
# Usage: discover_deps.sh <service-dir>
#
# Scans build.sbt and project/*.scala for:
#   - All ProjectRef declarations (cross-repo source dependencies)
#   - Published workspace artifact dependencies matching GROUP_ID
#   - Transitive workspace artifacts via sbt dependencyTree
#   - Version variables and their values
#   - Build configuration (sbt_env, subprojects, Scala version)
#   - Dirty workspace repos that may need local publishing
#
# Fully generic — no repo names are hardcoded.

set -uo pipefail

SERVICE_DIR="${1:?Usage: discover_deps.sh <service-dir>}"
SERVICE_NAME="$(basename "$SERVICE_DIR")"
WORKSPACE_DIR="${WORKSPACE_DIR:-$(dirname "$SERVICE_DIR")}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

if [ ! -f "$SERVICE_DIR/build.sbt" ]; then
  echo "ERROR: No build.sbt found in $SERVICE_DIR" >&2
  exit 2
fi

BUILD_FILES=()
while IFS= read -r _bf; do
  [ -f "$_bf" ] && BUILD_FILES+=("$_bf")
done <<< "$(collect_build_files "$SERVICE_DIR")"

source "$SCRIPT_DIR/resolve_projects.sh"

_DIRECT_ARTS=$(mktemp)
_TRANS_FILE=$(mktemp)
_ALL_ARTS=$(mktemp)
_WS_ARTIFACTS=$(mktemp)
_SBT_RAW=$(mktemp)
trap 'rm -f "$_DIRECT_ARTS" "$_TRANS_FILE" "$_ALL_ARTS" "$_WS_ARTIFACTS" "$_SBT_RAW"' EXIT

_strip_scala_suffix() {
  echo "$1" | sed -E 's/_[0-9]+\.[0-9]+$//'
}

_has_workspace_artifact() {
  awk -F '\t' -v base="$1" '$1 == base { found=1; exit } END { exit(found ? 0 : 1) }' "$_WS_ARTIFACTS"
}

_collect_workspace_artifacts() {
  : > "$_WS_ARTIFACTS"
  for _svc in "${SERVICES[@]}"; do
    _repo=$(basename "$_svc")
    _scan_files=("$_svc/build.sbt")
    for _f in "$_svc"/project/*.scala; do
      [ -f "$_f" ] && _scan_files+=("$_f")
    done
    _names=$(grep -hE '(^|[^[:alnum:]_])name[[:space:]]*:=[[:space:]]*"[^"]+"' "${_scan_files[@]}" 2>/dev/null \
      | sed 's/.*name[[:space:]]*:=[[:space:]]*"\([^"]*\)".*/\1/' \
      | sort -u || true)
    if [ -n "$_names" ]; then
      while IFS= read -r _name; do
        [ -n "$_name" ] && printf '%s\t%s\t%s\n' "$_name" "$_repo" "$_svc" >> "$_WS_ARTIFACTS"
      done <<EOF
$_names
EOF
    else
      printf '%s\t%s\t%s\n' "$_repo" "$_repo" "$_svc" >> "$_WS_ARTIFACTS"
    fi
  done
  sort -u "$_WS_ARTIFACTS" -o "$_WS_ARTIFACTS"
}

_JAVA_HOME="$(resolve_java_home_for_version "$JAVA_VERSION")"
_SBT_OK=false
if [ -n "$_JAVA_HOME" ] && command -v sbt >/dev/null 2>&1; then
  _SBT_OK=true
fi

_collect_workspace_artifacts

# ── Static fallback for Scala/project versions ──────────────────────────────
SCALA_VERSION="$(extract_scala_version "$SERVICE_DIR")"
PROJECT_VERSION="$(extract_project_version "$SERVICE_DIR/build.sbt")"

# ── Single batched SBT invocation for all evaluated data ─────────────────────
# Runs: show scalaVersion, show version, show libraryDependencies, Compile/dependencyTree
# in one SBT session to avoid repeated startup overhead.

_DEPS_AVAILABLE=false
_TREE_AVAILABLE=false

if [ "$_SBT_OK" = true ]; then
  if bash "$SCRIPT_DIR/run_sbt.sh" "$SERVICE_DIR" --workspace-dir "$WORKSPACE_DIR" -- \
       "show scalaVersion" "show version" "show libraryDependencies" "Compile/dependencyTree" \
       > "$_SBT_RAW" 2>&1; then
    _SBT_RAN=true
  else
    # Even on partial failure, some output may be usable
    _SBT_RAN=true
  fi

  if [ "$_SBT_RAN" = true ]; then
    # Extract metadata: scalaVersion and version appear as bare version lines
    _META_INFO=$(grep '^\[info\] ' "$_SBT_RAW" | sed 's/^\[info\] //' \
      | grep -v '^welcome to sbt ' \
      | grep -v '^loading ' \
      | grep -v '^set current project' \
      | grep -v '^Installing the ' \
      | grep -v '^resolving key references' \
      | grep -v '^done compiling' || true)

    # scalaVersion is the first bare version-like line (e.g. 2.13.12)
    _SCALA_EVAL=$(echo "$_META_INFO" | grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' | head -1 || true)
    [ -n "$_SCALA_EVAL" ] && SCALA_VERSION="$_SCALA_EVAL"

    # project version: find lines that look like version output but aren't scala version
    _VERSION_CANDIDATES=$(echo "$_META_INFO" | grep -E '^[0-9]+\.' | grep -v "^${SCALA_VERSION}$" || true)
    _VERSION_EVAL=$(echo "$_VERSION_CANDIDATES" | head -1 | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' || true)
    [ -n "$_VERSION_EVAL" ] && PROJECT_VERSION=$(echo "$_VERSION_EVAL" | sed 's/^"//; s/"$//' || true)

    # libraryDependencies: lines with [info] * prefix
    if grep -q '^\[info\] \* ' "$_SBT_RAW"; then
      _DEPS_AVAILABLE=true
    fi

    # dependencyTree: lines with group_id in tree format
    if [ -n "$GROUP_ID" ] && grep -q "$GROUP_ID" "$_SBT_RAW"; then
      _TREE_AVAILABLE=true
    fi
  fi
fi

_SCALA_SUFFIX="$(scala_binary_suffix "$SCALA_VERSION")"

echo "=== Dependency Discovery for $SERVICE_NAME ==="
echo ""

# --- Cross-repo ProjectRef dependencies (dev-mode source deps) ---
echo "--- ProjectRef (cross-repo source dependencies) ---"
PROJ_REFS="$(extract_project_refs "$SERVICE_DIR/build.sbt")"
if [ -n "$PROJ_REFS" ]; then
  echo "$PROJ_REFS" | while IFS= read -r line; do
    REF_PATH=$(echo "$line" | sed 's/.*file("\([^"]*\)".*/\1/')
    REF_NAME=$(echo "$line" | sed 's/.*,[ ]*"\([^"]*\)".*/\1/')
    echo "  $REF_NAME -> $REF_PATH"
  done | sort -u
else
  echo "  (none)"
fi

echo ""

# --- Published artifact dependencies ($GROUP_ID) ---
echo "--- Published workspace artifacts (${GROUP_ID:-group unavailable}) ---"

: > "$_DIRECT_ARTS"
if [ -z "$GROUP_ID" ]; then
  echo "  (skipped — no group ID detected; set .group_id in .sbt-workspace.conf if organization cannot be inferred)"
elif [ "$_DEPS_AVAILABLE" = true ]; then
  _SHOW_FILTERED=$(mktemp)
  trap 'rm -f "$_DIRECT_ARTS" "$_TRANS_FILE" "$_ALL_ARTS" "$_WS_ARTIFACTS" "$_SBT_RAW" "$_SHOW_FILTERED"' EXIT

  grep '^\[info\] \* ' "$_SBT_RAW" \
    | sed 's/^\[info\] \* //' \
    | awk -F: -v group="$GROUP_ID" '
        (($1 == group) || (index($1, group ".") == 1)) && NF >= 3 {
          art = $2
          ver = $3
          conf = ""
          if (NF >= 4) conf = $4
          gsub(/^ +| +$/, "", art)
          gsub(/^ +| +$/, "", ver)
          gsub(/^ +| +$/, "", conf)
          if (art != "" && ver != "") print art "\t" ver "\t" conf
        }
      ' \
    | sort -u > "$_SHOW_FILTERED"

  _DIRECT_FOUND=0
  while IFS=$'\t' read -r _art _ver _conf; do
    [ -z "$_art" ] && continue
    _art_base=$(_strip_scala_suffix "$_art")
    _has_workspace_artifact "$_art_base" || continue
    if [ -n "$_conf" ]; then
      echo "  $_art = $_ver [$_conf]"
    else
      echo "  $_art = $_ver"
    fi
    printf '%s\t%s\n' "$_art" "$_ver" >> "$_DIRECT_ARTS"
    _DIRECT_FOUND=1
  done < "$_SHOW_FILTERED"

  if [ "$_DIRECT_FOUND" -eq 0 ]; then
    echo "  (none found matching local workspace artifacts)"
  fi
  rm -f "$_SHOW_FILTERED"
elif [ "$_SBT_OK" = true ]; then
  _errs=$(grep '\[error\]' "$_SBT_RAW" | head -5)
  echo "  (sbt libraryDependencies failed — resolution error or missing deps)"
  [ -n "$_errs" ] && echo "$_errs" | sed 's/^/  /'
else
  if [ -z "$_JAVA_HOME" ]; then
    echo "  (skipped — Java $JAVA_VERSION not found; run sbt_status.sh --workspace first)"
  else
    echo "  (skipped — sbt not found on PATH)"
  fi
fi

echo ""

# --- Transitive workspace artifacts (via sbt dependencyTree) ---
echo "--- Transitive workspace artifacts (via sbt dependencyTree) ---"

_TRANS_FOUND=0
: > "$_TRANS_FILE"

if [ -z "$GROUP_ID" ]; then
  echo "  (skipped — no group ID detected; set .group_id in .sbt-workspace.conf if organization cannot be inferred)"
elif [ "$_TREE_AVAILABLE" = true ]; then
  _TREE_FILTERED=$(mktemp)
  trap 'rm -f "$_DIRECT_ARTS" "$_TRANS_FILE" "$_ALL_ARTS" "$_WS_ARTIFACTS" "$_SBT_RAW" "$_TREE_FILTERED"' EXIT

  grep "$GROUP_ID" "$_SBT_RAW" \
    | grep -v "(ev" \
    | sed 's/\[info\] *//' \
    | sed 's/^[| +-]*//' \
    | sed 's/ \[S\]$//' \
    | awk -F: -v group="$GROUP_ID" -v sname="$SERVICE_NAME" '
        (($1 == group) || (index($1, group ".") == 1)) && NF >= 3 {
          art = $2; ver = $3
          gsub(/^ +| +$/, "", art)
          gsub(/^ +| +$/, "", ver)
          gsub(/ .*/, "", ver)
          if (art ~ sname && ver ~ /SNAPSHOT/) next
          if (art != "" && ver != "" && ver !~ /\.\./) print art "\t" ver
        }
      ' \
    | sort -u > "$_TREE_FILTERED"

  while IFS=$'\t' read -r _tart _tver; do
    [ -z "$_tart" ] && continue
    _tart_base=$(_strip_scala_suffix "$_tart")
    _has_workspace_artifact "$_tart_base" || continue
    _skip=false
    while IFS=$'\t' read -r _dart _dver; do
      _dart_base=$(_strip_scala_suffix "$_dart")
      if [ "$_tart_base" = "$_dart_base" ] || [ "$_tart" = "$_dart" ]; then
        _skip=true
        break
      fi
    done < "$_DIRECT_ARTS"
    [ "$_skip" = true ] && continue
    echo "  $_tart = $_tver"
    printf '%s\t%s\n' "$_tart" "$_tver" >> "$_TRANS_FILE"
    _TRANS_FOUND=1
  done < "$_TREE_FILTERED"
  rm -f "$_TREE_FILTERED"
elif [ "$_SBT_OK" = true ]; then
  _errs=$(grep '\[error\]' "$_SBT_RAW" | head -5)
  echo "  (sbt dependencyTree failed — resolution error or missing deps)"
  [ -n "$_errs" ] && echo "$_errs" | sed 's/^/  /'
else
  if [ -z "$_JAVA_HOME" ]; then
    echo "  (skipped — configured Java version not found; run sbt_status.sh --workspace first)"
  else
    echo "  (skipped — sbt not found on PATH)"
  fi
fi

if [ "$_TRANS_FOUND" -eq 0 ] && [ "$_SBT_OK" = true ] && [ "$_TREE_AVAILABLE" != true ]; then
  : # already printed error above
elif [ "$_TRANS_FOUND" -eq 0 ] && [ "$_TREE_AVAILABLE" = true ]; then
  echo "  (none found matching local workspace artifacts)"
fi

echo ""

# --- Dirty workspace repos needing local publish ---
echo "--- Local publish check (dirty repos vs required versions) ---"

_PUBLISH_WARNINGS=0

# Build a combined list of all required artifacts (direct + transitive)
cat "$_DIRECT_ARTS" > "$_ALL_ARTS"
[ -s "$_TRANS_FILE" ] && cat "$_TRANS_FILE" >> "$_ALL_ARTS"
sort -u "$_ALL_ARTS" -o "$_ALL_ARTS"

# For each workspace repo with local changes, check if it produces an artifact we depend on
_WARNED_FILE=$(mktemp)
for _repo_dir in "${SERVICES[@]}"; do
  [ -d "$_repo_dir/.git" ] || continue

  _repo_name=$(basename "$_repo_dir")

  # Check if repo has uncommitted changes
  _dirty=""
  if [ -n "$(git -C "$_repo_dir" status --porcelain 2>/dev/null)" ]; then
    _dirty=true
  fi
  [ -z "$_dirty" ] && continue

  # Check if this repo produces any artifact we need (direct or transitive)
  while IFS=$'\t' read -r _need_art _need_ver; do
    _need_base=$(_strip_scala_suffix "$_need_art")
    while IFS=$'\t' read -r _ws_art _ws_repo _ws_path; do
      [ "$_ws_path" = "$_repo_dir" ] || continue
      [ "$_ws_art" = "$_need_base" ] || continue
      _warn_key="${_repo_name}@${_need_ver}"
      if grep -qF "$_warn_key" "$_WARNED_FILE" 2>/dev/null; then
        break
      fi
      echo "  WARN: '$_repo_name' has local changes and produces required artifact '$_ws_art' at version $_need_ver"
      echo "        -> publishLocal with ARTIFACT_VERSION=$_need_ver, then clear caches"
      echo "$_warn_key" >> "$_WARNED_FILE"
      _PUBLISH_WARNINGS=$((_PUBLISH_WARNINGS + 1))
      break
    done < "$_WS_ARTIFACTS"
  done < "$_ALL_ARTS"
done
rm -f "$_WARNED_FILE"

if [ "$_PUBLISH_WARNINGS" -eq 0 ]; then
  echo "  OK: no dirty workspace repos match required dependencies"
fi

echo ""

# --- Version variables ---
echo "--- Version variables ---"
grep -hE '(val|lazy val) [a-zA-Z_]*[Vv]ersion[^=]*=' "${BUILD_FILES[@]}" 2>/dev/null | while IFS= read -r line; do
  VAR=$(echo "$line" | grep -oE '(val|lazy val) [a-zA-Z_]+' | sed 's/lazy val //' | sed 's/val //')
  VAL=$(echo "$line" | grep -oE '"[^"]*"' | head -1 | tr -d '"')
  [ -n "$VAR" ] && echo "  $VAR = ${VAL:-<computed>}"
done || echo "  (none)"

echo ""

# --- Build configuration ---
echo "--- Build Configuration ---"

# sbt_env support
if grep -q 'System.getProperty.*sbt_env' "$SERVICE_DIR/build.sbt" 2>/dev/null; then
  echo "  sbt_env: supported (JVM system property via -Dsbt_env=dev)"
else
  echo "  sbt_env: not used (always resolves from published artifacts)"
fi

# Scala version
echo "  scala: ${SCALA_VERSION:-unknown}"

# Artifact version
echo "  version: $(echo "${PROJECT_VERSION:-unknown}" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"

# Multi-project detection: look for (project in file(...)) or Project(id=...) patterns
SUBPROJECTS=$(grep -oE '(lazy val [a-zA-Z_`-]+)\s*=\s*(if\s*\(isDev\)\s*)?(project\b|\(project|Project\()' "$SERVICE_DIR/build.sbt" 2>/dev/null | grep -oE 'lazy val [a-zA-Z_`-]+' | sed 's/lazy val //' | sort -u || true)
SP_COUNT=$(echo "$SUBPROJECTS" | grep -c '[a-zA-Z]' || true)
if [ "$SP_COUNT" -gt 1 ]; then
  echo "  multi-project: yes ($SP_COUNT subprojects)"
  echo "  subprojects:"
  echo "$SUBPROJECTS" | sed 's/^/    - /'
elif [ "$SP_COUNT" -eq 1 ]; then
  echo "  multi-project: no (single project: $SUBPROJECTS)"
else
  echo "  multi-project: no"
fi

echo ""
echo "=== End Discovery ==="
