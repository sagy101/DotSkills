#!/usr/bin/env python3
"""List Bitbucket repository pipelines."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_client import BitbucketClient
from bb_config import add_common_args, load_config, resolve_repo, resolve_workspace


def main() -> None:
    parser = argparse.ArgumentParser(description="List Bitbucket pipelines")
    add_common_args(parser)
    parser.add_argument(
        "--max-results",
        type=int,
        default=50,
        help="Maximum results to return (default: 50, 0 = all)",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    workspace = resolve_workspace(config, args.workspace)
    repo_slug = resolve_repo(config, args.repo)
    client = BitbucketClient(config)

    pipelines = client.list_pipelines(workspace, repo_slug, max_results=args.max_results)

    if args.format == "json":
        print(json.dumps(pipelines, indent=2))
        return

    if not pipelines:
        print("No pipelines found.")
        return

    print(f"{'UUID':<40}  {'State':<14}  {'Created'}")
    print(f"{'─' * 40}  {'─' * 14}  {'─' * 25}")
    for pipeline in pipelines:
        state = pipeline.get("state", {})
        state_name = state.get("name") or state.get("type") or "?"
        print(
            f"{pipeline.get('uuid', '?'):<40}  {state_name:<14}  {pipeline.get('created_on', '?')}"
        )


if __name__ == "__main__":
    main()
