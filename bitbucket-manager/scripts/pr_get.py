#!/usr/bin/env python3
"""Get details of a Bitbucket pull request."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_client import BitbucketClient
from bb_config import add_common_args, load_config, resolve_repo, resolve_workspace


def _format_reviewer(r: dict) -> str:
    """Format a reviewer entry with approval status."""
    name = r.get("display_name", r.get("uuid", "unknown"))
    approved = r.get("approved", False)
    status = "APPROVED" if approved else "pending"
    return f"  - {name} ({status})"


def main() -> None:
    parser = argparse.ArgumentParser(description="Get Bitbucket PR details")
    add_common_args(parser)
    parser.add_argument("--pr", required=True, type=int, help="PR ID")
    parser.add_argument(
        "--format",
        choices=["detail", "json"],
        default="detail",
        help="Output format (default: detail)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    workspace = resolve_workspace(config, args.workspace)
    repo_slug = resolve_repo(config, args.repo)
    client = BitbucketClient(config)

    pr = client.get_pr(workspace, repo_slug, args.pr)

    if args.format == "json":
        print(json.dumps(pr, indent=2))
        return

    # Detail format
    source = pr.get("source", {}).get("branch", {}).get("name", "?")
    dest = pr.get("destination", {}).get("branch", {}).get("name", "?")
    state = pr.get("state", "?")
    author = pr.get("author", {}).get("display_name", "?")
    created = pr.get("created_on", "?")
    updated = pr.get("updated_on", "?")
    url = pr.get("links", {}).get("html", {}).get("href", "")

    print(f"PR #{pr.get('id')} — {pr.get('title', '?')}")
    print(f"State:   {state}")
    print(f"Author:  {author}")
    print(f"Branch:  {source} → {dest}")
    print(f"Created: {created}")
    print(f"Updated: {updated}")
    print(f"URL:     {url}")

    desc = pr.get("description", "")
    if desc:
        print(f"\nDescription:\n{desc}")

    reviewers = pr.get("reviewers", [])
    participants = pr.get("participants", [])
    # Merge reviewer info with participant approval status
    reviewer_map = {p.get("user", {}).get("uuid"): p for p in participants}
    if reviewers:
        print("\nReviewers:")
        for r in reviewers:
            uuid = r.get("uuid", "")
            participant = reviewer_map.get(uuid, {})
            name = r.get("display_name", r.get("nickname", uuid))
            approved = participant.get("approved", False)
            status = "APPROVED" if approved else "pending"
            print(f"  - {name} ({status})")


if __name__ == "__main__":
    main()
