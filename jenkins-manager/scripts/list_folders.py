#!/usr/bin/env python3
"""List top-level Jenkins folders and jobs."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jenkins_client import JenkinsClient, color_to_status
from jenkins_config import load_config, resolve_instance


def main() -> None:
    parser = argparse.ArgumentParser(description="List top-level Jenkins folders and jobs")
    parser.add_argument("--config", help="Path to .jenkins.json (omit to auto-discover)")
    parser.add_argument("--instance", help="Named Jenkins instance (omit to use default)")
    parser.add_argument(
        "--format", choices=["table", "json"], default="table", help="Output format"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    instance = resolve_instance(config, args.instance)
    client = JenkinsClient(instance)
    items = client.list_top_level_jobs()

    if args.format == "json":
        print(json.dumps(items, indent=2))
        return

    if not items:
        print("No folders or jobs found.")
        return

    # Table output
    print(f"{'Name':<40} {'Type':<20} {'Status':<12}")
    print("-" * 72)
    for item in sorted(items, key=lambda x: x.get("name", "")):
        name = item.get("name", "")
        cls = item.get("_class", "")
        # Simplify class name
        if "OrganizationFolder" in cls:
            type_str = "Org Folder"
        elif "Folder" in cls:
            type_str = "Folder"
        elif "MultiBranch" in cls or "Multibranch" in cls:
            type_str = "MultiBranch"
        elif "FreeStyle" in cls:
            type_str = "Freestyle"
        elif "WorkflowJob" in cls:
            type_str = "Pipeline"
        else:
            type_str = cls.split(".")[-1] if cls else "Unknown"
        status = color_to_status(item.get("color")) if item.get("color") else "—"
        print(f"{name:<40} {type_str:<20} {status:<12}")

    print(f"\nTotal: {len(items)} items")


if __name__ == "__main__":
    main()
