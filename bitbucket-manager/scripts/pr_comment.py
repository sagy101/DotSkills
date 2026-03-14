#!/usr/bin/env python3
"""Add a comment to a Bitbucket pull request."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_config import add_common_args, load_config, resolve_repo, resolve_workspace
from bb_client import BitbucketClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Add a comment to a Bitbucket PR")
    add_common_args(parser)
    parser.add_argument("--pr", required=True, type=int, help="PR ID")
    parser.add_argument("--body", required=True, help="Comment text (markdown)")
    parser.add_argument("--file", help="File path for inline comment")
    parser.add_argument("--line", type=int, help="Line number for inline comment (requires --file)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show comment preview without posting")
    args = parser.parse_args()

    if args.line and not args.file:
        parser.error("--line requires --file")

    config = load_config(args.config)
    workspace = resolve_workspace(config, args.workspace)
    repo_slug = resolve_repo(config, args.repo)

    inline = None
    if args.file:
        inline = {"path": args.file}
        if args.line:
            inline["to"] = args.line

    if args.dry_run:
        print(f"DRY RUN — would post comment on PR #{args.pr}:")
        print(f"  Body: {args.body}")
        if inline:
            print(f"  Inline: {json.dumps(inline)}")
        return

    client = BitbucketClient(config)
    result = client.add_pr_comment(
        workspace=workspace,
        repo_slug=repo_slug,
        pr_id=args.pr,
        body=args.body,
        inline=inline,
    )

    comment_id = result.get("id", "?")
    print(f"Comment #{comment_id} posted on PR #{args.pr}.")


if __name__ == "__main__":
    main()
