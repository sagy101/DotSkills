#!/usr/bin/env python3
"""List Jenkins jobs, optionally filtered by folder and name pattern."""

import argparse
import json
import re
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jenkins_client import JenkinsClient, color_to_status
from jenkins_config import load_config, resolve_instance


def _collect_jobs(client: JenkinsClient, folder: str | None) -> list[dict]:
    """Collect jobs from a specific folder or all folders."""
    all_jobs: list[dict] = []
    if folder:
        jobs = client.list_jobs_in_folder(folder)
        for j in jobs:
            j["_folder"] = folder
        return jobs

    top_level = client.list_top_level_jobs()
    for item in top_level:
        cls = item.get("_class", "")
        name = item.get("name", "")
        if "Folder" in cls or "OrganizationFolder" in cls:
            try:
                jobs = client.list_jobs_in_folder(name)
            except (urllib.error.HTTPError, urllib.error.URLError):
                continue
            for j in jobs:
                j["_folder"] = name
            all_jobs.extend(jobs)
        else:
            item["_folder"] = ""
            all_jobs.append(item)
    return all_jobs


def _filter_by_name(jobs: list[dict], name_pattern: str) -> list[dict]:
    """Filter jobs by regex or substring pattern."""
    try:
        pattern = re.compile(name_pattern, re.IGNORECASE)
        return [j for j in jobs if pattern.search(j.get("name", ""))]
    except re.error:
        name_lower = name_pattern.lower()
        return [j for j in jobs if name_lower in j.get("name", "").lower()]


def main() -> None:
    parser = argparse.ArgumentParser(description="List Jenkins jobs")
    parser.add_argument("--config", help="Path to .jenkins.json (omit to auto-discover)")
    parser.add_argument("--instance", help="Named Jenkins instance (omit to use default)")
    parser.add_argument("--folder", help="Folder name (omit to search all folders)")
    parser.add_argument("--name", help="Filter jobs by name pattern (substring or regex)")
    parser.add_argument(
        "--format", choices=["table", "json"], default="table", help="Output format"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    instance = resolve_instance(config, args.instance)
    client = JenkinsClient(instance)
    all_jobs = _collect_jobs(client, args.folder)

    if args.name:
        all_jobs = _filter_by_name(all_jobs, args.name)

    if args.format == "json":
        print(json.dumps(all_jobs, indent=2))
        return

    if not all_jobs:
        print("No jobs found.")
        return

    # Table output
    print(f"{'Folder':<25} {'Job':<40} {'Type':<15} {'Status':<12}")
    print("-" * 92)
    for job in sorted(all_jobs, key=lambda x: (x.get("_folder", ""), x.get("name", ""))):
        folder = job.get("_folder", "")
        name = job.get("name", "")
        cls = job.get("_class", "")
        if "MultiBranch" in cls or "Multibranch" in cls:
            type_str = "MultiBranch"
        elif "FreeStyle" in cls:
            type_str = "Freestyle"
        elif "WorkflowJob" in cls:
            type_str = "Pipeline"
        else:
            type_str = cls.split(".")[-1] if cls else "Unknown"
        status = color_to_status(job.get("color")) if job.get("color") else "—"
        print(f"{folder:<25} {name:<40} {type_str:<15} {status:<12}")

    print(f"\nTotal: {len(all_jobs)} jobs")


if __name__ == "__main__":
    main()
