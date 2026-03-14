#!/usr/bin/env python3
"""Create a Bitbucket pull request."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_config import add_common_args, load_config, resolve_repo, resolve_workspace
from bb_client import BitbucketClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a Bitbucket pull request")
    add_common_args(parser)
    parser.add_argument("--title", required=True, help="PR title")
    parser.add_argument("--source", required=True, help="Source branch name")
    parser.add_argument("--destination", help="Destination branch (default from config)")
    parser.add_argument("--description", default="", help="PR description")
    parser.add_argument("--reviewers", help="Comma-separated reviewer UUIDs")
    parser.add_argument("--close-source-branch", action="store_true",
                        help="Close source branch after merge")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show payload without creating")
    args = parser.parse_args()

    config = load_config(args.config)
    workspace = resolve_workspace(config, args.workspace)
    repo_slug = resolve_repo(config, args.repo)
    destination = args.destination or config.default_destination

    reviewers = []
    if args.reviewers:
        reviewers = [r.strip() for r in args.reviewers.split(",") if r.strip()]
    elif config.default_reviewers:
        reviewers = config.default_reviewers

    payload = {
        "title": args.title,
        "source": {"branch": {"name": args.source}},
        "destination": {"branch": {"name": destination}},
        "description": args.description,
        "close_source_branch": args.close_source_branch,
        "reviewers": [{"uuid": r} for r in reviewers],
    }

    if args.dry_run:
        print("DRY RUN — would create PR with payload:")
        print(json.dumps(payload, indent=2))
        return

    client = BitbucketClient(config)
    result = client.create_pr(
        workspace=workspace,
        repo_slug=repo_slug,
        title=args.title,
        source_branch=args.source,
        destination_branch=destination,
        description=args.description,
        reviewers=reviewers,
        close_source_branch=args.close_source_branch,
    )

    pr_id = result.get("id")
    pr_url = result.get("links", {}).get("html", {}).get("href", "")
    print(f"PR #{pr_id} created: {pr_url}")


if __name__ == "__main__":
    main()
