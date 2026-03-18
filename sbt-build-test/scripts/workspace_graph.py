#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any


def read_services(path: Path) -> list[Path]:
    items: list[Path] = []
    for line in path.read_text().splitlines():
        raw = line.strip()
        if not raw:
            continue
        items.append(Path(raw).resolve())
    return items


def scan_repo(repo_path: Path, group_id: str) -> dict[str, Any]:
    files: list[Path] = [repo_path / "build.sbt"]
    project_dir = repo_path / "project"
    if project_dir.is_dir():
        files.extend(sorted(project_dir.glob("*.scala")))

    artifact_names: set[str] = set()
    project_refs: list[str] = []
    published_artifacts: set[str] = set()

    artifact_re = re.compile(r'(^|[^A-Za-z0-9_])name\s*:=\s*"([^"]+)"', re.MULTILINE)
    project_ref_re = re.compile(r'ProjectRef\(file\("([^"]+)"\),\s*"([^"]+)"')
    published_dep_re = None
    if group_id:
        published_dep_re = re.compile(r'"' + re.escape(group_id) + r'"\s*%%?\s*"([^"]+)"')

    for file_path in files:
        try:
            text = file_path.read_text()
        except UnicodeDecodeError:
            text = file_path.read_text(encoding="utf-8", errors="ignore")

        for match in artifact_re.finditer(text):
            artifact_names.add(match.group(2))
        for match in project_ref_re.finditer(text):
            ref_path = (repo_path / match.group(1)).resolve()
            project_refs.append(str(ref_path))
        if published_dep_re is not None:
            for match in published_dep_re.finditer(text):
                published_artifacts.add(match.group(1))

    if not artifact_names:
        artifact_names.add(repo_path.name)

    return {
        "name": repo_path.name,
        "path": str(repo_path),
        "artifacts": sorted(artifact_names),
        "project_ref_paths": sorted(set(project_refs)),
        "published_workspace_artifacts": sorted(published_artifacts),
    }


def topo_sort(nodes: list[str], deps: dict[str, set[str]]) -> tuple[list[str], list[str]]:
    in_degree = {node: len(deps.get(node, set())) for node in nodes}
    reverse: dict[str, set[str]] = defaultdict(set)
    for node, node_deps in deps.items():
        for dep in node_deps:
            reverse[dep].add(node)

    queue = deque(sorted(node for node in nodes if in_degree[node] == 0))
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for dependent in sorted(reverse.get(node, set())):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    remaining = sorted(node for node, degree in in_degree.items() if degree > 0)
    return order, remaining


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-dir", required=True)
    parser.add_argument("--services-file", required=True)
    parser.add_argument("--group-id", default="")
    args = parser.parse_args()

    workspace_dir = Path(args.workspace_dir).resolve()
    services = read_services(Path(args.services_file).resolve())
    repos = [scan_repo(repo, args.group_id) for repo in services]

    repo_by_path = {repo["path"]: repo for repo in repos}
    artifact_to_repos: dict[str, set[str]] = defaultdict(set)
    for repo in repos:
        for artifact in repo["artifacts"]:
            artifact_to_repos[artifact].add(repo["name"])

    dependencies: dict[str, set[str]] = {repo["name"]: set() for repo in repos}
    dependents: dict[str, set[str]] = {repo["name"]: set() for repo in repos}

    for repo in repos:
        repo_name = repo["name"]
        for ref_path in repo["project_ref_paths"]:
            target = repo_by_path.get(ref_path)
            if target is not None and target["name"] != repo_name:
                dependencies[repo_name].add(target["name"])
        for artifact in repo["published_workspace_artifacts"]:
            for target_name in artifact_to_repos.get(artifact, set()):
                if target_name != repo_name:
                    dependencies[repo_name].add(target_name)

    for repo_name, repo_deps in dependencies.items():
        for dep in repo_deps:
            dependents.setdefault(dep, set()).add(repo_name)

    order, cycles = topo_sort([repo["name"] for repo in repos], dependencies)

    output: dict[str, Any] = {
        "workspace": str(workspace_dir),
        "group_id": args.group_id,
        "repos": [],
        "publish_order": order,
        "cycles": cycles,
    }

    for repo in sorted(repos, key=lambda item: item["name"]):
        name = repo["name"]
        output["repos"].append(
            {
                **repo,
                "dependencies": sorted(dependencies.get(name, set())),
                "dependents": sorted(dependents.get(name, set())),
            }
        )

    json.dump(output, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
