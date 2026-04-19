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
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jira_client import JiraClient
from jira_config_loader import JiraConfig, add_config_arg, load_config
from jql_builder import build_board_jql, build_jql_from_filters
from markup_converter import jira_markup_to_md


def format_issue_table(issues: list[dict[str, Any]], config: JiraConfig) -> str:
    """Format issues as a readable table."""
    sp_field = config.get_field_id("story_points")

    lines = []
    lines.append(
        f"{'Key':<12} {'Type':<12} {'SP':>4}  {'Priority':<12} {'Status':<14} {'Sprint':<20} Summary"
    )
    lines.append("-" * 116)

    for issue in issues:
        key = issue["key"]
        fields = issue.get("fields", {})
        summary = fields.get("summary", "")[:40]
        itype = fields.get("issuetype", {}).get("name", "?")
        status = fields.get("status", {}).get("name", "?")
        priority = fields.get("priority", {}).get("name", "?") if fields.get("priority") else "?"
        sp = ""
        if sp_field and fields.get(sp_field) is not None:
            sp = str(fields[sp_field])
        sprint = _extract_sprint_name(fields, config) or ""
        if len(sprint) > 18:
            sprint = sprint[:17] + "\u2026"
        lines.append(
            f"{key:<12} {itype:<12} {sp:>4}  {priority:<12} {status:<14} {sprint:<20} {summary}"
        )

    return "\n".join(lines)


def _extract_sprint_from_value(sprint_data: object) -> str | None:
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


def _extract_sprint_name(fields: dict[str, Any], config: JiraConfig) -> str | None:
    """Extract sprint name from issue fields (standard API sprint custom field)."""
    sprint_field = config.get_field_id("sprint")
    if not sprint_field:
        return None
    return _extract_sprint_from_value(fields.get(sprint_field))


def format_issue_detail(
    issue: dict[str, Any], config: JiraConfig, convert_markup: bool = True
) -> str:
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
        lines.append(
            f"Parent:      {parent['key']} - {parent.get('fields', {}).get('summary', '')}"
        )

    remote_links = issue.get("remoteLinks", [])
    if remote_links:
        lines.append("Remote Links:")
        for remote_link in remote_links:
            obj = remote_link.get("object", {}) if isinstance(remote_link, dict) else {}
            title = obj.get("title") or obj.get("url") or remote_link.get("url", "?")
            url = obj.get("url") or remote_link.get("url", "")
            if url and title != url:
                lines.append(f"  - {title}: {url}")
            else:
                lines.append(f"  - {title}")

    desc = fields.get("description", "")
    if desc:
        if convert_markup:
            desc = jira_markup_to_md(desc)
        lines.append(f"\nDescription:\n{desc[:2000]}")
        if len(desc) > 2000:
            lines.append(f"  ... (truncated, {len(desc)} chars total)")

    return "\n".join(lines)


def _add_remote_links_to_issues(client: JiraClient, issues: list[dict[str, Any]]) -> None:
    """Fetch and attach remote links to issues in place."""
    for issue in issues:
        key = issue.get("key")
        if not key:
            continue
        issue["remoteLinks"] = client.get_remote_issue_links(key)


def _handle_key(
    client: JiraClient,
    config: JiraConfig,
    key: str,
    format_type: str,
    fields: list[str] | None,
    convert: bool = True,
    include_remote_links: bool = False,
) -> None:
    try:
        issue = client.get_issue(key, fields=fields)
        if include_remote_links and format_type in {"json", "detail"}:
            issue["remoteLinks"] = client.get_remote_issue_links(key)
        if format_type == "json":
            print(json.dumps(issue, indent=2))
        elif format_type == "detail":
            print(format_issue_detail(issue, config, convert_markup=convert))
        else:
            print(format_issue_table([issue], config))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _handle_jql(
    client: JiraClient,
    config: JiraConfig,
    jql: str,
    format_type: str,
    fields: list[str] | None,
    max_results: int,
    convert: bool = True,
    include_remote_links: bool = False,
) -> None:
    try:
        result = client.search_jql(jql, fields=fields, max_results=max_results)
        issues = result.get("issues", [])
        total = result.get("total", 0)

        if include_remote_links and format_type in {"json", "detail"}:
            _add_remote_links_to_issues(client, issues)

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
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _handle_children(
    client: JiraClient,
    config: JiraConfig,
    parent_key: str,
    format_type: str,
    fields: list[str] | None,
    convert: bool = True,
    include_remote_links: bool = False,
) -> None:
    try:
        issues = client.get_children(parent_key, fields=fields)

        if include_remote_links and format_type in {"json", "detail"}:
            _add_remote_links_to_issues(client, issues)

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
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _handle_board_issues(
    client: JiraClient,
    config: JiraConfig,
    board_id: int,
    filter_args: list[str] | None,
    format_type: str,
    fields: list[str] | None,
    max_results: int,
    convert: bool = True,
    fetch_all: bool = False,
    include_remote_links: bool = False,
) -> None:
    try:
        jql = build_board_jql(client, board_id, filter_pairs=filter_args, fetch_all=fetch_all)

        issues = client.get_board_issues(board_id, jql=jql, fields=fields, max_results=max_results)

        truncated = max_results > 0 and len(issues) >= max_results

        if include_remote_links and format_type in {"json", "detail"}:
            _add_remote_links_to_issues(client, issues)

        if format_type == "json":
            print(json.dumps(issues, indent=2))
        elif format_type == "detail":
            for issue in issues:
                print(format_issue_detail(issue, config, convert_markup=convert))
                print("-" * 40)
        else:
            print(format_issue_table(issues, config))

        print(f"\nTotal: {len(issues)}")
        if truncated:
            print(
                f"NOTE: Results capped at --max-results {max_results}. The board may contain more issues. Use --max-results to increase the limit."
            )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _build_filter_jql(args: argparse.Namespace, config: JiraConfig) -> str:
    """Legacy wrapper for build_jql_from_filters."""
    return build_jql_from_filters(args.filter, config, include_project_scope=True)


