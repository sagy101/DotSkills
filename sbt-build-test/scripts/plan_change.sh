#!/usr/bin/env bash

set -euo pipefail

usage() {
  local _rc
  _rc="${1:-2}"
  echo "Usage: plan_change.sh <changed-repo-or-path> <target-repo-or-path> [--workspace-dir <workspace-dir>] [--json]" >&2
  exit "$_rc"
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage 0
fi

[ "$#" -ge 2 ] || usage
CHANGED_SPEC="$1"
TARGET_SPEC="$2"
shift 2
WORKSPACE_DIR=""
OUTPUT_JSON=false
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --workspace-dir)
      [ "$#" -ge 2 ] || usage
      WORKSPACE_DIR="$2"
      shift 2
      ;;
    --json)
      OUTPUT_JSON=true
      shift
      ;;
    *)
      usage
      ;;
  esac
done

if [ -z "$WORKSPACE_DIR" ]; then
  if [ -d "$TARGET_SPEC" ] || [ -f "$TARGET_SPEC" ]; then
    TARGET_REPO_ROOT="$(find_repo_root_for_path "$TARGET_SPEC" || true)"
    [ -n "$TARGET_REPO_ROOT" ] || usage
    WORKSPACE_DIR="$(dirname "$TARGET_REPO_ROOT")"
  elif [ -d "$CHANGED_SPEC" ] || [ -f "$CHANGED_SPEC" ]; then
    CHANGED_REPO_ROOT="$(find_repo_root_for_path "$CHANGED_SPEC" || true)"
    [ -n "$CHANGED_REPO_ROOT" ] || usage
    WORKSPACE_DIR="$(dirname "$CHANGED_REPO_ROOT")"
  else
    usage
  fi
fi

WORKSPACE_DIR="$(cd "$WORKSPACE_DIR" && pwd)"
source "$SCRIPT_DIR/resolve_projects.sh"

[ ${#SERVICES[@]} -gt 0 ] || { echo "ERROR: No SBT projects found in $WORKSPACE_DIR" >&2; exit 2; }

_GRAPH_JSON=$(mktemp)
trap 'rm -f "$_GRAPH_JSON"' EXIT
build_workspace_graph_json "$SCRIPT_DIR" "$WORKSPACE_DIR" "$GROUP_ID" "$_GRAPH_JSON" "${SERVICES[@]}"

python3 - "$CHANGED_SPEC" "$TARGET_SPEC" "$OUTPUT_JSON" "$_GRAPH_JSON" <<'PY'
import json
import sys
from collections import deque
from pathlib import Path

changed_spec = sys.argv[1]
target_spec = sys.argv[2]
output_json = sys.argv[3].lower() == "true"
graph = json.loads(Path(sys.argv[4]).read_text())

repos = graph["repos"]
repo_by_name = {repo["name"]: repo for repo in repos}
repo_by_path = {str(Path(repo["path"]).resolve()): repo for repo in repos}

deps = {repo["name"]: set(repo.get("dependencies", [])) for repo in repos}
dependents = {repo["name"]: set(repo.get("dependents", [])) for repo in repos}
publish_order = graph.get("publish_order", [])

def resolve_repo(spec):
    spec_path = Path(spec).resolve()
    if str(spec_path) in repo_by_path:
        return repo_by_path[str(spec_path)]
    if spec in repo_by_name:
        return repo_by_name[spec]
    spec_name = spec_path.name
    if spec_name in repo_by_name:
        return repo_by_name[spec_name]
    raise SystemExit(f"ERROR: Could not resolve repo '{spec}' in workspace graph")

def closure(start, edges):
    seen = set()
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for nxt in sorted(edges.get(current, set())):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return sorted(seen)

changed = resolve_repo(changed_spec)
target = resolve_repo(target_spec)

upstreams_of_target = closure(target["name"], deps)
downstreams_of_changed = closure(changed["name"], dependents)
relevant_publish = [name for name in publish_order if name in upstreams_of_target]
impacts_target = changed["name"] == target["name"] or changed["name"] in upstreams_of_target

result = {
    "changed_repo": changed["name"],
    "target_repo": target["name"],
    "impacts_target": impacts_target,
    "affected_upstreams": upstreams_of_target,
    "affected_downstreams": downstreams_of_changed,
    "publish_order_for_target": relevant_publish,
    "commands": [],
}

skill_dir = "<skill_dir>/scripts"
result["commands"].append(f"bash {skill_dir}/sbt_status.sh {target['path']} --workspace")
if impacts_target and relevant_publish:
    result["commands"].append(f"bash {skill_dir}/sbt_refresh.sh {target['path']} --publish-upstreams --clean-target --rebuild")
elif impacts_target:
    result["commands"].append(f"bash {skill_dir}/sbt_build.sh {target['path']} -- compile")
else:
    result["commands"].append("# changed repo is not on the detected direct dependency path to the target")

if output_json:
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0)

print("=== Change Plan ===")
print(f"Changed repo: {result['changed_repo']}")
print(f"Target repo:  {result['target_repo']}")
print(f"Impacts target: {'yes' if impacts_target else 'no'}")
print()
print("--- Affected upstreams for target ---")
if result["affected_upstreams"]:
    for repo_name in result["affected_upstreams"]:
        print(f"  - {repo_name}")
else:
    print("  (none)")
print()
print("--- Affected downstreams for changed repo ---")
if result["affected_downstreams"]:
    for repo_name in result["affected_downstreams"]:
        print(f"  - {repo_name}")
else:
    print("  (none)")
print()
print("--- Publish order for target path ---")
if result["publish_order_for_target"]:
    for idx, repo_name in enumerate(result["publish_order_for_target"], start=1):
        print(f"  {idx}. {repo_name}")
else:
    print("  (no upstream publish steps required)")
print()
print("--- Suggested commands ---")
for command in result["commands"]:
    print(f"  {command}")
PY
