#!/usr/bin/env bash
# resolve_projects.sh — Shared helper to discover SBT projects in a workspace
#
# Sources into other scripts. Sets the SERVICES array with absolute paths
# to all SBT project directories.
#
# Discovery order:
#   1. Auto-scan: all immediate subdirectories of WORKSPACE_DIR with build.sbt
#   2. Config merge: if <workspace>/.sbt-workspace.conf exists, add/override with
#      explicit paths from the config file
#
# Config file format (.sbt-workspace.conf):
#   # Lines starting with # are comments
#   # Blank lines are ignored
#   # Format: project-name=/absolute/path/to/project
#   shared-models=/some/other/path/shared-models
#   platform-commons=/another/place/platform-commons
#
#   # Optional settings (key=value where key starts with a dot):
#   .group_id=com.acme
#   .java_version=17
#
# After sourcing, the following are set:
#   SERVICES — array of absolute paths to directories containing build.sbt
#   GROUP_ID — Maven group ID for artifact filtering (auto-detected unless overridden)
#   JAVA_VERSION — requested Java major version for SBT commands (default: 17)
#
# Usage (from another script):
#   WORKSPACE_DIR="/path/to/workspace"
#   SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
#   source "$SCRIPT_DIR/resolve_projects.sh"
#   # SERVICES array is now populated
#
# Compatible with bash 3.2+ (macOS default).

# Requires WORKSPACE_DIR to be set by the caller
if [ -z "${WORKSPACE_DIR:-}" ]; then
  echo "ERROR: WORKSPACE_DIR must be set before sourcing resolve_projects.sh" >&2
  return 1 2>/dev/null || exit 1
fi

_WORKSPACE_CONF="$WORKSPACE_DIR/.sbt-workspace.conf"

# Optional settings (overridable via config or environment)
GROUP_ID="${GROUP_ID:-}"
JAVA_VERSION="${JAVA_VERSION:-17}"

# Parallel arrays for name -> path mapping (bash 3.2 compatible, no declare -A)
_PROJ_NAMES=()
_PROJ_PATHS=()

# Helper: add or replace a project entry by name
_add_project() {
  local name="$1" path="$2" i
  for i in "${!_PROJ_NAMES[@]}"; do
    if [ "${_PROJ_NAMES[$i]}" = "$name" ]; then
      _PROJ_PATHS[$i]="$path"
      return
    fi
  done
  _PROJ_NAMES+=("$name")
  _PROJ_PATHS+=("$path")
}

# Helper: infer GROUP_ID from workspace organization settings
_infer_group_id() {
  local _svc _scan_files _f _org
  for _svc in "${_PROJ_PATHS[@]}"; do
    _scan_files=("$_svc/build.sbt")
    for _f in "$_svc"/project/*.scala; do
      [ -f "$_f" ] && _scan_files+=("$_f")
    done
    _org=$(grep -hE '(^|[^[:alnum:]_])((ThisBuild[[:space:]]*/[[:space:]]*)?organization)[[:space:]]*:=[[:space:]]*"[^"]+"' "${_scan_files[@]}" 2>/dev/null \
      | sed 's/.*organization[[:space:]]*:=[[:space:]]*"\([^"]*\)".*/\1/' \
      | head -1 || true)
    if [ -n "$_org" ]; then
      echo "$_org"
      return 0
    fi
  done
  return 1
}

# --- Step 1: Auto-scan workspace children ---
for dir in "$WORKSPACE_DIR"/*/; do
  [ -f "$dir/build.sbt" ] || continue
  _name=$(basename "$dir")
  _abs=$(cd "$dir" && pwd)
  _add_project "$_name" "$_abs"
done

# --- Step 2: Merge config file overrides ---
if [ -f "$_WORKSPACE_CONF" ]; then
  while IFS= read -r _line; do
    # Skip comments and blank lines
    case "$_line" in
      '#'*|'') continue ;;
    esac
    # Also skip lines that are only whitespace
    _trimmed="$(echo "$_line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [ -z "$_trimmed" ] && continue

    # Parse name=value
    _name="${_trimmed%%=*}"
    _value="${_trimmed#*=}"

    # Trim whitespace from name
    _name="$(echo "$_name" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

    # Handle settings (keys starting with .)
    if [[ "$_name" == .* ]]; then
      _value="$(echo "$_value" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
      case "$_name" in
        .group_id) GROUP_ID="$_value" ;;
        .java_version) JAVA_VERSION="$_value" ;;
        *) echo "WARN: Unknown setting '$_name' in .sbt-workspace.conf — skipping" >&2 ;;
      esac
      continue
    fi

    # It's a project path entry
    _path="$_value"

    # Trim whitespace from path
    _path="$(echo "$_path" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

    # Expand ~ to $HOME
    _path="${_path/#\~/$HOME}"

    if [ -z "$_name" ] || [ -z "$_path" ]; then
      echo "WARN: Skipping malformed config line: $_line" >&2
      continue
    fi

    if [ ! -f "$_path/build.sbt" ]; then
      echo "WARN: No build.sbt found at $_path (from .sbt-workspace.conf entry '$_name') — skipping" >&2
      continue
    fi

    _abs=$(cd "$_path" && pwd)
    _add_project "$_name" "$_abs"
  done < "$_WORKSPACE_CONF"
fi

# --- Build final SERVICES array (sorted by name) ---
SERVICES=()
_sorted_indices=$(
  for i in "${!_PROJ_NAMES[@]}"; do
    echo "$i ${_PROJ_NAMES[$i]}"
  done | sort -k2 | awk '{print $1}'
)
for i in $_sorted_indices; do
  SERVICES+=("${_PROJ_PATHS[$i]}")
done

# Infer GROUP_ID if not set
if [ -z "$GROUP_ID" ]; then
  GROUP_ID="$(_infer_group_id || true)"
fi

# Clean up internals
unset _PROJ_NAMES _PROJ_PATHS _WORKSPACE_CONF _name _path _abs _line _trimmed _sorted_indices _value
unset _svc _scan_files _f _org
unset -f _add_project
unset -f _infer_group_id
