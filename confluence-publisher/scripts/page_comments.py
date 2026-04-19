#!/usr/bin/env python3
"""Manage Confluence page comments with REST v2 helpers."""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from confluence_api import (  # noqa: E402
    add_page_comment,
    delete_comment,
    edit_comment,
    get_comment_like_count,
    get_comment_like_users,
    get_page_like_count,
    get_page_like_users,
    list_page_comments,
    reply_to_comment,
    resolve_comment,
    unresolve_comment,
    walk_comment_thread,
)
from confluence_config import load_config  # noqa: E402


def _comment_type(args: argparse.Namespace) -> str:
    if getattr(args, "inline", False):
        return "inline"
    return getattr(args, "comment_type", "comment")


def _dump_json(obj: object) -> str:
    if is_dataclass(obj) and not isinstance(obj, type):
        return json.dumps(asdict(obj), indent=2)
    if isinstance(obj, list):
        serialised = [
            asdict(item) if is_dataclass(item) and not isinstance(item, type) else item
            for item in obj
        ]
        return json.dumps(serialised, indent=2)
    return json.dumps(obj, indent=2)


def _print_comment_list(comments: Sequence[object], comment_type: str, page_id: str) -> None:
    if not comments:
        label = "inline" if comment_type == "inline" else "footer"
        print(f"No {label} comments on page {page_id}.")
        return

    print(f"{'ID':<12} {'Author':<20} {'Created':<24} Body")
    print("-" * 90)
    for comment in comments:
        preview = getattr(comment, "body_html", "").replace("\n", " ")[:120]
        print(
            f"{getattr(comment, 'comment_id', ''):<12} "
            f"{getattr(comment, 'author', ''):<20} "
            f"{getattr(comment, 'created', ''):<24} "
            f"{preview}"
        )
    print(f"\nTotal: {len(comments)}")


def _print_comment_tree(comments: Sequence[object]) -> None:
    if not comments:
        print("No comments found.")
        return

    children_by_parent: dict[str, list[object]] = {}
    roots: list[object] = []
    for comment in comments:
        parent_id = getattr(comment, "parent_comment_id", "")
        if parent_id:
            children_by_parent.setdefault(parent_id, []).append(comment)
        else:
            roots.append(comment)

    def _emit(comment: object, depth: int) -> None:
        prefix = "  " * depth
        preview = getattr(comment, "body_html", "").replace("\n", " ")[:120]
        print(
            f"{prefix}- [{getattr(comment, 'comment_id', '')}] "
            f"{getattr(comment, 'author', '')} {preview}"
        )
        for child in children_by_parent.get(getattr(comment, "comment_id", ""), []):
            _emit(child, depth + 1)

    for root in roots:
        _emit(root, 0)


def _cmd_list(args: argparse.Namespace) -> None:
    config = load_config()
    if args.tree:
        comments = walk_comment_thread(
            config,
            args.page_id,
            comment_type=_comment_type(args),
            limit=args.limit,
        )
    else:
        comments = list_page_comments(
            config,
            args.page_id,
            comment_type=_comment_type(args),
            limit=args.limit,
            resolution_status=args.resolution_status,
        )
    if args.format == "json":
        print(_dump_json(comments))
        return
    if args.tree:
        _print_comment_tree(comments)
        return
    _print_comment_list(comments, _comment_type(args), args.page_id)


def _cmd_add(args: argparse.Namespace) -> None:
    config = load_config()
    cid = add_page_comment(
        config,
        args.page_id,
        args.body,
        comment_type=_comment_type(args),
        inline_text_selection=args.inline_text_selection,
        inline_text_selection_match_count=args.inline_text_selection_match_count,
        inline_text_selection_match_index=args.inline_text_selection_match_index,
    )
    print(f"Created comment {cid} on page {args.page_id}")


def _cmd_reply(args: argparse.Namespace) -> None:
    config = load_config()
    cid = reply_to_comment(
        config,
        args.page_id,
        args.parent_comment_id,
        args.body,
        comment_type=_comment_type(args),
    )
    print(f"Created footer reply {cid} on page {args.page_id}")


def _cmd_edit(args: argparse.Namespace) -> None:
    config = load_config()
    cid = edit_comment(config, args.comment_id, args.body, comment_type=_comment_type(args))
    print(f"Updated comment {cid}")


def _cmd_delete(args: argparse.Namespace) -> None:
    config = load_config()
    delete_comment(config, args.comment_id, comment_type=_comment_type(args))
    print(f"Deleted comment {args.comment_id}")


def _cmd_resolve(args: argparse.Namespace, resolved: bool) -> None:
    config = load_config()
    if _comment_type(args) != "inline":
        raise SystemExit("resolve/unresolve are only supported for inline comments")
    if resolved:
        cid = resolve_comment(config, args.comment_id)
        print(f"Resolved comment {cid}")
    else:
        cid = unresolve_comment(config, args.comment_id)
        print(f"Unresolved comment {cid}")


