#!/usr/bin/env python3
"""Decline a Bitbucket pull request."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_config import add_common_args, load_config, resolve_repo, resolve_workspace
from bb_client import BitbucketClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Decline a Bitbucket pull request")
    add_common_args(parser)
    parser.add_argument("--pr", required=True, type=int, help="PR ID to decline")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be declined without declining")
    args = parser.parse_args()

    config = load_config(args.config)
    workspace = resolve_workspace(config, args.workspace)
    repo_slug = resolve_repo(config, args.repo)
    client = BitbucketClient(config)

    if args.dry_run:
        pr = client.get_pr(workspace, repo_slug, args.pr)
        title = pr.get("title", "?")
        state = pr.get("state", "?")
        source = pr.get("source", {}).get("branch", {}).get("name", "?")
        print(f"DRY RUN — would decline PR #{args.pr}:")
        print(f"  Title:  {title}")
        print(f"  State:  {state}")
        print(f"  Branch: {source}")
        if state != "OPEN":
            print(f"\n  WARNING: PR is {state}, not OPEN — cannot decline.")
        return

    client.decline_pr(workspace, repo_slug, args.pr)
    print(f"PR #{args.pr} declined.")


if __name__ == "__main__":
    main()
