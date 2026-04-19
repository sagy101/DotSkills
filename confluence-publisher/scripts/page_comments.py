#!/usr/bin/env python3
"""List and add comments on Confluence pages."""

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from confluence_api import add_page_comment, get_page_comments  # noqa: E402
from confluence_config import load_config  # noqa: E402


def _cmd_list(args: argparse.Namespace) -> None:
    """List comments on a page."""
    config = load_config()
    comment_type = "inline" if args.inline else "comment"
    comments = get_page_comments(config, args.page_id, comment_type=comment_type, limit=args.limit)

    if not comments:
        label = "inline" if args.inline else "footer"
        print(f"No {label} comments on page {args.page_id}.")
        return

    if args.format == "json":
        import json
        from dataclasses import asdict

        print(json.dumps([asdict(c) for c in comments], indent=2))
        return

    for c in comments:
        print(f"[{c.comment_id}] {c.author} ({c.created})")
        body_preview = c.body_html[:120].replace("\n", " ")
        print(f"  {body_preview}")
        print()
    print(f"Total: {len(comments)} comments")


def _cmd_add(args: argparse.Namespace) -> None:
    """Add a comment to a page."""
    config = load_config()
    body = args.body

    comment_id = add_page_comment(config, args.page_id, body, comment_type="comment")
    print(f"Created comment {comment_id} on page {args.page_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Confluence page comments")
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    list_parser = sub.add_parser("list", help="List comments on a page")
    list_parser.add_argument("--page-id", required=True, help="Confluence page ID")
    list_parser.add_argument(
        "--inline", action="store_true", help="Show inline comments instead of footer"
    )
    list_parser.add_argument("--limit", type=int, default=50, help="Max comments (default: 50)")
    list_parser.add_argument("--format", choices=["table", "json"], default="table")

    # add
    add_parser = sub.add_parser("add", help="Add a footer comment to a page")
    add_parser.add_argument("--page-id", required=True, help="Confluence page ID")
    add_parser.add_argument("--body", required=True, help="Comment body (HTML storage format)")

    args = parser.parse_args()

    if args.command == "list":
        _cmd_list(args)
    elif args.command == "add":
        _cmd_add(args)


if __name__ == "__main__":
    main()
