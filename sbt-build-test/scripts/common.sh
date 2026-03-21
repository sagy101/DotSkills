#!/usr/bin/env bash

SBT_BUILD_CACHE_ROOT="${SBT_BUILD_CACHE_ROOT:-$HOME/.sbt-build-cache}"
SBT_BUILD_LOG_ROOT="${SBT_BUILD_LOG_ROOT:-$SBT_BUILD_CACHE_ROOT/logs}"

resolve_java_home_for_version() {
  local _requested_version _java_home _java_ver
  _requested_version="${1:-17}"
  _java_home="${JAVA_HOME:-}"
  if [ -z "$_java_home" ]; then
    _java_home=$(/usr/libexec/java_home -v "$_requested_version" 2>/dev/null || true)
  fi
  if [ -z "$_java_home" ] && command -v java >/dev/null 2>&1; then
    _java_ver=$(java -version 2>&1 | head -1 || true)
    if echo "$_java_ver" | grep -q "\"${_requested_version}\." 2>/dev/null; then
      _java_home="$(dirname "$(dirname "$(command -v java)")")"
    fi
  fi
  echo "$_java_home"
}

ensure_sbt_skill_dirs() {
  mkdir -p "$SBT_BUILD_CACHE_ROOT" "$SBT_BUILD_CACHE_ROOT/locks" \
    "$SBT_BUILD_CACHE_ROOT/coursier" "$SBT_BUILD_CACHE_ROOT/boot" \
    "$SBT_BUILD_CACHE_ROOT/global" "$SBT_BUILD_LOG_ROOT"
}

sanitize_skill_key() {
  printf '%s' "$1" | sed 's/[^[:alnum:]._-]/_/g'
}

skill_timestamp() {
  date '+%Y%m%d-%H%M%S'
}

skill_log_file() {
  local _repo_root _label _key _ts
  _repo_root="$1"
  _label="${2:-run}"
  ensure_sbt_skill_dirs
  _key="$(sanitize_skill_key "$_repo_root")"
  _ts="$(skill_timestamp)"
  echo "$SBT_BUILD_LOG_ROOT/${_key}.${_label}.${_ts}.log"
}

build_workspace_graph_json() {
  local _script_dir _workspace_dir _group_id _output_file _services_file _rc
  _script_dir="$1"
  _workspace_dir="$2"
  _group_id="$3"
  _output_file="$4"
  shift 4
  _services_file="$(mktemp)"
  printf '%s\n' "$@" > "$_services_file"
  if python3 "$_script_dir/workspace_graph.py" --workspace-dir "$_workspace_dir" --services-file "$_services_file" --group-id "$_group_id" > "$_output_file"; then
    _rc=0
  else
    _rc=$?
  fi
  rm -f "$_services_file"
  return "$_rc"
}

service_dir_for_repo_name() {
  local _repo_name _svc
  _repo_name="$1"
  shift
  for _svc in "$@"; do
    if [ "$(basename "$_svc")" = "$_repo_name" ]; then
      echo "$_svc"
      return 0
    fi
  done
  return 1
}

infer_artifact_name_from_repo() {
  local _project_dir
  _project_dir="$1"
  grep -hE '(^|[^[:alnum:]_])name[[:space:]]*:=[[:space:]]*"[^"]+"' "$_project_dir/build.sbt" "$_project_dir"/project/*.scala 2>/dev/null | sed 's/.*name[[:space:]]*:=[[:space:]]*"\([^"]*\)".*/\1/' | head -1 || true
}

find_repo_root_for_path() {
  local _path
  _path="$1"
  if [ -f "$_path/build.sbt" ]; then
    echo "$_path"
    return 0
  fi
  if [ ! -d "$_path" ]; then
    _path="$(dirname "$_path")"
  fi
  _path="$(cd "$_path" 2>/dev/null && pwd || true)"
  while [ -n "$_path" ] && [ "$_path" != "/" ]; do
    if [ -f "$_path/build.sbt" ]; then
      echo "$_path"
      return 0
    fi
    _path="$(dirname "$_path")"
  done
  return 1
}

ivy_local_group_dir() {
  local _group_id
  _group_id="$1"
  [ -n "$_group_id" ] || return 1
  echo "$HOME/.ivy2/local/$_group_id"
}

isolated_cache_artifact_dir() {
  local _group_id _artifact_name
  _group_id="$1"
  _artifact_name="$2"
  [ -n "$_group_id" ] || return 1
  [ -n "$_artifact_name" ] || return 1
  echo "$SBT_BUILD_CACHE_ROOT/cache/$_group_id/$_artifact_name"
}

isolated_local_artifact_dir() {
  local _group_id _artifact_name
  _group_id="$1"
  _artifact_name="$2"
  [ -n "$_group_id" ] || return 1
  [ -n "$_artifact_name" ] || return 1
  echo "$SBT_BUILD_CACHE_ROOT/local/$_group_id/$_artifact_name"
}

coursier_cache_root() {
  echo "$SBT_BUILD_CACHE_ROOT/coursier"
}

sbt_boot_dir() {
  echo "$SBT_BUILD_CACHE_ROOT/boot"
}

