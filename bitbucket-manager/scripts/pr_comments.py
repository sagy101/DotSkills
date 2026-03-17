#!/usr/bin/env python3
"""List comments on one or more Bitbucket pull requests.

Supports filtering by resolution status, author, file, and reply presence.
Displays a threaded view optimised for agent readability.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_client import BitbucketClient
from bb_config import add_common_args, load_config, resolve_repo, resolve_workspace
from bb_threads import Thread, build_threads, filter_threads


def _format_comment_header(c: dict[str, Any]) -> str:
    """Format a single comment's header line: #ID Author (timestamp) [file:line]."""
    author = c.get("user", {}).get("display_name", "?")
    created = c.get("created_on", "?")[:19]
    inline = c.get("inline")

    location = ""
    if inline:
        path = inline.get("path", "")
        line = inline.get("to", "")
        location = f" [{path}:{line}]" if line else f" [{path}]"

    return f"#{c.get('id')} {author} ({created}){location}"


def _print_thread(thread: Thread, index: int, total: int) -> None:
    """Print a single thread with tree connectors."""
    # Thread header
    if thread.resolved:
        resolver = thread.resolver or "unknown"
        resolved_on = thread.resolved_on or "?"
        status = f"RESOLVED by {resolver} on {resolved_on}"
    else:
        status = "UNRESOLVED"

    print(f"--- Thread {index}/{total} [{status}] ---")

    # Root comment
    header = _format_comment_header(thread.root)
    print(f"  {header}")
    body = thread.root.get("content", {}).get("raw", "")
    for line in body.splitlines():
        print(f"    {line}")

    # Replies with tree connectors
    for i, child in enumerate(thread.children):
        is_last = i == len(thread.children) - 1
        print("  |")
        header = _format_comment_header(child)
        print(f"  +-- {header}")
        child_body = child.get("content", {}).get("raw", "")
        for line_text in child_body.splitlines():
            if is_last:
                print(f"      {line_text}")
            else:
                print(f"  |   {line_text}")

    print()


def _print_pr_comments(
    client: BitbucketClient,
    workspace: str,
    repo_slug: str,
    pr_id: int,
    threads: list[Thread],
    total_comments: int,
) -> dict[str, int]:
    """Print threaded comments for a single PR. Returns stats dict."""
    n_resolved = sum(1 for t in threads if t.resolved)
    n_unresolved = len(threads) - n_resolved

    print(
        f"PR #{pr_id} — {len(threads)} threads "
        f"({n_unresolved} unresolved, {n_resolved} resolved), "
        f"{total_comments} comments total"
    )
    print()

    if not threads:
        print("  (no matching comments)")
        print()
    else:
        for i, thread in enumerate(threads, 1):
            _print_thread(thread, i, len(threads))

    return {"threads": len(threads), "unresolved": n_unresolved, "comments": total_comments}


def main() -> None:
    parser = argparse.ArgumentParser(description="List comments on Bitbucket PR(s)")
    add_common_args(parser)
    parser.add_argument("--pr", required=True, type=int, nargs="+", help="PR ID(s)")
    parser.add_argument(
        "--format",
        choices=["threaded", "json"],
        default="threaded",
        help="Output format (default: threaded)",
    )
    # Filters
    parser.add_argument(
        "--status",
        choices=["resolved", "unresolved", "all"],
        default="all",
        help="Filter threads by resolution status (default: all)",
    )
    parser.add_argument("--author", help="Filter by root comment author (substring match)")
    parser.add_argument("--file", help="Filter by inline file path (substring match)")
    reply_group = parser.add_mutually_exclusive_group()
    reply_group.add_argument(
        "--has-replies", action="store_true", default=False, help="Only threads with replies"
    )
    reply_group.add_argument(
        "--no-replies", action="store_true", default=False, help="Only threads without replies"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    workspace = resolve_workspace(config, args.workspace)
    repo_slug = resolve_repo(config, args.repo)
    client = BitbucketClient(config)

    has_replies: bool | None = None
    if args.has_replies:
        has_replies = True
    elif args.no_replies:
        has_replies = False

    multi = len(args.pr) > 1
    all_comments_json: dict[int, list[dict]] = {}
    totals = {"threads": 0, "unresolved": 0, "comments": 0}

    for pr_id in args.pr:
        comments = client.get_pr_comments(workspace, repo_slug, pr_id)

        if args.format == "json":
            all_comments_json[pr_id] = comments
            continue

        threads = build_threads(comments)
        filtered = filter_threads(
            threads,
            status=args.status,
            author=args.author,
            file=args.file,
            has_replies=has_replies,
        )

        if multi:
            print(f"{'=' * 20} PR #{pr_id} {'=' * 20}")
            print()

        stats = _print_pr_comments(client, workspace, repo_slug, pr_id, filtered, len(comments))
        totals["threads"] += stats["threads"]
        totals["unresolved"] += stats["unresolved"]
        totals["comments"] += stats["comments"]

    if args.format == "json":
        # For single PR, output flat list (backwards-compatible); for multi, keyed dict
        if len(args.pr) == 1:
            print(json.dumps(all_comments_json[args.pr[0]], indent=2))
        else:
            print(json.dumps(all_comments_json, indent=2))
        return

    if multi:
        print(
            f"Total: {totals['threads']} threads "
            f"({totals['unresolved']} unresolved) "
            f"across {len(args.pr)} PRs"
        )


if __name__ == "__main__":
    main()
