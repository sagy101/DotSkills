#!/usr/bin/env python3
"""
Update fields on an existing Jira issue.

Usage:
    python update_ticket.py --config .jira.json --key API-123 --summary "New title"
    python update_ticket.py --config .jira.json --key API-123 --description-file desc.md --rewrite-links
    python update_ticket.py --config .jira.json --key API-123 --story-points 5
    python update_ticket.py --config .jira.json --key API-123 --fields '{"labels": ["urgent"]}'
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import load_config
from jira_client import JiraClient
from link_rewriter import rewrite_links_to_git
from markup_converter import md_to_jira_markup


def _build_description(args, config):
    """Resolve and transform the description from CLI args."""
    description = args.description
    if args.description_file:
        description = Path(args.description_file).read_text(encoding="utf-8")
    if description is None:
        return None
    if args.rewrite_links:
        description = rewrite_links_to_git(description, config)
    if not args.no_convert:
        description = md_to_jira_markup(description)
    return description


def _build_update_fields(args, config):
    """Build the fields dict from CLI arguments."""
    fields = {}

    if args.summary:
        fields["summary"] = args.summary

    description = _build_description(args, config)
    if description is not None:
        fields["description"] = description

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

    if args.labels:
        fields["labels"] = [l.strip() for l in args.labels.split(",")]

    if args.fields:
        extra = json.loads(args.fields)
        fields.update(extra)

    return fields


def main():
    parser = argparse.ArgumentParser(description="Update a Jira issue")
    parser.add_argument("--config", required=True, help="Path to .jira.json")
    parser.add_argument("--key", required=True, help="Issue key (e.g. API-123)")
    parser.add_argument("--summary", help="New summary/title")
    parser.add_argument("--description", help="New description text")
    parser.add_argument("--description-file", help="Read new description from file")
    parser.add_argument("--story-points", type=float, help="New story points value")
    parser.add_argument("--labels", help="Comma-separated labels (replaces existing)")
    parser.add_argument(
        "--fields", help='Extra fields as JSON: \'{"customfield_123": "val"}\''
    )
    parser.add_argument(
        "--rewrite-links",
        action="store_true",
        help="Rewrite relative markdown links to git browse URLs in description",
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
        help="Show what would be updated without making API calls",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    fields = _build_update_fields(args, config)

    if not fields and not args.attachment:
        print("ERROR: No fields or attachments specified to update.")
        sys.exit(1)

    if args.dry_run:
        if fields:
            print(f"DRY RUN — would update {args.key} with fields:")
            print(json.dumps(fields, indent=2))
        if args.attachment:
            print(f"Attachments: {', '.join(args.attachment)}")
        return

    client = JiraClient(config)

    if fields:
        try:
            client.update_issue(args.key, fields)
            print(f"Updated {args.key}")
            print(f"  {client.browse_url(args.key)}")
        except Exception:
            sys.exit(1)

    for fpath in args.attachment:
        try:
            attached = client.add_attachment(args.key, fpath)
            for a in attached:
                print(f"  Attached: {a.get('filename', fpath)}")
        except Exception:
            print(f"  WARNING: Failed to attach {fpath}", file=sys.stderr)


if __name__ == "__main__":
    main()
