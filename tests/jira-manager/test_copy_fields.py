#!/usr/bin/env python3
"""Tests for _copy_custom_fields in create_ticket.py — create-screen filtering."""

import importlib.util
import sys
from pathlib import Path
from unittest import mock

import pytest

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

_copy_custom_fields = _mod._copy_custom_fields


def _make_client(
    source_fields: dict,
    screen_fields: list[dict] | None = None,
) -> mock.MagicMock:
    """Build a mock JiraClient with source issue and create-screen metadata."""
    client = mock.MagicMock()
    client.get_issue.return_value = {"fields": source_fields}
    client.get_create_meta_for_type.return_value = screen_fields or []
    return client


# --- Basic copy behavior ---


def test_copies_fields_on_create_screen():
    """Only customfield_* fields on the create screen are copied."""
    source_fields = {
        "customfield_10001": "value1",
        "customfield_10002": {"id": "123"},
    }
    screen = [{"key": "customfield_10001"}, {"key": "customfield_10002"}]
    client = _make_client(source_fields, screen)
    fields: dict = {}
    _copy_custom_fields(fields, "SRC-1", client, "28")
    assert fields["customfield_10001"] == "value1"
    assert fields["customfield_10002"] == {"id": "123"}


def test_skips_fields_not_on_create_screen():
    """Fields not on the create screen are skipped."""
    source_fields = {
        "customfield_10001": "on_screen",
        "customfield_10634": "ghost_field",
        "customfield_10635": "another_ghost",
    }
    screen = [{"key": "customfield_10001"}]
    client = _make_client(source_fields, screen)
    fields: dict = {}
    _copy_custom_fields(fields, "SRC-1", client, "28")
    assert fields["customfield_10001"] == "on_screen"
    assert "customfield_10634" not in fields
    assert "customfield_10635" not in fields


def test_skips_none_values():
    """Fields with None values are not copied even if on screen."""
    source_fields = {
        "customfield_10001": "value1",
        "customfield_10002": None,
    }
    screen = [{"key": "customfield_10001"}, {"key": "customfield_10002"}]
    client = _make_client(source_fields, screen)
    fields: dict = {}
    _copy_custom_fields(fields, "SRC-1", client, "28")
    assert "customfield_10001" in fields
    assert "customfield_10002" not in fields


def test_skips_non_custom_fields():
    """Non-customfield_ fields (system fields) are never copied."""
    source_fields = {
        "summary": "Some summary",
        "status": {"name": "Done"},
        "customfield_10001": "value1",
    }
    screen = [
        {"key": "summary"},
        {"key": "status"},
        {"key": "customfield_10001"},
    ]
    client = _make_client(source_fields, screen)
    fields: dict = {}
    _copy_custom_fields(fields, "SRC-1", client, "28")
    assert "summary" not in fields
    assert "status" not in fields
    assert "customfield_10001" in fields


def test_does_not_overwrite_existing_fields():
    """Fields already set in the target dict are not overwritten."""
    source_fields = {
        "customfield_10001": "from_source",
        "customfield_10002": "from_source",
    }
    screen = [{"key": "customfield_10001"}, {"key": "customfield_10002"}]
    client = _make_client(source_fields, screen)
    fields = {"customfield_10001": "already_set"}
    _copy_custom_fields(fields, "SRC-1", client, "28")
    assert fields["customfield_10001"] == "already_set"
    assert fields["customfield_10002"] == "from_source"


# --- Rank / ghost fields automatically filtered by create screen ---


def test_rank_fields_skipped_by_screen_filter():
    """Rank fields are not on the create screen, so they get skipped generically."""
    source_fields = {
        "customfield_11430": "0|i00abc:",
        "customfield_10001": "safe_value",
    }
    screen = [{"key": "customfield_10001"}]
    client = _make_client(source_fields, screen)
    fields: dict = {}
    _copy_custom_fields(fields, "SRC-1", client, "28")
    assert "customfield_11430" not in fields
    assert fields["customfield_10001"] == "safe_value"


def test_multiple_off_screen_fields_all_skipped():
    """All fields not on the create screen are skipped."""
    source_fields = {
        "customfield_11430": "0|i00abc:",
        "customfield_99999": "0|rank:",
        "customfield_10634": "ghost",
        "customfield_10001": "safe_value",
    }
    screen = [{"key": "customfield_10001"}]
    client = _make_client(source_fields, screen)
    fields: dict = {}
    _copy_custom_fields(fields, "SRC-1", client, "28")
    assert "customfield_11430" not in fields
    assert "customfield_99999" not in fields
    assert "customfield_10634" not in fields
    assert fields["customfield_10001"] == "safe_value"


# --- Fallback behavior ---


def test_no_issue_type_id_copies_all():
    """Without issue_type_id, screen check is skipped — all custom fields copied (graceful)."""
    source_fields = {
        "customfield_10001": "value1",
    }
    client = _make_client(source_fields)
    fields: dict = {}
    _copy_custom_fields(fields, "SRC-1", client, None)
    assert fields["customfield_10001"] == "value1"


def test_createmeta_api_failure_copies_all():
    """If get_create_meta_for_type raises, screen check is skipped — all copied (graceful)."""
    source_fields = {
        "customfield_10001": "value1",
    }
    client = _make_client(source_fields)
    client.get_create_meta_for_type.side_effect = Exception("API error")
    fields: dict = {}
    _copy_custom_fields(fields, "SRC-1", client, "28")
    assert fields["customfield_10001"] == "value1"


def test_field_id_fallback_key():
    """Create screen metadata may use 'fieldId' instead of 'key'."""
    source_fields = {
        "customfield_10001": "value1",
    }
    screen = [{"fieldId": "customfield_10001"}]
    client = _make_client(source_fields, screen)
    fields: dict = {}
    _copy_custom_fields(fields, "SRC-1", client, "28")
    assert fields["customfield_10001"] == "value1"


# --- Output messages ---


def test_output_messages(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify that skip and copy messages are printed correctly."""
    source_fields = {
        "customfield_10001": "safe_value",
        "customfield_10634": "ghost",
    }
    screen = [{"key": "customfield_10001"}]
    client = _make_client(source_fields, screen)
    fields: dict = {}
    _copy_custom_fields(fields, "SRC-1", client, "28")
    captured = capsys.readouterr()
    assert "Skipped 1 fields not on create screen" in captured.out
    assert "Copied 1 custom fields from SRC-1" in captured.out
