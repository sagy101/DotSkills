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
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import load_config
from field_resolver import (
    add_common_field_args,
    apply_extra_fields,
    apply_named_fields,
    apply_set_pairs,
    handle_status_transition,
    resolve_description,
    resolve_sprint_id,
    upload_attachments,
)
from jira_client import JiraClient


def _build_update_fields(args, config):
    """Build the fields dict from CLI arguments."""
    fields = {}

    if args.summary:
        fields["summary"] = args.summary

    description = resolve_description(args, config)
    if description is not None:
        fields["description"] = description

    apply_named_fields(fields, args, config)
    status_from_set = apply_set_pairs(fields, args, config)
    apply_extra_fields(fields, args)

    return fields, status_from_set


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
    parser.add_argument("--config", required=True, help="Path to .jira.json")
    parser.add_argument("--key", required=True, help="Issue key (e.g. API-123)")
    parser.add_argument("--summary", help="New summary/title")
    add_common_field_args(parser)
    args = parser.parse_args()

    config = load_config(args.config)
    fields, status_from_set = _build_update_fields(args, config)

    effective_status = args.status or status_from_set
    effective_sprint = getattr(args, "sprint", None)

    if not fields and not effective_status and not effective_sprint and not args.attachment:
        print("ERROR: No fields, status, sprint, or attachments specified to update.")
        sys.exit(1)

    if args.dry_run:
        _print_dry_run(args.key, fields, effective_status, effective_sprint, config, args.attachment)
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


if __name__ == "__main__":
    main()
