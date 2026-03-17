"""
JQL query building helpers for jira-manager scripts.

Provides:
- build_board_jql: Build JQL for board fetch with active sprint filter
- build_jql_from_filters: Build JQL from key=value filter pairs
"""

import re
import sys
from typing import List, Optional

# JQL functions that should NOT be quoted when used as filter values.
# Matches patterns like: currentUser(), now(), startOfDay(), startOfWeek(-1w), etc.
_JQL_FUNCTION_RE = re.compile(r"^[a-zA-Z_]\w*\(.*\)$")


def _format_jql_value(value: str) -> str:
    """Format a value for JQL — leave functions unquoted, quote everything else."""
    value = value.strip()
    if _JQL_FUNCTION_RE.match(value):
        return value
    return f'"{value.replace(chr(34), chr(92) + chr(34))}"'


def build_board_jql(
    client,
    board_id: int,
    filter_pairs: Optional[List[str]] = None,
    fetch_all: bool = False,
) -> Optional[str]:
    """Build JQL for board fetch. By default restricts to active sprint(s).

    Shared by fetch_tickets.py and bulk_update.py.

    Args:
        client: JiraClient instance (used to fetch active sprints).
        board_id: Agile board ID.
        filter_pairs: Optional list of "field=value" strings.
        fetch_all: If True, skip the active-sprint filter.

    Returns:
        JQL string or None if no clauses.
    """
    clauses: list[str] = []

    if not fetch_all:
        sprints = client.get_sprints(board_id, state="active")
        if sprints:
            sprint_ids = [str(s["id"]) for s in sprints]
            sprint_names = [s["name"] for s in sprints]
            if len(sprint_ids) == 1:
                clauses.append(f"sprint = {sprint_ids[0]}")
            else:
                clauses.append(f"sprint in ({', '.join(sprint_ids)})")
            print(f"Filtering to active sprint(s): {', '.join(sprint_names)}", file=sys.stderr)
        else:
            print("WARNING: No active sprints found for this board. Showing all issues.", file=sys.stderr)

    if filter_pairs:
        for pair in filter_pairs:
            if "=" not in pair:
                print(f"ERROR: --filter must be 'field=value', got: {pair}", file=sys.stderr)
                sys.exit(1)
            field, _, value = pair.partition("=")
            clauses.append(f'{field.strip()} = {_format_jql_value(value)}')

    return " AND ".join(clauses) if clauses else None


def build_jql_from_filters(
    filter_pairs: List[str],
    config,
    include_project_scope: bool = True,
) -> str:
    """Build a JQL query string from key=value pairs.

    Shared by fetch_tickets.py and bulk_update.py.

    Args:
        filter_pairs: List of "field=value" strings.
        config: JiraConfig instance (used for project_key).
        include_project_scope: If True, prepend ``project = <key>`` clause.

    Returns:
        JQL string with ORDER BY key ASC.
    """
    clauses: list[str] = []
    if include_project_scope:
        clauses.append(f"project = {config.project_key}")

    for pair in filter_pairs:
        if "=" not in pair:
            print(f"ERROR: --filter must be 'field=value', got: {pair}", file=sys.stderr)
            sys.exit(1)
        field, _, value = pair.partition("=")
        clauses.append(f'{field.strip()} = {_format_jql_value(value)}')

    return " AND ".join(clauses) + " ORDER BY key ASC"
