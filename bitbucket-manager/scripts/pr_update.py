#!/usr/bin/env python3
"""Update an existing Bitbucket pull request."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_client import BitbucketClient
from bb_config import add_common_args, load_config, resolve_repo, resolve_workspace


def main() -> None:
    parser = argparse.ArgumentParser(description="Update a Bitbucket pull request")
    add_common_args(parser)
    parser.add_argument("--pr", required=True, type=int, help="PR ID to update")
    parser.add_argument("--title", help="New PR title")
    parser.add_argument("--description", help="New PR description")
    parser.add_argument("--destination", help="New destination branch")
    parser.add_argument("--reviewers", help="Comma-separated reviewer UUIDs (replaces existing)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show current vs proposed diff without updating"
    )
    args = parser.parse_args()

    if not any([args.title, args.description, args.destination, args.reviewers]):
        parser.error(
            "Provide at least one field to update: --title, --description, --destination, --reviewers"
        )

    config = load_config(args.config)
    workspace = resolve_workspace(config, args.workspace)
    repo_slug = resolve_repo(config, args.repo)
    client = BitbucketClient(config)

    fields = {}
    if args.title:
        fields["title"] = args.title
    if args.description:
        fields["description"] = args.description
    if args.destination:
        fields["destination"] = args.destination
    if args.reviewers:
        fields["reviewers"] = [r.strip() for r in args.reviewers.split(",") if r.strip()]

    if args.dry_run:
        current = client.get_pr(workspace, repo_slug, args.pr)
        print(f"DRY RUN — PR #{args.pr} diff:")
        print()
        for key, new_val in fields.items():
            if key == "destination":
                old_val = current.get("destination", {}).get("branch", {}).get("name", "")
            elif key == "reviewers":
                old_val = [r.get("uuid", "") for r in current.get("reviewers", [])]
            else:
                old_val = current.get(key, "")
            print(f"  {key}:")
            print(f"    current:  {old_val}")
            print(f"    proposed: {new_val}")
        return

    result = client.update_pr(workspace, repo_slug, args.pr, **fields)
    print(f"PR #{args.pr} updated.")
    pr_url = result.get("links", {}).get("html", {}).get("href", "")
    if pr_url:
        print(f"URL: {pr_url}")


if __name__ == "__main__":
    main()
