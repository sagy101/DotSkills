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
    resolve_description,
    resolve_transition,
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


def main():
    parser = argparse.ArgumentParser(description="Update a Jira issue")
    parser.add_argument("--config", required=True, help="Path to .jira.json")
    parser.add_argument("--key", required=True, help="Issue key (e.g. API-123)")
    parser.add_argument("--summary", help="New summary/title")
    add_common_field_args(parser)
    args = parser.parse_args()

    config = load_config(args.config)
    fields, status_from_set = _build_update_fields(args, config)

    # Merge status from --set with explicit --status flag (--status takes precedence)
    effective_status = args.status or status_from_set

    if not fields and not effective_status and not args.attachment:
        print("ERROR: No fields, status, or attachments specified to update.")
        sys.exit(1)

    if args.dry_run:
        if fields:
            print(f"DRY RUN — would update {args.key} with fields:")
            print(json.dumps(fields, indent=2))
        if effective_status:
            print(f"DRY RUN — would transition {args.key} to status: {effective_status}")
        if args.attachment:
            print(f"Attachments: {', '.join(args.attachment)}")
        return

    client = JiraClient(config)

    # Update fields first (before transition)
    if fields:
        try:
            client.update_issue(args.key, fields)
            print(f"Updated {args.key}")
            print(f"  {client.browse_url(args.key)}")
        except Exception:
            sys.exit(1)

    # Handle status transition
    if effective_status:
        result = resolve_transition(client, args.key, effective_status, config)
        if result is None:
            available = client.get_transitions(args.key)
            names = [
                f"{t['to']['name']}" for t in available
                if "to" in t
            ]
            print(
                f"ERROR: No transition found to status '{effective_status}' for {args.key}.",
                file=sys.stderr,
            )
            print(
                f"  Available target statuses: {', '.join(names) if names else '(none)'}",
                file=sys.stderr,
            )
            sys.exit(1)

        transition_id, transition_name, target_name = result
        try:
            client.transition_issue(args.key, transition_id)
            print(f"Transitioned {args.key} -> {target_name} (via '{transition_name}')")
        except Exception:
            sys.exit(1)

    # Attachments
    upload_attachments(client, args.key, args.attachment)


if __name__ == "__main__":
    main()
