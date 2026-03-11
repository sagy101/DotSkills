#!/usr/bin/env python3
"""
Bulk update Jira issues based on a list of keys, board ID, JQL, or filters.

Usage:
    python bulk_update.py --config .jira.json --tickets "PROJ-1,PROJ-2" --status "Done"
    python bulk_update.py --config .jira.json --board-id 123 --sprint "Sprint 5"
    python bulk_update.py --config .jira.json --filter "status=In Progress" --assignee "me"
    python bulk_update.py --config .jira.json --jql "project=PROJ AND priority=High" --priority "Medium"
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
from issue_selector import select_issues
from workflow_ops import handle_status_transition, upload_attachments
from jira_client import JiraClient


def _print_dry_run_summary(
    issues: list[dict],
    fields: dict,
    status: str | None,
    sprint: str | None,
    config,
    attachments: list[str],
) -> None:
    """Print a summary of what would be updated."""
    print("\nBULK UPDATE PREVIEW")
    print("=" * 60)
    print(f"Target issues: {len(issues)}")
    
    if fields:
        print("\nFields to update:")
        print(json.dumps(fields, indent=2))
    
    if status:
        print(f"\nTarget status: {status}")
        
    if sprint:
        sid, sname = resolve_sprint_id(config, sprint)
        print(f"\nTarget sprint: {sname} (id={sid})")
        
    if attachments:
        print(f"\nAttachments: {', '.join(attachments)}")
        
    print("\nIssues to be modified:")
    print(f"{'Key':<10} {'Status':<15} Summary")
    print("-" * 60)
    for i in issues[:20]:
        fields_data = i.get("fields", {})
        print(f"{i['key']:<10} {fields_data.get('status', {}).get('name', '?'):<15} {fields_data.get('summary', '')[:50]}")
    
    if len(issues) > 20:
        print(f"... and {len(issues) - 20} more.")
    print("=" * 60)


def _update_single_issue(
    client,
    key: str,
    fields: dict,
    status: str | None,
    sprint_id: int | None,
    attachments: list[str],
    config,
) -> bool:
    """Apply all updates to a single issue. Returns True on full success."""
    ok = True
    if fields:
        client.update_issue(key, fields)
    if status:
        if not handle_status_transition(client, key, status, config, warn_only=True):
            ok = False
    if sprint_id:
        client.move_issues_to_sprint(sprint_id, [key])
    if attachments and not upload_attachments(client, key, attachments):
        ok = False
    return ok


def execute_bulk_updates(
    client,
    issues: list[dict],
    fields: dict,
    status: str | None,
    sprint_val: str | None,
    attachments: list[str],
    config,
) -> None:
    """Execute updates for a list of issues."""
    print(f"\nUpdating {len(issues)} issues...")
    success_count = 0
    fail_count = 0

    sprint_id = None
    if sprint_val:
        sprint_id, _ = resolve_sprint_id(config, sprint_val)
        if not sprint_id:
            print(f"ERROR: Could not resolve sprint '{sprint_val}'", file=sys.stderr)
            sys.exit(1)

    for issue in issues:
        key = issue["key"]
        try:
            if _update_single_issue(client, key, fields, status, sprint_id, attachments, config):
                print(f"Updated {key}")
                success_count += 1
            else:
                print(f"PARTIAL update {key} (status transition failed)", file=sys.stderr)
                fail_count += 1
        except Exception as e:
            print(f"FAILED to update {key}: {e}", file=sys.stderr)
            fail_count += 1

    print(f"\nDone. Success: {success_count}, Failed: {fail_count}")


def main():
    parser = argparse.ArgumentParser(description="Bulk update Jira issues")
    add_config_arg(parser)
    
    # Selection arguments
    # We use manual validation to allow combining board-id with filters
    parser.add_argument("--tickets", help="Comma-separated list of issue keys (PROJ-1,PROJ-2)")
    parser.add_argument("--board-id", type=int, help="Agile board ID")
    parser.add_argument("--jql", help="JQL query string")
    parser.add_argument("--filter", action="append", nargs="+", help="Field filters (key=value)")
    parser.add_argument(
        "--board-all",
        action="store_true",
        dest="fetch_all",
        help="With --board-id: update all board issues instead of only the active sprint",
    )
    
    # Update arguments
    add_common_field_args(parser)
    
    parser.add_argument(
        "--confirm", 
        action="store_true", 
        help="Execute the updates (default is dry-run)"
    )
    
    args = parser.parse_args(normalize_args())
    
    # Flatten filters
    if args.filter:
        args.filter = [item for sublist in args.filter for item in sublist]

    # Validate selection arguments
    # Count how many primary selection methods are used
    primary_modes = sum(1 for x in [args.tickets, args.board_id, args.jql] if x is not None)
    
    # If filter is used without any of the above, it counts as a mode (Project Search)
    if primary_modes == 0 and not args.filter:
        parser.error("Must provide a selection method: --tickets, --board-id, --jql, or --filter")
        
    if primary_modes > 1:
        parser.error("Conflicting options: provide only one of --tickets, --board-id, or --jql")

    config = load_config(args.config)
    client = JiraClient(config)
    
    # 1. Resolve Updates
    fields, status_from_set = build_update_fields(args, config)
    effective_status = args.status or status_from_set
    effective_sprint = getattr(args, "sprint", None)
    
    if not fields and not effective_status and not effective_sprint and not args.attachment:
        print("ERROR: No updates specified (fields, status, sprint, or attachments).")
        sys.exit(1)

    # 2. Fetch Issues
    issues = select_issues(
        client, config,
        tickets=args.tickets,
        board_id=args.board_id,
        jql=args.jql,
        filter_pairs=args.filter,
        fetch_all=getattr(args, "fetch_all", False),
        max_results=0,
        fields=["summary", "status", "issuetype"],
    )
    if not issues:
        print("No issues found matching the criteria.")
        sys.exit(0)
        
    # 3. Dry Run / Preview
    if not args.confirm:
        _print_dry_run_summary(issues, fields, effective_status, effective_sprint, config, args.attachment)
        print("\nTo execute these changes, run again with --confirm")
        return

    # 4. Execute Updates
    execute_bulk_updates(client, issues, fields, effective_status, effective_sprint, args.attachment, config)


if __name__ == "__main__":
    main()
