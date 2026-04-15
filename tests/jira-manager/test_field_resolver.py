#!/usr/bin/env python3
"""Tests for field_resolver.py — assignee unassign, set resolution, named fields."""

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any
from unittest import mock

_MODULE_PATH = (
    Path(__file__).resolve().parent.parent.parent / "jira-manager" / "scripts" / "field_resolver.py"
)

# field_resolver imports from sibling modules, so add scripts dir to path
_SCRIPTS_DIR = str(_MODULE_PATH.parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_spec = importlib.util.spec_from_file_location("field_resolver", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["field_resolver"] = _mod

apply_assignee = _mod.apply_assignee
apply_priority = _mod.apply_priority
resolve_catalog_value = _mod.resolve_catalog_value
normalize_key = _mod.normalize_key


# ---------------------------------------------------------------------------
# apply_assignee — including empty-string unassign
# ---------------------------------------------------------------------------


class TestApplyAssignee:
    def _make_args(self, assignee_value: str | None) -> argparse.Namespace:
        return argparse.Namespace(assignee=assignee_value)

    def _make_client(self, search_results: list[dict] | None = None) -> mock.MagicMock:
        client = mock.MagicMock()
        client.search_users.return_value = search_results if search_results is not None else []
        return client

    def test_no_client_falls_back_to_name(self):
        fields = {}
        apply_assignee(fields, self._make_args("user@example.com"))
        assert fields["assignee"] == {"name": "user@example.com"}

    def test_empty_string_unassigns(self):
        fields = {}
        apply_assignee(fields, self._make_args(""))
        assert fields["assignee"] is None

    def test_none_does_nothing(self):
        fields = {}
        apply_assignee(fields, self._make_args(None))
        assert "assignee" not in fields

    def test_exact_match_resolves_to_account_id(self):
        client = self._make_client(
            [
                {"displayName": "Dor Melamed", "accountId": "abc123"},
                {"displayName": "Dor Lebel", "accountId": "def456"},
            ]
        )
        fields = {}
        apply_assignee(fields, self._make_args("Dor Melamed"), client)
        assert fields["assignee"] == {"accountId": "abc123"}

    def test_case_insensitive_exact_match(self):
        client = self._make_client(
            [
                {"displayName": "Dor Melamed", "accountId": "abc123"},
            ]
        )
        fields = {}
        apply_assignee(fields, self._make_args("dor melamed"), client)
        assert fields["assignee"] == {"accountId": "abc123"}

    def test_no_exact_match_suggests_similar_names(self, capsys: Any) -> None:
        client = self._make_client(
            [
                {"displayName": "Dor Melamed", "accountId": "abc123"},
                {"displayName": "Dor Lebel", "accountId": "def456"},
                {"displayName": "Dorothy Copeland", "accountId": "ghi789"},
            ]
        )
        fields: dict[str, Any] = {}
        apply_assignee(fields, self._make_args("Dor Melamd"), client)
        assert "assignee" not in fields  # not set — agent should self-correct
        stderr = capsys.readouterr().err
        assert "Did you mean one of" in stderr
        assert "Dor Melamed" in stderr

    def test_no_users_found_warns(self, capsys: Any) -> None:
        client = self._make_client([])
        fields: dict[str, Any] = {}
        apply_assignee(fields, self._make_args("Nonexistent Person"), client)
        assert "assignee" not in fields
        stderr = capsys.readouterr().err
        assert "No users found" in stderr

    def test_account_id_passthrough(self):
        """If value looks like an accountId, use it directly without searching."""
        fields = {}
        test_id = "5f4e3d2c1b0a9876543210ab"  # pragma: allowlist secret
        apply_assignee(fields, self._make_args(test_id))
        assert fields["assignee"] == {"accountId": test_id}

    def test_client_search_error_falls_back_to_name(self):
        client = mock.MagicMock()
        client.search_users.side_effect = Exception("API error")
        fields = {}
        apply_assignee(fields, self._make_args("Some User"), client)
        assert fields["assignee"] == {"name": "Some User"}


# ---------------------------------------------------------------------------
# normalize_key
# ---------------------------------------------------------------------------


class TestNormalizeKey:
    def test_spaces_to_underscores(self):
        assert normalize_key("Story Points") == "story_points"

    def test_dashes_to_underscores(self):
        assert normalize_key("fix-version") == "fix_version"

    def test_already_normalized(self):
        assert normalize_key("priority") == "priority"

    def test_strips_whitespace(self):
        assert normalize_key("  status  ") == "status"


# ---------------------------------------------------------------------------
# resolve_catalog_value
# ---------------------------------------------------------------------------


class TestResolveCatalogValue:
    def _make_config(self) -> mock.MagicMock:
        config = mock.MagicMock()
        config.field_catalog = {
            "priority": {
                "values": {
                    "high": {"id": "2", "name": "High"},
                    "medium": {"id": "3", "name": "Medium"},
                    "critical": {"id": "1", "name": "Critical"},
                }
            }
        }
        return config

    def test_exact_key_match(self):
        config = self._make_config()
        result = resolve_catalog_value(config, "priority", "high")
        assert result["name"] == "High"

    def test_name_match_case_insensitive(self):
        config = self._make_config()
        result = resolve_catalog_value(config, "priority", "HIGH")
        assert result["name"] == "High"

    def test_not_found_returns_none(self):
        config = self._make_config()
        result = resolve_catalog_value(config, "priority", "nonexistent")
        assert result is None

    def test_empty_catalog_returns_none(self):
        config = mock.MagicMock()
        config.field_catalog = {}
        result = resolve_catalog_value(config, "priority", "High")
        assert result is None


# ---------------------------------------------------------------------------
# apply_priority
# ---------------------------------------------------------------------------


class TestApplyPriority:
    def _make_config(self) -> mock.MagicMock:
        config = mock.MagicMock()
        config.field_catalog = {
            "priority": {
                "values": {
                    "high": {"id": "2", "name": "High"},
                }
            }
        }
        return config

    def test_resolved_priority(self):
        fields = {}
        args = argparse.Namespace(priority="High")
        apply_priority(fields, args, self._make_config())
        assert fields["priority"] == {"name": "High"}

    def test_unresolved_priority_uses_raw(self):
        fields = {}
        args = argparse.Namespace(priority="Custom Priority")
        apply_priority(fields, args, self._make_config())
        assert fields["priority"] == {"name": "Custom Priority"}

    def test_none_priority_does_nothing(self):
        fields = {}
        args = argparse.Namespace(priority=None)
        apply_priority(fields, args, self._make_config())
        assert "priority" not in fields


if __name__ == "__main__":
    import subprocess

    sys.exit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
