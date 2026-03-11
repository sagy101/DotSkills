#!/usr/bin/env python3
"""
Create a single Jira issue.

Supports named flags for common fields (--status, --priority, --assignee,
--component, --fix-version) and a generic --set flag for ANY discovered field.
Status is applied as a post-create transition.

Usage:
    python create_ticket.py --config .jira.json --type story --summary "My Story" --description "Details"
    python create_ticket.py --config .jira.json --type subtask --summary "Sub" --parent API-123
    python create_ticket.py --config .jira.json --type story --summary "S" --epic API-100 --story-points 3
    python create_ticket.py --config .jira.json --type story --summary "S" --status "In Progress"
    python create_ticket.py --config .jira.json --type story --summary "S" --set "priority=High"
    python create_ticket.py --config .jira.json --type story --summary "S" --description-file desc.md --rewrite-links
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import add_config_arg, load_config, load_manifest, normalize_args, save_manifest
from field_resolver import (
    add_common_field_args,
    apply_extra_fields,
    apply_named_fields,
    apply_set_pairs,
    resolve_description,
    resolve_issue_type,
    resolve_sprint_id,
    validate_required_fields,
)
from workflow_ops import handle_status_transition, upload_attachments
from jira_client import JiraClient


def _add_epic_link(fields, args, config):
    """Add epic link field if --epic was provided."""
    if not args.epic:
        return
    epic_field = config.get_field_id("epic_link")
    if epic_field:
        fields[epic_field] = args.epic
    else:
        print(
            "WARNING: epic_link field not configured. "
            "Run discover_fields.py --apply to detect it.",
            file=sys.stderr,
        )


def build_fields(args, config):
    """Build the Jira fields dict from CLI arguments.

    Returns (fields_dict, status_value_or_None).
    """
    fields = {
        "project": {"key": config.project_key},
        "summary": args.summary,
    }

    fields["issuetype"] = resolve_issue_type(config, args.type)

    # Description (for create, default to empty string so None means "not provided")
    description = args.description or ""
    if args.description_file:
        description = Path(args.description_file).read_text(encoding="utf-8")
    if description:
        # Temporarily set args.description for resolve_description compatibility
        orig = args.description
        args.description = description
        resolved = resolve_description(args, config)
        args.description = orig
        if resolved:
            fields["description"] = resolved

    # Parent (for subtasks)
    if args.parent:
        fields["parent"] = {"key": args.parent}

    _add_epic_link(fields, args, config)
    apply_named_fields(fields, args, config)
    status_from_set = apply_set_pairs(fields, args, config)
    apply_extra_fields(fields, args)

    return fields, status_from_set


def _update_manifest(config, args, key):
    """Update the manifest file with the newly created ticket."""
    manifest = load_manifest(config)
    category = "subtasks" if args.parent else "stories"
    if category not in manifest:
        manifest[category] = {}
    entry = {"key": key, "summary": args.summary}
    if args.story_points is not None:
        entry["story_points"] = args.story_points
    if args.parent:
        entry["parent_key"] = args.parent
    manifest[category][args.manifest_id] = entry
    save_manifest(config, manifest)
    print(f"  Manifest updated: {category}/{args.manifest_id} = {key}")


def main():
    parser = argparse.ArgumentParser(description="Create a Jira issue")
    add_config_arg(parser)
    parser.add_argument(
        "--type",
        required=True,
        help="Issue type: story, subtask, bug, task, epic, or custom name",
    )
    parser.add_argument("--summary", required=True, help="Issue summary/title")
    parser.add_argument("--parent", help="Parent issue key (for subtasks)")
    parser.add_argument("--epic", help="Epic key to link to")
    parser.add_argument(
        "--manifest-id",
        help="ID to track this ticket in the manifest (e.g. '1' for story 1, '1.1' for subtask)",
    )
    add_common_field_args(parser)
    args = parser.parse_args(normalize_args())

    config = load_config(args.config)
    fields, status_from_set = build_fields(args, config)
    effective_status = args.status or status_from_set

    missing = validate_required_fields(config, args.type, fields)
    if missing:
        print(f"ERROR: Missing required fields for issue type "
              f"'{args.type}':", file=sys.stderr)
        for mf in missing:
            fid = mf["id"]
            fname = mf["name"]
            hint = '--set "{}=<value>"'.format(fname)
            print(f"  - {fname} ({fid})  → {hint}", file=sys.stderr)
        print("\nRun discover_fields.py --apply to refresh required fields.",
              file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print("DRY RUN — would create issue with fields:")
        print(json.dumps(fields, indent=2))
        if effective_status:
            print(f"DRY RUN — would transition to status: {effective_status}")
        if args.attachment:
            print(f"Attachments: {', '.join(args.attachment)}")
        return

    client = JiraClient(config)

    try:
        result = client.create_issue(fields)
    except Exception:
        sys.exit(1)

    key = result["key"]
    print(f"Created {key}: {args.summary}")
    print(f"  {client.browse_url(key)}")

    # Post-create transition
    if effective_status:
        handle_status_transition(client, key, effective_status, config, warn_only=True)

    # Post-create sprint move
    effective_sprint = getattr(args, "sprint", None)
    if effective_sprint:
        sprint_id, sprint_name = resolve_sprint_id(config, effective_sprint)
        if sprint_id is not None:
            try:
                client.move_issues_to_sprint(sprint_id, [key])
                print(f"  Moved {key} to sprint: {sprint_name} (id={sprint_id})")
            except Exception:
                print(f"  WARNING: Failed to move {key} to sprint {sprint_name}", file=sys.stderr)

    if args.manifest_id:
        _update_manifest(config, args, key)

    upload_attachments(client, key, args.attachment)

    # Output JSON for script chaining
    print(json.dumps({"key": key, "self": result.get("self", "")}))


if __name__ == "__main__":
    main()
