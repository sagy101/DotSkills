#!/usr/bin/env python3
"""List repositories in a Bitbucket workspace."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_client import BitbucketClient
from bb_config import add_common_args, load_config, resolve_workspace


def main() -> None:
    parser = argparse.ArgumentParser(description="List repos in a Bitbucket workspace")
    add_common_args(parser)
    parser.add_argument("--name", help="Filter by repo name (substring match)")
    parser.add_argument(
        "--max-results", type=int, default=50, help="Maximum results to return (default: 50)"
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
    client = BitbucketClient(config)

    q = None
    if args.name:
        q = f'name ~ "{args.name}"'

    repos = client.list_repos(workspace, max_results=args.max_results, q=q)

    if args.format == "json":
        print(json.dumps(repos, indent=2))
        return

    if not repos:
        print(f"No repositories found in workspace '{workspace}'.")
        return

    print(f"{'Slug':<30}  {'Name':<40}  {'Updated'}")
    print(f"{'─' * 30}  {'─' * 40}  {'─' * 20}")

    for r in repos:
        slug = r.get("slug", "?")[:30]
        name = r.get("name", "?")[:40]
        updated = r.get("updated_on", "?")[:19]
        print(f"{slug:<30}  {name:<40}  {updated}")

    print(f"\n{len(repos)} repo(s) shown.")


if __name__ == "__main__":
    main()
