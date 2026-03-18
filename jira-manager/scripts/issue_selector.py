"""
Shared issue selection logic for jira-manager scripts.

Provides a unified way to fetch issues from different sources:
tickets (comma-separated keys), board ID, JQL, or filter pairs.

Used by fetch_tickets.py, bulk_update.py, and potentially future scripts.
"""

import sys
from typing import Any

from jira_client import JiraClient
from jira_config_loader import JiraConfig
from jql_builder import build_board_jql, build_jql_from_filters


def select_issues(
    client: JiraClient,
    config: JiraConfig,
    tickets: str | None = None,
    board_id: int | None = None,
    jql: str | None = None,
    filter_pairs: list[str] | None = None,
    fetch_all: bool = False,
    max_results: int = 0,
    fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch issues from the appropriate source based on provided arguments.

    Args:
        client: JiraClient instance.
        config: JiraConfig instance.
        tickets: Comma-separated issue keys (e.g. "PROJ-1,PROJ-2").
        board_id: Agile board ID.
        jql: Raw JQL query string.
        filter_pairs: List of "field=value" filter strings.
        fetch_all: With board_id, skip the active-sprint filter.
        max_results: Cap on total issues (0 = unlimited).
        fields: List of Jira fields to fetch per issue.

    Returns:
        List of issue dicts from the Jira API.
    """
    if tickets:
        return _fetch_by_keys(client, tickets, fields)

    if board_id:
        return _fetch_from_board(client, board_id, filter_pairs, fetch_all, max_results, fields)

    if jql:
        print(f"Fetching issues by JQL: {jql}...", file=sys.stderr)
        return client.search_jql_all(jql, fields=fields, max_results=max_results)

    if filter_pairs:
        built_jql = build_jql_from_filters(filter_pairs, config, include_project_scope=True)
        print(f"Fetching issues by filter JQL: {built_jql}...", file=sys.stderr)
        return client.search_jql_all(built_jql, fields=fields, max_results=max_results)

    return []


def _fetch_by_keys(
    client: JiraClient,
    tickets: str,
    fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch issues by comma-separated keys."""
    issues: list[dict[str, Any]] = []
    keys = [k.strip() for k in tickets.split(",") if k.strip()]
    for key in keys:
        try:
            issue = client.get_issue(key, fields=fields)
            issues.append(issue)
        except Exception:
            print(f"WARNING: Could not fetch issue {key}, skipping.", file=sys.stderr)
    return issues


def _fetch_from_board(
    client: JiraClient,
    board_id: int,
    filter_pairs: list[str] | None,
    fetch_all: bool,
    max_results: int,
    fields: list[str] | None,
) -> list[dict[str, Any]]:
    """Fetch issues from an Agile board."""
    print(f"Fetching issues from board {board_id}...", file=sys.stderr)
    jql = build_board_jql(client, board_id, filter_pairs=filter_pairs, fetch_all=fetch_all)
    return client.get_board_issues(board_id, jql=jql, fields=fields, max_results=max_results)
