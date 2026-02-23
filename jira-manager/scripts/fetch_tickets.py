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
    lines.append(f"{'Key':<12} {'Type':<12} {'SP':>4}  {'Status':<14} Summary")
    lines.append("-" * 80)

    for issue in issues:
        key = issue["key"]
        fields = issue.get("fields", {})
        summary = fields.get("summary", "")[:40]
        itype = fields.get("issuetype", {}).get("name", "?")
        status = fields.get("status", {}).get("name", "?")
        sp = ""
        if sp_field and fields.get(sp_field) is not None:
            sp = str(fields[sp_field])
        lines.append(f"{key:<12} {itype:<12} {sp:>4}  {status:<14} {summary}")

    return "\n".join(lines)


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


def main():
    parser = argparse.ArgumentParser(description="Fetch Jira issues")
    parser.add_argument("--config", required=True, help="Path to .jira.json")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--key", help="Fetch a single issue by key")
    group.add_argument("--jql", help="Search using JQL query")
    group.add_argument("--children-of", help="Fetch children of an epic or story")

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

    config = load_config(args.config)
    client = JiraClient(config)

    field_list = None
    if args.fields:
        field_list = [f.strip() for f in args.fields.split(",")]

    convert = not args.no_convert

    if args.key:
        _handle_key(client, config, args.key, args.format, field_list, convert)
    elif args.jql:
        _handle_jql(client, config, args.jql, args.format, field_list, args.max_results, convert)
    elif args.children_of:
        _handle_children(client, config, args.children_of, args.format, field_list, convert)


if __name__ == "__main__":
    main()
