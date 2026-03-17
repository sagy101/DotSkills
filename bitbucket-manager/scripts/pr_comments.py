#!/usr/bin/env python3
"""List comments on a Bitbucket pull request."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_client import BitbucketClient
from bb_config import add_common_args, load_config, resolve_repo, resolve_workspace


def main() -> None:
    parser = argparse.ArgumentParser(description="List comments on a Bitbucket PR")
    add_common_args(parser)
    parser.add_argument("--pr", required=True, type=int, help="PR ID")
    parser.add_argument(
        "--format",
        choices=["threaded", "json"],
        default="threaded",
        help="Output format (default: threaded)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    workspace = resolve_workspace(config, args.workspace)
    repo_slug = resolve_repo(config, args.repo)
    client = BitbucketClient(config)

    comments = client.get_pr_comments(workspace, repo_slug, args.pr)

    if args.format == "json":
        print(json.dumps(comments, indent=2))
        return

    if not comments:
        print(f"No comments on PR #{args.pr}.")
        return

    # Build threaded view
    roots = []
    children = {}
    for c in comments:
        parent_id = c.get("parent", {}).get("id")
        if parent_id:
            children.setdefault(parent_id, []).append(c)
        else:
            roots.append(c)

    def _print_comment(c: dict, indent: int = 0) -> None:
        prefix = "  " * indent
        author = c.get("user", {}).get("display_name", "?")
        created = c.get("created_on", "?")[:19]
        body = c.get("content", {}).get("raw", "")
        inline = c.get("inline")

        location = ""
        if inline:
            path = inline.get("path", "")
            line = inline.get("to", "")
            location = f" [{path}:{line}]" if line else f" [{path}]"

        resolution = c.get("resolution")
        resolved = resolution and resolution.get("type")
        status = " [RESOLVED]" if resolved else ""

        print(f"{prefix}#{c.get('id')} {author} ({created}){location}{status}")
        for line in body.splitlines():
            print(f"{prefix}  {line}")
        print()

        for child in children.get(c.get("id"), []):
            _print_comment(child, indent + 1)

    print(f"Comments on PR #{args.pr}:")
    print()
    for root in roots:
        _print_comment(root)

    print(f"{len(comments)} comment(s) total.")


if __name__ == "__main__":
    main()
