#!/usr/bin/env python3
"""List Jenkins jobs, optionally filtered by folder and name pattern."""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jenkins_client import JenkinsClient, color_to_status
from jenkins_config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="List Jenkins jobs")
    parser.add_argument("--config", help="Path to .jenkins.json (omit to auto-discover)")
    parser.add_argument("--folder", help="Folder name (omit to search all folders)")
    parser.add_argument("--name", help="Filter jobs by name pattern (substring or regex)")
    parser.add_argument(
        "--format", choices=["table", "json"], default="table", help="Output format"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    client = JenkinsClient(config)

    # Collect jobs
    all_jobs: list[dict] = []

    if args.folder:
        # Search specific folder
        jobs = client.list_jobs_in_folder(args.folder)
        for j in jobs:
            j["_folder"] = args.folder
        all_jobs.extend(jobs)
    else:
        # Search all top-level items
        top_level = client.list_top_level_jobs()
        for item in top_level:
            cls = item.get("_class", "")
            name = item.get("name", "")
            if "Folder" in cls or "OrganizationFolder" in cls:
                try:
                    jobs = client.list_jobs_in_folder(name)
                    for j in jobs:
                        j["_folder"] = name
                    all_jobs.extend(jobs)
                except Exception:
                    continue
            else:
                # Top-level job (not in a folder)
                item["_folder"] = ""
                all_jobs.append(item)

    # Filter by name pattern
    if args.name:
        try:
            pattern = re.compile(args.name, re.IGNORECASE)
            all_jobs = [j for j in all_jobs if pattern.search(j.get("name", ""))]
        except re.error:
            # Fall back to substring match
            name_lower = args.name.lower()
            all_jobs = [j for j in all_jobs if name_lower in j.get("name", "").lower()]

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
