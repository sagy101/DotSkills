"""
Workflow operation helpers for jira-manager scripts.

Provides:
- handle_status_transition: Resolve and execute a workflow transition
- resolve_transition: Find the transition that leads to a target status
- upload_attachments: Upload attachment files to an issue
"""

import sys

from field_resolver import normalize_key, resolve_catalog_value
from jira_client import JiraClient
from jira_config_loader import JiraConfig


def resolve_transition(
    client: JiraClient,
    issue_key: str,
    target_status: str,
    config: JiraConfig,
) -> tuple[str, str, str] | None:
    """Find the transition that leads to the target status.

    Returns (transition_id, transition_name, target_status_name) or None.
    """
    transitions = client.get_transitions(issue_key)
    normalized_target = normalize_key(target_status)

    for t in transitions:
        to_status = t.get("to", {})
        status_name = to_status.get("name", "")
        if normalize_key(status_name) == normalized_target:
            return t["id"], t["name"], status_name

    for t in transitions:
        if normalize_key(t.get("name", "")) == normalized_target:
            to_status = t.get("to", {})
            return t["id"], t["name"], to_status.get("name", t["name"])

    resolved = resolve_catalog_value(config, "status", target_status)
    if resolved:
        canonical = resolved["name"]
        for t in transitions:
            to_status = t.get("to", {})
            if to_status.get("name", "") == canonical:
                return t["id"], t["name"], canonical

    return None


def handle_status_transition(
    client: JiraClient,
    issue_key: str,
    target_status: str,
    config: JiraConfig,
    warn_only: bool = False,
) -> bool:
    """Resolve and execute a workflow transition.

    Args:
        warn_only: If True, print a warning instead of exiting on failure.
                   Useful for post-create transitions where the issue already exists.

    Returns:
        True if transition succeeded, False if it failed (only when warn_only=True).
        Exits the process on failure when warn_only=False.
    """
    result = resolve_transition(client, issue_key, target_status, config)
    if result is None:
        available = client.get_transitions(issue_key)
        names = [t["to"]["name"] for t in available if "to" in t]
        msg = (
            f"No transition found to status '{target_status}' for {issue_key}. "
            f"Available: {', '.join(names) if names else '(none)'}"
        )
        if warn_only:
            print(f"WARNING: {msg}", file=sys.stderr)
            return False
        print(f"ERROR: {msg}", file=sys.stderr)
        sys.exit(1)

    transition_id, transition_name, target_name = result
    try:
        client.transition_issue(issue_key, transition_id)
        print(f"  Transitioned {issue_key} -> {target_name} (via '{transition_name}')")
        return True
    except Exception:
        if warn_only:
            print(f"  WARNING: Failed to transition {issue_key} to {target_name}", file=sys.stderr)
            return False
        sys.exit(1)


def upload_attachments(client: JiraClient, issue_key: str, file_paths: list[str]) -> bool:
    """Upload attachment files to an issue. Returns True if all succeeded."""
    all_ok = True
    for fpath in file_paths:
        try:
            attached = client.add_attachment(issue_key, fpath)
            for a in attached:
                print(f"  Attached: {a.get('filename', fpath)}")
        except Exception:
            print(f"  WARNING: Failed to attach {fpath}", file=sys.stderr)
            all_ok = False
    return all_ok
