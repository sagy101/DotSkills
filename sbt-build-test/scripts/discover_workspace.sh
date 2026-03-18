#!/usr/bin/env bash
# discover_workspace.sh — Scan a workspace for SBT projects and print a
# direct workspace dependency graph plus repo publish order.
#
# Scans all immediate subdirectories of the workspace for build.sbt files,
# merges with any overrides from <workspace>/.sbt-workspace.conf, then builds
# a direct workspace dependency map.
#
# Fully generic — discovers any SBT project, no repo names hardcoded.

set -euo pipefail

usage() {
  echo "Usage: discover_workspace.sh <workspace-dir> [--json]" >&2
  exit 2
}

[ "$#" -ge 1 ] || usage
WORKSPACE_DIR="$1"
shift
OUTPUT_JSON=false
while [ "$#" -gt 0 ]; do
  case "$1" in
    --json)
      OUTPUT_JSON=true
      shift
      ;;
    *)
      usage
      ;;
  esac
done

WORKSPACE_DIR="$(cd "$WORKSPACE_DIR" && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required for workspace graph generation" >&2
  exit 2
fi

# Resolve all SBT projects (auto-scan + config overrides)
source "$SCRIPT_DIR/resolve_projects.sh"

if [ ${#SERVICES[@]} -eq 0 ]; then
  echo "ERROR: No SBT projects found in $WORKSPACE_DIR" >&2
  exit 2
fi

_SERVICES_FILE=$(mktemp)
_GRAPH_JSON=$(mktemp)
trap 'rm -f "$_SERVICES_FILE" "$_GRAPH_JSON"' EXIT
printf '%s\n' "${SERVICES[@]}" > "$_SERVICES_FILE"
python3 "$SCRIPT_DIR/workspace_graph.py" --workspace-dir "$WORKSPACE_DIR" --services-file "$_SERVICES_FILE" --group-id "$GROUP_ID" > "$_GRAPH_JSON"

if [ "$OUTPUT_JSON" = true ]; then
  cat "$_GRAPH_JSON"
  exit 0
fi

python3 - "$WORKSPACE_DIR" "$_GRAPH_JSON" <<'PY'
import json
import sys
from pathlib import Path

workspace_dir = Path(sys.argv[1])
graph_path = Path(sys.argv[2])
data = json.loads(graph_path.read_text())

print("=== Workspace Dependency Map ===")
print(f"Workspace: {workspace_dir}")
config_path = workspace_dir / ".sbt-workspace.conf"
if config_path.is_file():
    print(f"Config: {config_path}")
print()
print(f"Found {len(data['repos'])} SBT projects:")
for repo in data["repos"]:
    print(f"  - {repo['name']}")
print()
print("=== Direct Workspace Dependency Graph ===")
print()
for repo in data["repos"]:
    deps = repo.get("dependencies", [])
    if deps:
        print(f"  {repo['name']} depends on:")
        for dep in deps:
            print(f"    -> {dep}")
    else:
        print(f"  {repo['name']}: no direct workspace dependencies")
print()
print("=== Publish Order (direct workspace dependency topological sort) ===")
print()
if data.get("publish_order"):
    for index, repo_name in enumerate(data["publish_order"], start=1):
        print(f"  {index}. {repo_name}")
else:
    print("  (no publish order available)")
if data.get("cycles"):
    print()
    print("WARN: cycle(s) detected in the direct workspace dependency graph:")
    for name in data["cycles"]:
        print(f"  - {name}")
print()
print("=== End Workspace Map ===")
PY
