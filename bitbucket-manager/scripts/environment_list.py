#!/usr/bin/env python3
"""List Bitbucket deployment environments."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_client import BitbucketClient
from bb_config import add_common_args, load_config, resolve_repo, resolve_workspace


def main() -> None:
    parser = argparse.ArgumentParser(description="List Bitbucket environments")
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

    environments = client.list_environments(workspace, repo_slug, max_results=args.max_results)
    if args.format == "json":
        print(json.dumps(environments, indent=2))
        return

    if not environments:
        print("No environments found.")
        return

    print(f"{'UUID':<40}  {'Name'}")
    print(f"{'─' * 40}  {'─' * 30}")
    for env in environments:
        print(f"{env.get('uuid', '?'):<40}  {env.get('name', '?')}")


if __name__ == "__main__":
    main()
