#!/usr/bin/env python3
"""Manage Jira issue comments."""

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jira_client import JiraClient
from jira_config_loader import add_config_arg, load_config


def _comment_body_preview(comment: dict[str, Any], limit: int = 80) -> str:
    text = _extract_comment_text(comment.get("body", ""))
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def _extract_comment_text(body: Any) -> str:
    """Extract readable text from Jira comment bodies."""
    if isinstance(body, str):
        return body.replace("\n", " ").strip()
    if isinstance(body, list):
        return " ".join(filter(None, (_extract_comment_text(item) for item in body))).strip()
    if isinstance(body, dict):
        if "text" in body and isinstance(body["text"], str):
            return body["text"].replace("\n", " ").strip()
        if "content" in body:
            return _extract_comment_text(body["content"])
    return str(body).replace("\n", " ").strip()


def format_comments_table(comments: list[dict[str, Any]]) -> str:
    """Format comments as a simple table."""
    if not comments:
        return "No comments found."

    lines = [f"{'ID':<8} {'Author':<24} {'Updated':<24} Body", "-" * 90]
    for comment in comments:
        author = comment.get("author", {}).get("displayName", "?")
        updated = comment.get("updated", "?")
        body = _comment_body_preview(comment)
        lines.append(f"{comment.get('id', '?'):<8} {author:<24} {updated:<24} {body}")
    return "\n".join(lines)


def _handle_list(client: JiraClient, issue_key: str) -> None:
    comments = client.get_comments(issue_key)
    print(format_comments_table(comments))


def _handle_add(client: JiraClient, issue_key: str, body: str) -> None:
    comment = client.add_comment(issue_key, body)
    print(f"Added comment {comment.get('id', '?')} to {issue_key}")


def _handle_edit(client: JiraClient, issue_key: str, comment_id: str, body: str) -> None:
    comment = client.update_comment(issue_key, comment_id, body)
    print(f"Updated comment {comment.get('id', comment_id)} on {issue_key}")


def _handle_delete(client: JiraClient, issue_key: str, comment_id: str) -> None:
    client.delete_comment(issue_key, comment_id)
    print(f"Deleted comment {comment_id} from {issue_key}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Jira comments")
    add_config_arg(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List comments on an issue")
    list_parser.add_argument("--key", required=True, help="Issue key")

    add_parser = subparsers.add_parser("add", help="Add a comment to an issue")
    add_parser.add_argument("--key", required=True, help="Issue key")
    add_parser.add_argument("--body", required=True, help="Comment body text")

    edit_parser = subparsers.add_parser("edit", help="Edit an existing comment")
    edit_parser.add_argument("--key", required=True, help="Issue key")
    edit_parser.add_argument("--comment-id", required=True, help="Comment ID")
    edit_parser.add_argument("--body", required=True, help="New comment body text")

    delete_parser = subparsers.add_parser("delete", help="Delete an existing comment")
    delete_parser.add_argument("--key", required=True, help="Issue key")
    delete_parser.add_argument("--comment-id", required=True, help="Comment ID")

    args = parser.parse_args()
    config = load_config(args.config)
    client = JiraClient(config)

    if args.command == "list":
        _handle_list(client, args.key)
    elif args.command == "add":
        _handle_add(client, args.key, args.body)
    elif args.command == "edit":
        _handle_edit(client, args.key, args.comment_id, args.body)
    elif args.command == "delete":
        _handle_delete(client, args.key, args.comment_id)


if __name__ == "__main__":
    main()
