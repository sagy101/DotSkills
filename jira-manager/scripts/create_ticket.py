#!/usr/bin/env python3
"""
Create a single Jira issue.

Usage:
    python create_ticket.py --config .jira.json --type story --summary "My Story" --description "Details"
    python create_ticket.py --config .jira.json --type subtask --summary "Sub" --parent API-123
    python create_ticket.py --config .jira.json --type story --summary "S" --epic API-100 --story-points 3
    python create_ticket.py --config .jira.json --type story --summary "S" --description-file desc.md --rewrite-links
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import load_config, load_manifest, save_manifest
from jira_client import JiraClient
from link_rewriter import rewrite_links_to_git
from markup_converter import md_to_jira_markup


def _add_description(fields, args, config):
    """Add description field if provided."""
    description = args.description or ""
    if args.description_file:
        description = Path(args.description_file).read_text(encoding="utf-8")
    if args.rewrite_links and description:
        description = rewrite_links_to_git(description, config)
    if description and not args.no_convert:
        description = md_to_jira_markup(description)
    if description:
        fields["description"] = description


def _add_optional_fields(fields, args, config):
    """Add optional fields like epic link, story points, labels."""
    # Epic link
    if args.epic:
        epic_field = config.get_field_id("epic_link")
        if epic_field:
            fields[epic_field] = args.epic
        else:
            print(
                "WARNING: epic_link field not configured. "
                "Run discover_fields.py --apply to detect it.",
                file=sys.stderr,
            )

    # Story points
    if args.story_points is not None:
        sp_field = config.get_field_id("story_points")
        if sp_field:
            fields[sp_field] = args.story_points
        else:
            print(
                "WARNING: story_points field not configured. "
                "Run discover_fields.py --apply to detect it.",
                file=sys.stderr,
            )

    # Labels
    if args.labels:
        fields["labels"] = [l.strip() for l in args.labels.split(",")]


def build_fields(args, config):
    """Build the Jira fields dict from CLI arguments."""
    fields = {
        "project": {"key": config.project_key},
        "summary": args.summary,
    }

    # Issue type
    type_id = config.get_issue_type_id(args.type)
    if type_id:
        fields["issuetype"] = {"id": type_id}
    else:
        fields["issuetype"] = {"name": args.type.capitalize()}

    _add_description(fields, args, config)

    # Parent (for subtasks)
    if args.parent:
        fields["parent"] = {"key": args.parent}

    _add_optional_fields(fields, args, config)

    # Extra fields (raw JSON)
    if args.fields:
        extra = json.loads(args.fields)
        fields.update(extra)

    return fields


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


def _upload_attachments(client, key, file_paths):
    """Upload attachment files to an issue."""
    for fpath in file_paths:
        try:
            attached = client.add_attachment(key, fpath)
            for a in attached:
                print(f"  Attached: {a.get('filename', fpath)}")
        except Exception:
            print(f"  WARNING: Failed to attach {fpath}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Create a Jira issue")
    parser.add_argument("--config", required=True, help="Path to .jira.json")
    parser.add_argument(
        "--type",
        required=True,
        help="Issue type: story, subtask, bug, task, epic, or custom name",
    )
    parser.add_argument("--summary", required=True, help="Issue summary/title")
    parser.add_argument("--description", help="Issue description text")
    parser.add_argument("--description-file", help="Read description from file")
    parser.add_argument("--parent", help="Parent issue key (for subtasks)")
    parser.add_argument("--epic", help="Epic key to link to")
    parser.add_argument("--story-points", type=float, help="Story points value")
    parser.add_argument("--labels", help="Comma-separated labels")
    parser.add_argument(
        "--fields", help='Extra fields as JSON: \'{"customfield_123": "val"}\''
    )
    parser.add_argument(
        "--rewrite-links",
        action="store_true",
        help="Rewrite relative markdown links to git browse URLs in description",
    )
    parser.add_argument(
        "--manifest-id",
        help="ID to track this ticket in the manifest (e.g. '1' for story 1, '1.1' for subtask)",
    )
    parser.add_argument(
        "--attachment",
        action="append",
        default=[],
        help="File to attach to the issue (can be repeated)",
    )
    parser.add_argument(
        "--no-convert",
        action="store_true",
        help="Skip Markdown to Jira wiki markup conversion for description",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without making API calls",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    fields = build_fields(args, config)

    if args.dry_run:
        print("DRY RUN — would create issue with fields:")
        print(json.dumps(fields, indent=2))
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

    if args.manifest_id:
        _update_manifest(config, args, key)

    if args.attachment:
        _upload_attachments(client, key, args.attachment)

    # Output JSON for script chaining
    print(json.dumps({"key": key, "self": result.get("self", "")}))


if __name__ == "__main__":
    main()
