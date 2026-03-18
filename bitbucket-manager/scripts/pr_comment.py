#!/usr/bin/env python3
"""Add a comment to a Bitbucket pull request."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_client import BitbucketClient
from bb_config import add_common_args, load_config, resolve_repo, resolve_workspace


def main() -> None:
    parser = argparse.ArgumentParser(description="Add a comment to a Bitbucket PR")
    add_common_args(parser)
    parser.add_argument("--pr", required=True, type=int, help="PR ID")
    parser.add_argument("--body", help="Comment text (markdown, required unless --resolve)")
    parser.add_argument("--file", help="File path for inline comment")
    parser.add_argument("--line", type=int, help="Line number for inline comment (requires --file)")
    parser.add_argument("--parent-id", type=int, help="Parent comment ID for threaded reply")
    parser.add_argument(
        "--resolve",
        type=int,
        metavar="COMMENT_ID",
        help="Resolve a comment by ID (no --body needed)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show comment preview without posting"
    )
    args = parser.parse_args()

    if args.line and not args.file:
        parser.error("--line requires --file")
    if not args.resolve and not args.body:
        parser.error("--body is required unless using --resolve")

    config = load_config(args.config)
    workspace = resolve_workspace(config, args.workspace)
    repo_slug = resolve_repo(config, args.repo)

    inline = None
    if args.file:
        inline = {"path": args.file}
        if args.line:
            inline["to"] = args.line

    client = BitbucketClient(config)

    if args.resolve:
        if args.dry_run:
            print(f"DRY RUN — would resolve comment #{args.resolve} on PR #{args.pr}")
            return
        client.resolve_pr_comment(
            workspace=workspace,
            repo_slug=repo_slug,
            pr_id=args.pr,
            comment_id=args.resolve,
        )
        print(f"Comment #{args.resolve} resolved on PR #{args.pr}.")
        return

    if args.dry_run:
        print(f"DRY RUN — would post comment on PR #{args.pr}:")
        print(f"  Body: {args.body}")
        if inline:
            print(f"  Inline: {json.dumps(inline)}")
        if args.parent_id:
            print(f"  Reply to: #{args.parent_id}")
        return

    result = client.add_pr_comment(
        workspace=workspace,
        repo_slug=repo_slug,
        pr_id=args.pr,
        body=args.body,
        inline=inline,
        parent_id=args.parent_id,
    )

    comment_id = result.get("id", "?")
    action = f"replied to #{args.parent_id}" if args.parent_id else "posted"
    print(f"Comment #{comment_id} {action} on PR #{args.pr}.")


if __name__ == "__main__":
    main()
