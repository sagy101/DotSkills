#!/usr/bin/env python3
"""Tests for auto-diagnosis improvements in create_ticket.py —
_check_field_on_screen, actionable-first sorting in _suggest_fix_for_field_error."""

import importlib.util
import sys
from io import StringIO
from pathlib import Path
from unittest import mock

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "jira-manager" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_MODULE_PATH = Path(_SCRIPTS_DIR) / "create_ticket.py"
_spec = importlib.util.spec_from_file_location("create_ticket", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["create_ticket"] = _mod

_check_field_on_screen = _mod._check_field_on_screen
_suggest_fix_for_field_error = _mod._suggest_fix_for_field_error


def _make_client(
    fields_list: list[dict] | None = None,
    createmeta_fields: list[dict] | None = None,
) -> mock.MagicMock:
    """Build a mock JiraClient with get_fields and get_create_meta_for_type."""
    client = mock.MagicMock()
    client.get_fields.return_value = fields_list or []
    client.get_create_meta_for_type.return_value = createmeta_fields or []
    return client


# ---------------------------------------------------------------------------
# _check_field_on_screen
# ---------------------------------------------------------------------------


class TestCheckFieldOnScreen:
    def test_field_on_screen_with_allowed_values(self):
        """Field found in createmeta with allowed values."""
        client = _make_client(
            createmeta_fields=[
                {"key": "customfield_24712", "allowedValues": [{"value": "Infrastructure"}]},
            ]
        )
        on_screen, allowed = _check_field_on_screen("customfield_24712", client, "10001")
        assert on_screen is True
        assert len(allowed) == 1
        assert allowed[0]["value"] == "Infrastructure"

    def test_field_on_screen_no_allowed_values(self):
        """Field found in createmeta but with no allowed values."""
        client = _make_client(
            createmeta_fields=[
                {"key": "customfield_12839"},
            ]
        )
        on_screen, allowed = _check_field_on_screen("customfield_12839", client, "10001")
        assert on_screen is True
        assert allowed == []

    def test_field_not_on_screen(self):
        """Field not found in createmeta at all."""
        client = _make_client(
            createmeta_fields=[
                {"key": "customfield_99999", "allowedValues": [{"value": "X"}]},
            ]
        )
        on_screen, allowed = _check_field_on_screen("customfield_12839", client, "10001")
        assert on_screen is False
        assert allowed == []

    def test_no_issue_type_id(self):
        """Without issue_type_id, always returns False."""
        client = _make_client()
        on_screen, allowed = _check_field_on_screen("customfield_12839", client, None)
        assert on_screen is False
        assert allowed == []

    def test_createmeta_api_error(self):
        """If createmeta call fails, returns False."""
        client = _make_client()
        client.get_create_meta_for_type.side_effect = Exception("API error")
        on_screen, allowed = _check_field_on_screen("customfield_12839", client, "10001")
        assert on_screen is False
        assert allowed == []

    def test_field_id_fallback_key(self):
        """createmeta may return 'fieldId' instead of 'key'."""
        client = _make_client(
            createmeta_fields=[
                {"fieldId": "customfield_24712", "allowedValues": [{"value": "Innovation"}]},
            ]
        )
        on_screen, allowed = _check_field_on_screen("customfield_24712", client, "10001")
        assert on_screen is True
        assert allowed[0]["value"] == "Innovation"


# ---------------------------------------------------------------------------
# _suggest_fix_for_field_error — actionable-first sorting
# ---------------------------------------------------------------------------


class TestSuggestFixActionableSorting:
    def test_actionable_field_appears_before_non_actionable(self):
        """QBR Theme (on screen) should appear before QBR (not on screen)."""
        all_fields = [
            {"id": "customfield_12839", "name": "QBR"},
            {"id": "customfield_24712", "name": "QBR Theme"},
        ]

        def mock_createmeta(issue_type_id: str) -> list[dict]:
            return [
                {
                    "key": "customfield_24712",
                    "allowedValues": [
                        {"value": "Infrastructure"},
                        {"value": "Innovation"},
                    ],
                },
            ]

        client = _make_client(fields_list=all_fields)
        client.get_create_meta_for_type.side_effect = mock_createmeta

        stderr = StringIO()
        with mock.patch("sys.stderr", stderr):
            _suggest_fix_for_field_error(
                "Please Fill Out QBR",
                client,
                "10001",
            )

        output = stderr.getvalue()
        lines = output.strip().split("\n")

        qbr_theme_idx = None
        qbr_not_settable_idx = None
        for i, line in enumerate(lines):
            if "QBR Theme" in line and "customfield_24712" in line:
                qbr_theme_idx = i
            if "customfield_12839" in line and "not on create screen" in line:
                qbr_not_settable_idx = i

        assert qbr_theme_idx is not None, f"QBR Theme not found in output:\n{output}"
        assert qbr_not_settable_idx is not None, f"QBR not-settable not found in output:\n{output}"
        assert qbr_theme_idx < qbr_not_settable_idx, (
            f"QBR Theme (line {qbr_theme_idx}) should appear before "
            f"QBR not-settable (line {qbr_not_settable_idx})"
        )

    def test_recommended_marker_on_actionable_field(self):
        """Actionable field with allowed values gets ★ Recommended marker."""
        all_fields = [
            {"id": "customfield_24712", "name": "QBR Theme"},
        ]
        client = _make_client(
            fields_list=all_fields,
            createmeta_fields=[
                {"key": "customfield_24712", "allowedValues": [{"value": "Infrastructure"}]},
            ],
        )

        stderr = StringIO()
        with mock.patch("sys.stderr", stderr):
            _suggest_fix_for_field_error("Please Fill Out QBR", client, "10001")

        output = stderr.getvalue()
        assert "★ Recommended" in output

    def test_no_candidates_produces_no_output(self):
        """Error text with no field candidates should produce no diagnosis."""
        client = _make_client()
        stderr = StringIO()
        with mock.patch("sys.stderr", stderr):
            _suggest_fix_for_field_error("Something unexpected happened", client, "10001")
        assert stderr.getvalue() == ""

    def test_unmatched_candidate(self):
        """Candidate that matches no field in get_fields produces 'Could not find' message."""
        client = _make_client(fields_list=[])
        stderr = StringIO()
        with mock.patch("sys.stderr", stderr):
            _suggest_fix_for_field_error("Please Fill Out XYZ", client, "10001")
        output = stderr.getvalue()
        assert "Could not find" in output