def _cmd_likes(args: argparse.Namespace) -> None:
    config = load_config()
    if args.page_id:
        count = get_page_like_count(config, args.page_id)
        users = get_page_like_users(config, args.page_id)
        target = f"page {args.page_id}"
    else:
        if (
            _comment_type(args) != "inline"
            and getattr(args, "comment_type", "comment") != "comment"
        ):
            target_type = _comment_type(args)
        else:
            target_type = _comment_type(args)
        count = get_comment_like_count(config, args.comment_id, comment_type=target_type)
        users = get_comment_like_users(config, args.comment_id, comment_type=target_type)
        target = f"{target_type} comment {args.comment_id}"

    if args.format == "json":
        print(json.dumps({"target": target, "count": count, "users": users}, indent=2))
        return

    print(f"Likes for {target}: {count}")
    if users:
        print("Users:")
        for user in users:
            print(f"  {user}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Confluence page comments")
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="List page comments")
    list_parser.add_argument("--page-id", required=True)
    list_parser.add_argument("--comment-type", choices=["comment", "inline"], default="comment")
    list_parser.add_argument("--inline", action="store_true", help="Alias for inline comments")
    list_parser.add_argument("--limit", type=int, default=50)
    list_parser.add_argument("--resolution-status", help="Inline comment resolution status filter")
    list_parser.add_argument("--tree", action="store_true", help="Recursively include replies")
    list_parser.add_argument("--format", choices=["table", "json"], default="table")

    add_parser = sub.add_parser("add", help="Add a footer or inline comment")
    add_parser.add_argument("--page-id", required=True)
    add_parser.add_argument("--body", required=True)
    add_parser.add_argument("--comment-type", choices=["comment", "inline"], default="comment")
    add_parser.add_argument("--inline", action="store_true", help="Alias for inline comments")
    add_parser.add_argument("--inline-text-selection")
    add_parser.add_argument("--inline-text-selection-match-count", type=int)
    add_parser.add_argument("--inline-text-selection-match-index", type=int)

    reply_parser = sub.add_parser("reply", help="Reply to a footer comment")
    reply_parser.add_argument("--page-id", required=True)
    reply_parser.add_argument("--parent-comment-id", required=True)
    reply_parser.add_argument("--body", required=True)

    edit_parser = sub.add_parser("edit", help="Edit a comment")
    edit_parser.add_argument("--comment-id", required=True)
    edit_parser.add_argument("--body", required=True)
    edit_parser.add_argument("--comment-type", choices=["comment", "inline"], default="comment")
    edit_parser.add_argument("--inline", action="store_true", help="Alias for inline comments")

    delete_parser = sub.add_parser("delete", help="Delete a comment")
    delete_parser.add_argument("--comment-id", required=True)
    delete_parser.add_argument("--comment-type", choices=["comment", "inline"], default="comment")
    delete_parser.add_argument("--inline", action="store_true", help="Alias for inline comments")

    resolve_parser = sub.add_parser("resolve", help="Resolve an inline comment")
    resolve_parser.add_argument("--comment-id", required=True)
    resolve_parser.add_argument("--comment-type", choices=["comment", "inline"], default="inline")
    resolve_parser.add_argument("--inline", action="store_true", help="Alias for inline comments")

    unresolve_parser = sub.add_parser("unresolve", help="Unresolve an inline comment")
    unresolve_parser.add_argument("--comment-id", required=True)
    unresolve_parser.add_argument("--comment-type", choices=["comment", "inline"], default="inline")
    unresolve_parser.add_argument("--inline", action="store_true", help="Alias for inline comments")

    likes_parser = sub.add_parser("likes", help="Read likes for a page or comment")
    target = likes_parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--page-id")
    target.add_argument("--comment-id")
    likes_parser.add_argument("--comment-type", choices=["comment", "inline"], default="comment")
    likes_parser.add_argument("--inline", action="store_true", help="Alias for inline comments")
    likes_parser.add_argument("--format", choices=["table", "json"], default="table")

    args = parser.parse_args()

    if getattr(args, "inline", False):
        args.comment_type = "inline"

    if args.command == "list":
        _cmd_list(args)
    elif args.command == "add":
        _cmd_add(args)
    elif args.command == "reply":
        _cmd_reply(args)
    elif args.command == "edit":
        _cmd_edit(args)
    elif args.command == "delete":
        _cmd_delete(args)
    elif args.command == "resolve":
        _cmd_resolve(args, True)
    elif args.command == "unresolve":
        _cmd_resolve(args, False)
    elif args.command == "likes":
        _cmd_likes(args)


if __name__ == "__main__":
    main()
