#!/usr/bin/env python3
"""
Update fields on an existing Jira issue.

Supports named flags for common fields (--status, --priority, --assignee,
--component, --fix-version) that resolve values from the field_catalog
in .jira.json. Status changes use the Jira workflow transitions API.

The generic --set flag can set ANY discovered field by friendly name:
    --set "priority=High" --set "story_points=3" --set "components=Backend"

Usage:
    python update_ticket.py --config .jira.json --key API-123 --summary "New title"
    python update_ticket.py --config .jira.json --key API-123 --status "In Progress"
    python update_ticket.py --config .jira.json --key API-123 --priority "High"
    python update_ticket.py --config .jira.json --key API-123 --set "priority=High"
    python update_ticket.py --config .jira.json --key API-123 --set "components=Backend"
    python update_ticket.py --config .jira.json --key API-123 --assignee "user@example.com"
    python update_ticket.py --config .jira.json --key API-123 --component "Backend"
    python update_ticket.py --config .jira.json --key API-123 --fix-version "1.0"
    python update_ticket.py --config .jira.json --key API-123 --story-points 5
    python update_ticket.py --config .jira.json --key API-123 --fields '{"labels": ["urgent"]}'
    python update_ticket.py --config .jira.json --key API-123 --comment "This is done."
    python update_ticket.py --config .jira.json --key API-123 --link "Blocks:API-456"
    python update_ticket.py --config .jira.json --key API-123 --link "is blocked by:API-456"
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import add_config_arg, load_config, normalize_args
from field_resolver import (
    add_common_field_args,
    build_update_fields,
    resolve_sprint_id,
)
from workflow_ops import handle_status_transition, upload_attachments
from jira_client import JiraClient


def _handle_sprint(client, issue_key, sprint_value, config):
    """Resolve and move an issue into a sprint via the Agile API."""
    sprint_id, sprint_name = resolve_sprint_id(config, sprint_value)
    if sprint_id is None:
        print(
            f"ERROR: Could not resolve sprint '{sprint_value}'. "
            "Run discover_fields.py --all --apply to discover available sprints, "
            "or pass a numeric sprint ID.",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        client.move_issues_to_sprint(sprint_id, [issue_key])
        print(f"Moved {issue_key} to sprint: {sprint_name} (id={sprint_id})")
    except Exception:
        sys.exit(1)


def _print_dry_run(key, fields, status, sprint, config, attachments):
    """Print dry-run summary without making API calls."""
    if fields:
        print(f"DRY RUN \u2014 would update {key} with fields:")
        print(json.dumps(fields, indent=2))
    if status:
        print(f"DRY RUN \u2014 would transition {key} to status: {status}")
    if sprint:
        sid, sname = resolve_sprint_id(config, sprint)
        print(f"DRY RUN \u2014 would move {key} to sprint: {sname} (id={sid})")
    if attachments:
        print(f"Attachments: {', '.join(attachments)}")


def main():
    parser = argparse.ArgumentParser(description="Update a Jira issue")
    add_config_arg(parser)
    parser.add_argument("--key", required=True, help="Issue key (e.g. API-123)")
    parser.add_argument("--summary", help="New summary/title")
    parser.add_argument(
        "--comment",
        help="Add a comment to the issue",
    )
    parser.add_argument(
        "--link",
        action="append",
        metavar="TYPE:TARGET_KEY",
        help="Link this issue to another. Format: 'Blocks:API-456' or "
             "'is blocked by:API-456'. Can be repeated.",
    )
    add_common_field_args(parser)
    args = parser.parse_args(normalize_args())

    config = load_config(args.config)
    fields, status_from_set = build_update_fields(args, config)

    effective_status = args.status or status_from_set
    effective_sprint = getattr(args, "sprint", None)

    links = args.link or []

    has_work = (
        fields or effective_status or effective_sprint
        or args.attachment or args.comment or links
    )
    if not has_work:
        print("ERROR: No fields, status, sprint, attachments, comment, or links specified.")
        sys.exit(1)

    if args.dry_run:
        _print_dry_run(args.key, fields, effective_status, effective_sprint, config, args.attachment)
        if args.comment:
            print(f"DRY RUN \u2014 would add comment to {args.key}: {args.comment[:80]}...")
        for link_spec in links:
            print(f"DRY RUN \u2014 would add link to {args.key}: {link_spec}")
        return

    client = JiraClient(config)

    if fields:
        try:
            client.update_issue(args.key, fields)
            print(f"Updated {args.key}")
            print(f"  {client.browse_url(args.key)}")
        except Exception:
            sys.exit(1)

    if effective_status:
        handle_status_transition(client, args.key, effective_status, config)

    if effective_sprint:
        _handle_sprint(client, args.key, effective_sprint, config)

    upload_attachments(client, args.key, args.attachment)
    _handle_comment(client, args.key, args.comment)
    for link_spec in links:
        _handle_issue_link(client, args.key, link_spec)


def _handle_comment(client, issue_key, comment_text):
    """Add a comment to an issue if comment_text is provided."""
    if not comment_text:
        return
    try:
        client.add_comment(issue_key, comment_text)
        preview = comment_text[:80]
        suffix = "..." if len(comment_text) > 80 else ""
        print(f"  Added comment to {issue_key}: {preview}{suffix}")
    except Exception:
        print(f"  WARNING: Failed to add comment to {issue_key}", file=sys.stderr)


def _handle_issue_link(client, issue_key, link_spec):
    """Parse and create an issue link from a spec string.

    Format: "LinkType:TARGET_KEY" where the current issue is the inward side.
    Examples:
        "Blocks:API-456"           -> issue_key blocks API-456
        "is blocked by:API-456"    -> API-456 blocks issue_key (swap direction)
    """
    if ":" not in link_spec:
        print(
            f"ERROR: Invalid link format '{link_spec}'. "
            "Expected 'LinkType:TARGET_KEY' (e.g. 'Blocks:API-456').",
            file=sys.stderr,
        )
        return

    link_type_input, target_key = link_spec.split(":", 1)
    link_type_input = link_type_input.strip()
    target_key = target_key.strip()

    if not target_key:
        print(f"ERROR: No target key in link spec '{link_spec}'.", file=sys.stderr)
        return

    link_types = client.get_link_types()
    resolved_type = None
    is_inward = False

    link_lower = link_type_input.lower()
    for lt in link_types:
        if lt["name"].lower() == link_lower:
            resolved_type = lt["name"]
            break
        if lt.get("inward", "").lower() == link_lower:
            resolved_type = lt["name"]
            is_inward = True
            break
        if lt.get("outward", "").lower() == link_lower:
            resolved_type = lt["name"]
            break

    if not resolved_type:
        available = [f"{lt['name']} ({lt.get('inward', '')}/{lt.get('outward', '')})" for lt in link_types]
        print(
            f"ERROR: Unknown link type '{link_type_input}'. "
            f"Available: {', '.join(available)}",
            file=sys.stderr,
        )
        return

    try:
        if is_inward:
            client.add_issue_link(resolved_type, target_key, issue_key)
            print(f"  Linked: {target_key} --[{resolved_type}]--> {issue_key}")
        else:
            client.add_issue_link(resolved_type, issue_key, target_key)
            print(f"  Linked: {issue_key} --[{resolved_type}]--> {target_key}")
    except Exception:
        print(f"  WARNING: Failed to create link {link_spec}", file=sys.stderr)


if __name__ == "__main__":
    main()
