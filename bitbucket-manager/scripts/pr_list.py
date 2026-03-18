#!/usr/bin/env python3
"""List Bitbucket pull requests."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_client import BitbucketClient
from bb_config import add_common_args, load_config, resolve_repo, resolve_workspace


def main() -> None:
    parser = argparse.ArgumentParser(description="List Bitbucket pull requests")
    add_common_args(parser)
    parser.add_argument(
        "--state",
        default="OPEN",
        choices=["OPEN", "MERGED", "DECLINED", "SUPERSEDED"],
        help="Filter by state (default: OPEN)",
    )
    parser.add_argument("--author", help="Filter by author nickname or UUID")
    parser.add_argument("--branch", help="Filter by source branch name")
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
    repo_slug = resolve_repo(config, args.repo)
    client = BitbucketClient(config)

    prs = client.list_prs(workspace, repo_slug, state=args.state, max_results=args.max_results)

    # Client-side filters
    if args.author:
        prs = [
            p
            for p in prs
            if args.author.lower()
            in (
                p.get("author", {}).get("display_name", "").lower()
                + p.get("author", {}).get("nickname", "").lower()
                + p.get("author", {}).get("uuid", "").lower()
            )
        ]
    if args.branch:
        prs = [
            p for p in prs if p.get("source", {}).get("branch", {}).get("name", "") == args.branch
        ]

    if args.format == "json":
        print(json.dumps(prs, indent=2))
        return

    # Table format
    if not prs:
        print(f"No {args.state} pull requests found.")
        return

    # Header
    print(f"{'ID':>6}  {'State':<10}  {'Author':<20}  {'Source':<30}  {'Title'}")
    print(f"{'─' * 6}  {'─' * 10}  {'─' * 20}  {'─' * 30}  {'─' * 40}")

    for pr in prs:
        pr_id = pr.get("id", "?")
        state = pr.get("state", "?")
        author = pr.get("author", {}).get("display_name", "?")[:20]
        source = pr.get("source", {}).get("branch", {}).get("name", "?")[:30]
        title = pr.get("title", "?")
        print(f"{pr_id:>6}  {state:<10}  {author:<20}  {source:<30}  {title}")

    print(f"\n{len(prs)} PR(s) shown.")


if __name__ == "__main__":
    main()
