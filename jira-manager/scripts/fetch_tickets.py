#!/usr/bin/env python3
"""
Fetch Jira issues by key, JQL query, or parent relationship.

Usage:
    python fetch_tickets.py --config .jira.json --key API-123
    python fetch_tickets.py --config .jira.json --jql "project=API AND type=Story"
    python fetch_tickets.py --config .jira.json --children-of API-8291
    python fetch_tickets.py --config .jira.json --children-of API-8291 --format table
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import load_config
from jira_client import JiraClient
from markup_converter import jira_markup_to_md


def format_issue_table(issues, config):
    """Format issues as a readable table."""
    sp_field = config.get_field_id("story_points")

    lines = []
    lines.append(f"{'Key':<12} {'Type':<12} {'SP':>4}  {'Status':<14} {'Sprint':<20} Summary")
    lines.append("-" * 100)

    for issue in issues:
        key = issue["key"]
        fields = issue.get("fields", {})
        summary = fields.get("summary", "")[:40]
        itype = fields.get("issuetype", {}).get("name", "?")
        status = fields.get("status", {}).get("name", "?")
        sp = ""
        if sp_field and fields.get(sp_field) is not None:
            sp = str(fields[sp_field])
        sprint = _extract_sprint_name(fields, config) or ""
        if len(sprint) > 18:
            sprint = sprint[:17] + "\u2026"
        lines.append(f"{key:<12} {itype:<12} {sp:>4}  {status:<14} {sprint:<20} {summary}")

    return "\n".join(lines)


def _extract_sprint_from_value(sprint_data):
    """Parse a sprint value which may be a dict, list, or legacy string."""
    if isinstance(sprint_data, dict):
        return sprint_data.get("name")
    if isinstance(sprint_data, list) and sprint_data:
        return _extract_sprint_from_value(sprint_data[-1])
    if isinstance(sprint_data, str) and "name=" in sprint_data:
        for part in sprint_data.split(","):
            if part.strip().startswith("name="):
                return part.strip().split("=", 1)[1]
    return None


def _extract_sprint_name(fields, config):
    """Extract sprint name from issue fields (standard API sprint custom field)."""
    sprint_field = config.get_field_id("sprint")
    if not sprint_field:
        return None
    return _extract_sprint_from_value(fields.get(sprint_field))


def format_issue_detail(issue, config, convert_markup=True):
    """Format a single issue with full details."""
    sp_field = config.get_field_id("story_points")
    fields = issue.get("fields", {})

    lines = []
    lines.append(f"Key:         {issue['key']}")
    lines.append(f"Summary:     {fields.get('summary', '')}")
    lines.append(f"Type:        {fields.get('issuetype', {}).get('name', '?')}")
    lines.append(f"Status:      {fields.get('status', {}).get('name', '?')}")
    lines.append(f"Priority:    {fields.get('priority', {}).get('name', '?')}")

    if sp_field and fields.get(sp_field) is not None:
        lines.append(f"Story Pts:   {fields[sp_field]}")

    sprint_name = _extract_sprint_name(fields, config)
    if sprint_name:
        lines.append(f"Sprint:      {sprint_name}")

    labels = fields.get("labels", [])
    if labels:
        lines.append(f"Labels:      {', '.join(labels)}")

    assignee = fields.get("assignee")
    if assignee:
        lines.append(f"Assignee:    {assignee.get('displayName', '?')}")

    parent = fields.get("parent")
    if parent:
        lines.append(f"Parent:      {parent['key']} - {parent.get('fields', {}).get('summary', '')}")

    desc = fields.get("description", "")
    if desc:
        if convert_markup:
            desc = jira_markup_to_md(desc)
        lines.append(f"\nDescription:\n{desc[:2000]}")
        if len(desc) > 2000:
            lines.append(f"  ... (truncated, {len(desc)} chars total)")

    return "\n".join(lines)


def _handle_key(client, config, key, format_type, fields, convert=True):
    try:
        issue = client.get_issue(key, fields=fields)
        if format_type == "json":
            print(json.dumps(issue, indent=2))
        elif format_type == "detail":
            print(format_issue_detail(issue, config, convert_markup=convert))
        else:
            print(format_issue_table([issue], config))
    except Exception:
        sys.exit(1)


def _handle_jql(client, config, jql, format_type, fields, max_results, convert=True):
    try:
        result = client.search_jql(
            jql, fields=fields, max_results=max_results
        )
        issues = result.get("issues", [])
        total = result.get("total", 0)

        if format_type == "json":
            print(json.dumps(issues, indent=2))
        elif format_type == "detail":
            for issue in issues:
                print(format_issue_detail(issue, config, convert_markup=convert))
                print("-" * 40)
            if total > len(issues):
                print(f"\nShowing {len(issues)} of {total} results")
        else:
            print(format_issue_table(issues, config))
            if total > len(issues):
                print(f"\nShowing {len(issues)} of {total} results")
    except Exception:
        sys.exit(1)


def _handle_children(client, config, parent_key, format_type, fields, convert=True):
    try:
        issues = client.get_children(parent_key, fields=fields)

        if format_type == "json":
            print(json.dumps(issues, indent=2))
        elif format_type == "detail":
            for issue in issues:
                print(format_issue_detail(issue, config, convert_markup=convert))
                print("-" * 40)
        else:
            print(f"Children of {parent_key}:")
            print(format_issue_table(issues, config))
            print(f"\nTotal: {len(issues)}")
    except Exception:
        sys.exit(1)


def _build_filter_jql(args, config):
    """Build a JQL query from --filter key=value pairs."""
    clauses = [f"project = {config.project_key}"]
    for pair in args.filter:
        if "=" not in pair:
            print(f"ERROR: --filter must be 'field=value', got: {pair}", file=sys.stderr)
            sys.exit(1)
        field, _, value = pair.partition("=")
        field = field.strip()
        value = value.strip()
        clauses.append(f'{field} = "{value}"')
    return " AND ".join(clauses) + " ORDER BY key ASC"


def _handle_boards(client, fmt):
    """List Agile boards for the project."""
    boards = client.get_boards()
    if fmt == "json":
        print(json.dumps(boards, indent=2))
        return
    if not boards:
        print("No boards found for this project.")
        return
    print(f"{'ID':<8} {'Type':<12} Name")
    print("-" * 50)
    for b in boards:
        print(f"{b['id']:<8} {b.get('type', '?'):<12} {b.get('name', '?')}")
    print(f"\nTotal: {len(boards)}")


def main():
    parser = argparse.ArgumentParser(description="Fetch Jira issues")
    parser.add_argument("--config", required=True, help="Path to .jira.json")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--key", help="Fetch a single issue by key")
    group.add_argument("--jql", help="Search using JQL query")
    group.add_argument("--children-of", help="Fetch children of an epic or story")
    group.add_argument(
        "--filter",
        action="append",
        nargs="+",
        help="Filter tickets by field=value pairs (e.g. --filter assignee=me status='In Progress')",
    )
    group.add_argument(
        "--boards",
        action="store_true",
        help="List Agile boards for the project",
    )

    parser.add_argument(
        "--format",
        choices=["json", "table", "detail"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=50,
        help="Maximum results for JQL queries (default: 50)",
    )
    parser.add_argument(
        "--fields",
        help="Comma-separated list of fields to fetch",
    )
    parser.add_argument(
        "--no-convert",
        action="store_true",
        help="Skip Jira wiki markup to Markdown conversion for descriptions",
    )
    args = parser.parse_args()

    # Flatten --filter lists into a single list of key=value pairs
    if args.filter:
        args.filter = [item for sublist in args.filter for item in sublist]

    config = load_config(args.config)
    client = JiraClient(config)

    field_list = None
    if args.fields:
        field_list = [f.strip() for f in args.fields.split(",")]

    convert = not args.no_convert

    if args.boards:
        _handle_boards(client, args.format)
    elif args.key:
        _handle_key(client, config, args.key, args.format, field_list, convert)
    elif args.jql:
        _handle_jql(client, config, args.jql, args.format, field_list, args.max_results, convert)
    elif args.children_of:
        _handle_children(client, config, args.children_of, args.format, field_list, convert)
    elif args.filter:
        jql = _build_filter_jql(args, config)
        _handle_jql(client, config, jql, args.format, field_list, args.max_results, convert)


if __name__ == "__main__":
    main()
