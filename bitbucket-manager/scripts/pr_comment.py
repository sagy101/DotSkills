#!/usr/bin/env python3
"""Add a comment to a Bitbucket pull request, or resolve one or more comments."""

import argparse
import json
import sys
import time
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_client import BitbucketClient
from bb_config import add_common_args, load_config, resolve_repo, resolve_workspace

_RESOLVE_DELAY_S = 1  # Atlassian-recommended delay between mutative requests


def _bulk_resolve(
    client: BitbucketClient,
    workspace: str,
    repo_slug: str,
    pr_id: int,
    comment_ids: list[int],
    dry_run: bool,
) -> None:
    """Resolve one or more comment threads by ID."""
    total = len(comment_ids)

    if dry_run:
        print(f"DRY RUN — would resolve {total} comment(s) on PR #{pr_id}:")
        for cid in comment_ids:
            print(f"  #{cid}")
        return

    succeeded = 0
    for i, cid in enumerate(comment_ids, 1):
        try:
            client.resolve_pr_comment(
                workspace=workspace,
                repo_slug=repo_slug,
                pr_id=pr_id,
                comment_id=cid,
            )
            print(f"[{i}/{total}] Resolved #{cid}")
            succeeded += 1
        except urllib.error.HTTPError as e:
            if e.code == 403:
                print(
                    f"[{i}/{total}] FAILED #{cid}: Cannot resolve — only inline "
                    f"(diff) comments can be resolved, not general PR comments.",
                    file=sys.stderr,
                )
            else:
                print(f"[{i}/{total}] FAILED #{cid}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[{i}/{total}] FAILED #{cid}: {e}", file=sys.stderr)
        # Sleep between calls to respect rate limits (skip after last)
        if i < total:
            time.sleep(_RESOLVE_DELAY_S)

    print(f"\nResolved {succeeded}/{total} comments on PR #{pr_id}.")
    if succeeded < total:
        sys.exit(1)


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
        nargs="+",
        metavar="COMMENT_ID",
        help="Resolve comment(s) by ID (no --body needed)",
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
        _bulk_resolve(client, workspace, repo_slug, args.pr, args.resolve, args.dry_run)
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
