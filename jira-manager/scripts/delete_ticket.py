#!/usr/bin/env python3
"""
Delete a Jira issue by key.

Always requires explicit confirmation or --dry-run first.

Usage:
    python delete_ticket.py --config .jira.json --key API-123 --dry-run
    python delete_ticket.py --config .jira.json --key API-123 --confirm
    python delete_ticket.py --config .jira.json --key API-123 --confirm --delete-subtasks
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import add_config_arg, load_config, load_manifest, save_manifest
from jira_client import JiraClient


def _print_issue_details(issue, delete_subtasks_flag):
    """Print issue summary and subtask status."""
    fields = issue.get("fields", {})
    summary = fields.get("summary", "?")
    itype = fields.get("issuetype", {}).get("name", "?")
    status = fields.get("status", {}).get("name", "?")

    # Check for subtasks
    subtasks = fields.get("subtasks", [])
    subtask_info = ""
    if subtasks:
        subtask_keys = [st["key"] for st in subtasks]
        subtask_info = f"\n  Subtasks: {', '.join(subtask_keys)}"
        if not delete_subtasks_flag:
            subtask_info += " (will NOT be deleted unless --delete-subtasks is used)"

    print(f"Issue:       {issue['key']}")
    print(f"Summary:     {summary}")
    print(f"Type:        {itype}")
    print(f"Status:      {status}")
    if subtask_info:
        print(subtask_info)
    
    return summary


def _cleanup_manifest(config, key):
    """Remove the deleted key from the manifest."""
    manifest = load_manifest(config)
    changed = False
    
    for category in ("stories", "subtasks", "epic"):
        if not isinstance(manifest.get(category), dict):
            continue
            
        # Collect keys to remove first to avoid modifying during iteration
        to_remove = []
        for mid, mdata in manifest[category].items():
            if isinstance(mdata, dict) and mdata.get("key") == key:
                to_remove.append(mid)
        
        for mid in to_remove:
            del manifest[category][mid]
            print(f"  Removed from manifest: {category}/{mid}")
            changed = True

    if changed:
        save_manifest(config, manifest)


def main():
    parser = argparse.ArgumentParser(description="Delete a Jira issue")
    add_config_arg(parser)
    parser.add_argument("--key", required=True, help="Issue key to delete (e.g. API-123)")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm deletion (required to actually delete)",
    )
    parser.add_argument(
        "--delete-subtasks",
        action="store_true",
        help="Also delete subtasks of the issue",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without making API calls",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    client = JiraClient(config)

    # Fetch issue details first
    try:
        issue = client.get_issue(args.key)
    except Exception:
        print(f"ERROR: Could not fetch issue {args.key}")
        sys.exit(1)

    summary = _print_issue_details(issue, args.delete_subtasks)

    if args.dry_run:
        print("\nDRY RUN — no changes made.")
        return

    if not args.confirm:
        print("\nERROR: Deletion requires --confirm flag. Use --dry-run to preview.")
        sys.exit(1)

    # Perform deletion
    try:
        client.delete_issue(args.key, delete_subtasks=args.delete_subtasks)
        print(f"\nDeleted {args.key}: {summary}")
    except Exception:
        sys.exit(1)

    # Clean up manifest
    _cleanup_manifest(config, args.key)


if __name__ == "__main__":
    main()
