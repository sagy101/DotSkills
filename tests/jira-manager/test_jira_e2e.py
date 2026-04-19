#!/usr/bin/env python3
"""Opt-in live Jira E2E smoke test for issue comments.

Run only when explicitly enabled:
    JIRA_LIVE_E2E=1 python3 -m pytest tests/jira-manager/test_jira_e2e.py -q
"""

import importlib.util
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

_LIVE_FLAG = os.environ.get("JIRA_LIVE_E2E", "").lower() in ("1", "true", "yes")
pytestmark = pytest.mark.skipif(not _LIVE_FLAG, reason="Set JIRA_LIVE_E2E=1 to run live Jira E2E")

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "jira-manager" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_CLIENT_PATH = Path(_SCRIPTS_DIR) / "jira_client.py"
_client_spec = importlib.util.spec_from_file_location("jira_client", _CLIENT_PATH)
assert _client_spec is not None
assert _client_spec.loader is not None
_client_mod = importlib.util.module_from_spec(_client_spec)
_client_spec.loader.exec_module(_client_mod)
sys.modules["jira_client"] = _client_mod

_COMMENTS_PATH = Path(_SCRIPTS_DIR) / "issue_comments.py"
_comments_spec = importlib.util.spec_from_file_location("issue_comments", _COMMENTS_PATH)
assert _comments_spec is not None
assert _comments_spec.loader is not None
_comments_mod = importlib.util.module_from_spec(_comments_spec)
_comments_spec.loader.exec_module(_comments_mod)

from jira_config_loader import load_config  # type: ignore  # noqa: E402

_extract_comment_text = _comments_mod._extract_comment_text


def _required_field_value(field_meta: dict[str, Any]) -> Any | None:
    allowed = field_meta.get("allowedValues") or []
    if allowed:
        choice = allowed[0]
        if isinstance(choice, dict):
            for key in ("id", "value", "name", "key"):
                if choice.get(key) is not None:
                    if field_meta.get("schema", {}).get("type") == "array":
                        return [{key: choice[key]}]
                    return {key: choice[key]}
        if field_meta.get("schema", {}).get("type") == "array":
            return [choice]
        return choice

    default_value = field_meta.get("defaultValue")
    if default_value is not None:
        return default_value

    return None


def _create_disposable_issue(client: Any, project_key: str) -> str:
    meta = client.get_create_meta(project_key)
    projects = meta.get("projects", [])
    if not projects:
        pytest.skip("No create metadata returned; cannot create a disposable Jira issue")

    summary = f"Codex Jira E2E {datetime.now(timezone.utc).isoformat()} {uuid.uuid4().hex[:8]}"

    candidates: list[tuple[int, dict[str, Any]]] = []
    for project in projects:
        if project.get("key") != project_key:
            continue
        for issue_type in project.get("issuetypes", []):
            fields = issue_type.get("fields", {})
            required_count = sum(1 for meta in fields.values() if meta.get("required"))
            candidates.append((required_count, issue_type))

    for _required_count, issue_type in sorted(candidates, key=lambda item: item[0]):
        issue_fields: dict[str, Any] = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"id": issue_type["id"]},
        }
        supported = True
        for fid, field_meta in issue_type.get("fields", {}).items():
            if not field_meta.get("required") or fid in {"project", "summary", "issuetype"}:
                continue
            value = _required_field_value(field_meta)
            if value is None:
                supported = False
                break
            issue_fields[fid] = value
        if not supported:
            continue

        try:
            created = client.create_issue(issue_fields)
        except Exception:
            continue

        issue_key = created.get("key")
        if isinstance(issue_key, str) and issue_key:
            return issue_key

    pytest.skip("No createmeta issue type could be satisfied for a disposable Jira issue")
    raise AssertionError("unreachable")


def test_issue_comment_lifecycle() -> None:
    config = load_config()
    client = _client_mod.JiraClient(config)
    issue_key = _create_disposable_issue(client, config.project_key)

    try:
        created = client.add_comment(issue_key, "Live E2E comment")
        comment_id = created["id"]

        comments = client.get_comments(issue_key)
        assert comment_id in {comment["id"] for comment in comments}

        fetched = client.get_comment(issue_key, comment_id)
        assert _extract_comment_text(fetched["body"]) == "Live E2E comment"

        updated = client.update_comment(issue_key, comment_id, "Live E2E comment updated")
        assert updated["id"] == comment_id

        fetched_updated = client.get_comment(issue_key, comment_id)
        assert _extract_comment_text(fetched_updated["body"]) == "Live E2E comment updated"

        client.delete_comment(issue_key, comment_id)
        remaining = client.get_comments(issue_key)
        assert comment_id not in {comment["id"] for comment in remaining}
    finally:
        try:
            client.delete_issue(issue_key, delete_subtasks=True)
        except Exception as exc:
            print(
                f"WARNING: failed to delete disposable Jira issue {issue_key}: {exc}",
                file=sys.stderr,
            )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
