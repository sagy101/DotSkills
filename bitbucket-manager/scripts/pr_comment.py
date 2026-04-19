#!/usr/bin/env python3
"""Add, edit, delete, or resolve comments on a Bitbucket pull request."""

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


def _bulk_delete(
    client: BitbucketClient,
    workspace: str,
    repo_slug: str,
    pr_id: int,
    comment_ids: list[int],
    dry_run: bool,
) -> None:
    """Delete one or more comments by ID."""
    total = len(comment_ids)

    if dry_run:
        print(f"DRY RUN — would delete {total} comment(s) on PR #{pr_id}:")
        for cid in comment_ids:
            print(f"  #{cid}")
        return

    succeeded = 0
    for i, cid in enumerate(comment_ids, 1):
        try:
            client.delete_pr_comment(
                workspace=workspace,
                repo_slug=repo_slug,
                pr_id=pr_id,
                comment_id=cid,
            )
            print(f"[{i}/{total}] Deleted #{cid}")
            succeeded += 1
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(
                    f"[{i}/{total}] FAILED #{cid}: Comment not found.",
                    file=sys.stderr,
                )
            elif e.code == 403:
                print(
                    f"[{i}/{total}] FAILED #{cid}: Permission denied — "
                    f"you can only delete your own comments.",
                    file=sys.stderr,
                )
            else:
                print(f"[{i}/{total}] FAILED #{cid}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[{i}/{total}] FAILED #{cid}: {e}", file=sys.stderr)
        # Sleep between calls to respect rate limits (skip after last)
        if i < total:
            time.sleep(_RESOLVE_DELAY_S)

    print(f"\nDeleted {succeeded}/{total} comments on PR #{pr_id}.")
    if succeeded < total:
        sys.exit(1)


def _bulk_unresolve(
    client: BitbucketClient,
    workspace: str,
    repo_slug: str,
    pr_id: int,
    comment_ids: list[int],
    dry_run: bool,
) -> None:
    """Reopen one or more resolved comment threads by ID."""
    total = len(comment_ids)

    if dry_run:
        print(f"DRY RUN — would reopen {total} comment(s) on PR #{pr_id}:")
        for cid in comment_ids:
            print(f"  #{cid}")
        return

    succeeded = 0
    for i, cid in enumerate(comment_ids, 1):
        try:
            client.unresolve_pr_comment(
                workspace=workspace,
                repo_slug=repo_slug,
                pr_id=pr_id,
                comment_id=cid,
            )
            print(f"[{i}/{total}] Reopened #{cid}")
            succeeded += 1
        except urllib.error.HTTPError as e:
            if e.code == 403:
                print(
                    f"[{i}/{total}] FAILED #{cid}: Cannot reopen — only resolved inline "
                    f"(diff) comments can be reopened.",
                    file=sys.stderr,
                )
            else:
                print(f"[{i}/{total}] FAILED #{cid}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[{i}/{total}] FAILED #{cid}: {e}", file=sys.stderr)
        if i < total:
            time.sleep(_RESOLVE_DELAY_S)

    print(f"\nReopened {succeeded}/{total} comments on PR #{pr_id}.")
    if succeeded < total:
        sys.exit(1)


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Validate mutually exclusive flags and required combinations."""
    if not any([args.resolve, args.unresolve, args.edit, args.delete, args.body]):
        parser.error("one of --body, --resolve, --unresolve, --edit, or --delete is required")
    if args.resolve and args.unresolve:
        parser.error("--resolve and --unresolve are mutually exclusive")
    if args.edit and args.resolve:
        parser.error("--edit and --resolve are mutually exclusive")
    if args.edit and args.unresolve:
        parser.error("--edit and --unresolve are mutually exclusive")
    if args.edit and args.delete:
        parser.error("--edit and --delete are mutually exclusive")
    if args.delete and args.resolve:
        parser.error("--delete and --resolve are mutually exclusive")
    if args.delete and args.unresolve:
        parser.error("--delete and --unresolve are mutually exclusive")
    if args.edit and not args.body:
        parser.error("--edit requires --body with the new comment text")
    if args.delete and args.body:
        parser.error("--delete does not accept --body")
    if args.unresolve and args.body:
        parser.error("--unresolve does not accept --body")
    if args.line and not args.file:
        parser.error("--line requires --file")


def _edit_comment(
    client: BitbucketClient,
    workspace: str,
    repo_slug: str,
    pr_id: int,
    comment_id: int,
    body: str,
    dry_run: bool,
) -> None:
    """Edit an existing comment."""
    if dry_run:
        print(f"DRY RUN — would edit comment #{comment_id} on PR #{pr_id}:")
        print(f"  New body: {body}")
        return
    result = client.update_pr_comment(
        workspace=workspace,
        repo_slug=repo_slug,
        pr_id=pr_id,
        comment_id=comment_id,
        body=body,
    )
    print(f"Comment #{result.get('id', comment_id)} updated on PR #{pr_id}.")


def _add_comment(
    client: BitbucketClient,
    workspace: str,
    repo_slug: str,
    args: argparse.Namespace,
    inline: dict | None,
) -> None:
    """Add a new comment to a PR."""
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add, edit, delete, or resolve comments on a Bitbucket PR"
    )
    add_common_args(parser)
    parser.add_argument("--pr", required=True, type=int, help="PR ID")
    parser.add_argument("--body", help="Comment text (markdown)")
    parser.add_argument("--file", help="File path for inline comment")
    parser.add_argument("--line", type=int, help="Line number for inline comment (requires --file)")
    parser.add_argument("--parent-id", type=int, help="Parent comment ID for threaded reply")
    parser.add_argument(
        "--resolve",
        type=int,
        nargs="+",
        metavar="COMMENT_ID",
        help="Resolve comment(s) by ID",
    )
    parser.add_argument(
        "--unresolve",
        type=int,
        nargs="+",
        metavar="COMMENT_ID",
        help="Reopen resolved comment thread(s) by ID",
    )
    parser.add_argument(
        "--edit",
        type=int,
        metavar="COMMENT_ID",
        help="Edit an existing comment (requires --body)",
    )
    parser.add_argument(
        "--delete",
        type=int,
        nargs="+",
        metavar="COMMENT_ID",
        help="Delete comment(s) by ID",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show preview without executing")
    args = parser.parse_args()

    _validate_args(parser, args)

    config = load_config(args.config)
    workspace = resolve_workspace(config, args.workspace)
    repo_slug = resolve_repo(config, args.repo)
    client = BitbucketClient(config)

    if args.resolve:
        _bulk_resolve(client, workspace, repo_slug, args.pr, args.resolve, args.dry_run)
    elif args.unresolve:
        _bulk_unresolve(client, workspace, repo_slug, args.pr, args.unresolve, args.dry_run)
    elif args.delete:
        _bulk_delete(client, workspace, repo_slug, args.pr, args.delete, args.dry_run)
    elif args.edit:
        _edit_comment(client, workspace, repo_slug, args.pr, args.edit, args.body, args.dry_run)
    else:
        inline = None
        if args.file:
            inline = {"path": args.file}
            if args.line:
                inline["to"] = args.line
        _add_comment(client, workspace, repo_slug, args, inline)


if __name__ == "__main__":
    main()