sbt_global_base() {
  echo "$SBT_BUILD_CACHE_ROOT/global"
}

test_activity_lock_file() {
  local _repo_root _key
  _repo_root="$1"
  ensure_sbt_skill_dirs
  _key="$(sanitize_skill_key "$_repo_root")"
  echo "$SBT_BUILD_CACHE_ROOT/locks/${_key}.sbt-test.lock"
}

# ── Shared extraction helpers (used by multiple scripts) ─────────────────────

# Collect build.sbt + project/*.scala into a newline-separated list.
# Usage: _files=$(collect_build_files "/path/to/project")
#        while IFS= read -r f; do ... done <<< "$_files"
collect_build_files() {
  local _dir="$1"
  echo "$_dir/build.sbt"
  for _f in "$_dir"/project/*.scala; do
    [ -f "$_f" ] && echo "$_f"
  done
}

# Get all artifact names (name := "...") from a project directory.
# Returns one name per line, sorted and unique.
get_all_artifact_names() {
  local _dir="$1"
  grep -hE '(^|[^[:alnum:]_])name[[:space:]]*:=[[:space:]]*"[^"]+"' \
    "$_dir/build.sbt" "$_dir"/project/*.scala 2>/dev/null \
    | sed 's/.*name[[:space:]]*:=[[:space:]]*"\([^"]*\)".*/\1/' \
    | sort -u || true
}

# Get the primary (first) artifact name from a project directory.
get_primary_artifact_name() {
  local _dir="$1"
  grep -hE '(^|[^[:alnum:]_])name[[:space:]]*:=[[:space:]]*"[^"]+"' \
    "$_dir/build.sbt" "$_dir"/project/*.scala 2>/dev/null \
    | sed 's/.*name[[:space:]]*:=[[:space:]]*"\([^"]*\)".*/\1/' \
    | head -1 || true
}

# Extract static scalaVersion from build files. Returns e.g. "2.13.14".
extract_scala_version() {
  local _dir="$1"
  grep -hoE 'scalaVersion[^"]*"[0-9]+\.[0-9]+\.[0-9]+"' \
    "$_dir/build.sbt" "$_dir"/project/*.scala 2>/dev/null \
    | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true
}

# Convert a full Scala version to its binary suffix (e.g. "2.13.14" -> "_2.13").
scala_binary_suffix() {
  local _version="$1"
  if [ -n "$_version" ]; then
    echo "_$(echo "$_version" | grep -oE '^[0-9]+\.[0-9]+')"
  fi
}

# Extract project version from build.sbt (static, no SBT evaluation).
extract_project_version() {
  local _file="$1"
  grep -hE '^version\b|ThisBuild.*version' "$_file" 2>/dev/null \
    | grep -oE '"[0-9]+\.[0-9]+[^"]*"' | head -1 | tr -d '"' || true
}

# Resolve the workspace directory from a project directory.
resolve_workspace_dir() {
  local _workspace_dir="$1" _project_dir="$2"
  if [ -z "$_workspace_dir" ]; then
    _workspace_dir="$(dirname "$_project_dir")"
  fi
  cd "$_workspace_dir" && pwd
}

# Look up the version of a specific artifact in a set of build files.
# Usage: lookup_artifact_version "artifact-name" file1 file2 ...
# Searches for %% "artifact-name" % "version" patterns and version variable references.
lookup_artifact_version() {
  local _art_name="$1"
  shift
  local _bf _ver _ver_var

  for _bf in "$@"; do
    [ -f "$_bf" ] || continue
    # Direct version literal: %% "artifact-name" % "1.2.3"
    _ver=$(grep -hE "%%[^%]*\"${_art_name}\"" "$_bf" 2>/dev/null \
      | grep -oE '%[^%]*"[0-9]+\.[0-9]+[^"]*"' | tail -1 \
      | grep -oE '"[0-9]+[^"]*"' | tr -d '"' || true)
    if [ -n "$_ver" ]; then
      echo "$_ver"
      return 0
    fi
    # Version variable reference: %% "artifact-name" % someVersionVar
    _ver_var=$(grep -hE "%%[^\"]*\"${_art_name}\"[^\"]*%[^\"]*[a-zA-Z_]+" "$_bf" 2>/dev/null \
      | grep -oE '%[[:space:]]*[a-zA-Z_]+' | tail -1 \
      | sed 's/%[[:space:]]*//' || true)
    if [ -n "$_ver_var" ]; then
      _ver=$(grep -hE "(val|lazy val)[[:space:]]+${_ver_var}[[:space:]]*=" "$@" 2>/dev/null \
        | grep -oE '"[0-9]+[^"]*"' | tr -d '"' | head -1 || true)
      if [ -n "$_ver" ]; then
        echo "$_ver"
        return 0
      fi
    fi
  done
  return 1
}

# Extract ProjectRef entries from a build.sbt file.
# Returns lines like: ProjectRef(file("../shared-models"), "shared-models"
extract_project_refs() {
  local _build_sbt="$1"
  grep -oE 'ProjectRef\(file\("[^"]+"\),\s*"[^"]+"' "$_build_sbt" 2>/dev/null || true
}