def _handle_boards(client: JiraClient, fmt: str) -> None:
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


def _normalize_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Flatten filters, coalesce repeated --key into --keys, and validate mode exclusivity."""
    if args.filter:
        args.filter = [item for sublist in args.filter for item in sublist]

    mode_count = sum(
        1
        for x in [args.key, args.keys, args.jql, args.children_of, args.boards, args.board_id]
        if x
    )

    # Coalesce --key list into --keys when multiple --key flags are given
    if args.key and len(args.key) > 1:
        if args.keys:
            parser.error("Cannot combine repeated --key with --keys")
        args.keys = ",".join(args.key)
        args.key = None
    elif args.key:
        args.key = args.key[0]  # unwrap single-element list

    if args.filter and any([args.key, args.keys, args.jql, args.children_of, args.boards]):
        parser.error(
            "Cannot combine --filter with --key, --keys, --jql, --children-of, or --boards"
        )

    if mode_count > 1:
        parser.error(
            "Conflicting options: provide only one of --key, --keys, --jql, --children-of, --boards, or --board-id"
        )

    if mode_count == 0 and not args.filter:
        parser.error(
            "Must provide one of --key, --keys, --jql, --children-of, --filter, --boards, or --board-id"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Jira issues")
    add_config_arg(parser)

    # We use a manual check instead of mutually_exclusive_group to allow
    # --filter to be combined with --board-id
    parser.add_argument(
        "--key",
        action="append",
        help="Fetch issue(s) by key (repeatable, e.g. --key PROJ-1 --key PROJ-2)",
    )
    parser.add_argument(
        "--keys",
        help="Fetch multiple issues by key (comma-separated, e.g. PROJ-1,PROJ-2,PROJ-3)",
    )
    parser.add_argument("--jql", help="Search using JQL query")
    parser.add_argument("--children-of", help="Fetch children of an epic or story")
    parser.add_argument(
        "--filter",
        action="append",
        nargs="+",
        help="Filter tickets by field=value pairs (e.g. --filter assignee=me status='In Progress')",
    )
    parser.add_argument(
        "--boards",
        action="store_true",
        help="List Agile boards for the project",
    )
    parser.add_argument(
        "--board-id",
        type=int,
        help="Fetch issues from a specific Agile board (can combine with --filter)",
    )
    parser.add_argument(
        "--board-all",
        action="store_true",
        dest="fetch_all",
        help="With --board-id: fetch all issues instead of only the active sprint",
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
    parser.add_argument(
        "--include-remote-links",
        action="store_true",
        help="Fetch and include remote issue links in detail/json output",
    )
    args = parser.parse_args()
    _normalize_args(parser, args)

    config = load_config(args.config)
    client = JiraClient(config)

    field_list = None
    if args.fields:
        field_list = [f.strip() for f in args.fields.split(",")]

    convert = not args.no_convert

    if args.boards:
        _handle_boards(client, args.format)
    elif args.board_id:
        _handle_board_issues(
            client,
            config,
            args.board_id,
            args.filter,
            args.format,
            field_list,
            args.max_results,
            convert,
            fetch_all=args.fetch_all,
            include_remote_links=args.include_remote_links,
        )
    elif args.key and not args.keys:
        _handle_key(
            client,
            config,
            args.key,
            args.format,
            field_list,
            convert,
            include_remote_links=args.include_remote_links,
        )
    elif args.keys:
        keys = [k.strip() for k in args.keys.split(",") if k.strip()]
        jql = f"key in ({','.join(keys)})"
        _handle_jql(
            client,
            config,
            jql,
            args.format,
            field_list,
            len(keys),
            convert,
            include_remote_links=args.include_remote_links,
        )
    elif args.jql:
        _handle_jql(
            client,
            config,
            args.jql,
            args.format,
            field_list,
            args.max_results,
            convert,
            include_remote_links=args.include_remote_links,
        )
    elif args.children_of:
        _handle_children(
            client,
            config,
            args.children_of,
            args.format,
            field_list,
            convert,
            include_remote_links=args.include_remote_links,
        )
    elif args.filter:
        jql = _build_filter_jql(args, config)
        _handle_jql(
            client,
            config,
            jql,
            args.format,
            field_list,
            args.max_results,
            convert,
            include_remote_links=args.include_remote_links,
        )


if __name__ == "__main__":
    main()
