#!/usr/bin/env python3
"""List Jira projects visible to the current user."""

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jira_client import JiraClient
from jira_config_loader import add_config_arg, load_config


def format_projects_table(projects: list[dict[str, Any]]) -> str:
    """Format projects as a readable table."""
    if not projects:
        return "No visible projects found."

    lines = [f"{'Key':<12} {'Name':<30} {'Type':<12} Style", "-" * 70]
    lines.extend(
        [
            f"{project.get('key', '?'):<12} {project.get('name', '?'):<30} "
            f"{project.get('projectTypeKey', '?'):<12} {project.get('style', '?')}"
            for project in projects
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="List visible Jira projects")
    add_config_arg(parser)
    args = parser.parse_args()

    config = load_config(args.config)
    client = JiraClient(config)
    projects = client.get_visible_projects()

    print(format_projects_table(projects))


if __name__ == "__main__":
    main()
