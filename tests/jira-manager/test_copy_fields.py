#!/usr/bin/env python3
"""Tests for _copy_custom_fields in create_ticket.py — schema-based filtering."""

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
_NON_COPYABLE_SCHEMA_TYPES = _mod._NON_COPYABLE_SCHEMA_TYPES
_SKIP_COPY_FIELDS = _mod._SKIP_COPY_FIELDS


def _make_client(
    source_fields: dict,
    field_metadata: list[dict] | None = None,
) -> mock.MagicMock:
    """Build a mock JiraClient that returns the given source issue and field metadata."""
    client = mock.MagicMock()
    client.get_issue.return_value = {"fields": source_fields}
    if field_metadata is not None:
        client.get_fields.return_value = field_metadata
    else:
        client.get_fields.return_value = []
    return client


# --- Basic copy behavior ---


def test_copies_custom_fields():
    """Custom fields from the source issue are copied into the target fields dict."""
    source_fields = {
        "customfield_10001": "value1",
        "customfield_10002": {"id": "123"},
    }
    client = _make_client(source_fields)
    fields: dict = {}
    _copy_custom_fields(fields, "SRC-1", client)
    assert fields["customfield_10001"] == "value1"
    assert fields["customfield_10002"] == {"id": "123"}


def test_skips_none_values():
    """Fields with None values are not copied."""
    source_fields = {
        "customfield_10001": "value1",
        "customfield_10002": None,
    }
    client = _make_client(source_fields)
    fields: dict = {}
    _copy_custom_fields(fields, "SRC-1", client)
    assert "customfield_10001" in fields
    assert "customfield_10002" not in fields


def test_skips_non_custom_fields():
    """Non-customfield_ fields (system fields) are not copied."""
    source_fields = {
        "summary": "Some summary",
        "status": {"name": "Done"},
        "customfield_10001": "value1",
    }
    client = _make_client(source_fields)
    fields: dict = {}
    _copy_custom_fields(fields, "SRC-1", client)
    assert "summary" not in fields
    assert "status" not in fields
    assert "customfield_10001" in fields


def test_does_not_overwrite_existing_fields():
    """Fields already set in the target dict are not overwritten."""
    source_fields = {
        "customfield_10001": "from_source",
        "customfield_10002": "from_source",
    }
    client = _make_client(source_fields)
    fields = {"customfield_10001": "already_set"}
    _copy_custom_fields(fields, "SRC-1", client)
    assert fields["customfield_10001"] == "already_set"
    assert fields["customfield_10002"] == "from_source"


def test_skips_fields_in_skip_list():
    """Fields in _SKIP_COPY_FIELDS are never copied even if present."""
    source_fields = {
        "project": {"key": "PROJ"},
        "status": {"name": "Done"},
        "customfield_10001": "value1",
    }
    client = _make_client(source_fields)
    fields: dict = {}
    _copy_custom_fields(fields, "SRC-1", client)
    assert "project" not in fields
    assert "status" not in fields
    assert "customfield_10001" in fields


# --- Rank / non-copyable schema filtering (the bug fix) ---


def test_skips_lexo_rank_field():
    """Fields with gh-lexo-rank schema type are skipped (the original bug)."""
    source_fields = {
        "customfield_11430": "0|i00abc:",
        "customfield_10001": "safe_value",
    }
    field_metadata = [
        {
            "id": "customfield_11430",
            "name": "Rank",
            "schema": {"custom": "com.pyxis.greenhopper.jira:gh-lexo-rank"},
        },
        {
            "id": "customfield_10001",
            "name": "Some Field",
            "schema": {"custom": "com.atlassian.jira.plugin.system.customfieldtypes:select"},
        },
    ]
    client = _make_client(source_fields, field_metadata)
    fields: dict = {}
    _copy_custom_fields(fields, "SRC-1", client)
    assert "customfield_11430" not in fields, "Rank field should be skipped"
    assert fields["customfield_10001"] == "safe_value"


def test_skips_global_rank_field():
    """Fields with gh-global-rank schema type are skipped."""
    source_fields = {
        "customfield_99999": "0|rank:",
        "customfield_10001": "safe_value",
    }
    field_metadata = [
        {
            "id": "customfield_99999",
            "name": "Global Rank",
            "schema": {"custom": "com.pyxis.greenhopper.jira:gh-global-rank"},
        },
        {
            "id": "customfield_10001",
            "name": "Some Field",
            "schema": {"type": "string"},
        },
    ]
    client = _make_client(source_fields, field_metadata)
    fields: dict = {}
    _copy_custom_fields(fields, "SRC-1", client)
    assert "customfield_99999" not in fields, "Global rank field should be skipped"
    assert fields["customfield_10001"] == "safe_value"


def test_skips_jpo_baseline_fields():
    """JPO baseline start/end fields are skipped."""
    source_fields = {
        "customfield_20001": "2024-01-01",
        "customfield_20002": "2024-06-01",
        "customfield_10001": "safe_value",
    }
    field_metadata = [
        {
            "id": "customfield_20001",
            "name": "Baseline Start",
            "schema": {"custom": "com.atlassian.jpo:jpo-custom-field-baseline-start"},
        },
        {
            "id": "customfield_20002",
            "name": "Baseline End",
            "schema": {"custom": "com.atlassian.jpo:jpo-custom-field-baseline-end"},
        },
        {
            "id": "customfield_10001",
            "name": "Some Field",
            "schema": {"type": "string"},
        },
    ]
    client = _make_client(source_fields, field_metadata)
    fields: dict = {}
    _copy_custom_fields(fields, "SRC-1", client)
    assert "customfield_20001" not in fields
    assert "customfield_20002" not in fields
    assert fields["customfield_10001"] == "safe_value"


def test_multiple_rank_fields_all_skipped():
    """When multiple non-copyable fields exist, all are skipped."""
    source_fields = {
        "customfield_11430": "0|i00abc:",
        "customfield_99999": "0|rank:",
        "customfield_10001": "safe_value",
        "customfield_10002": "also_safe",
    }
    field_metadata = [
        {
            "id": "customfield_11430",
            "name": "Rank",
            "schema": {"custom": "com.pyxis.greenhopper.jira:gh-lexo-rank"},
        },
        {
            "id": "customfield_99999",
            "name": "Global Rank",
            "schema": {"custom": "com.pyxis.greenhopper.jira:gh-global-rank"},
        },
        {
            "id": "customfield_10001",
            "name": "Field A",
            "schema": {"type": "string"},
        },
        {
            "id": "customfield_10002",
            "name": "Field B",
            "schema": {"type": "string"},
        },
    ]
    client = _make_client(source_fields, field_metadata)
    fields: dict = {}
    _copy_custom_fields(fields, "SRC-1", client)
    assert "customfield_11430" not in fields
    assert "customfield_99999" not in fields
    assert fields["customfield_10001"] == "safe_value"
    assert fields["customfield_10002"] == "also_safe"


def test_field_metadata_fetch_failure_graceful():
    """If get_fields() raises, copy proceeds without schema filtering (graceful degradation)."""
    source_fields = {
        "customfield_11430": "0|i00abc:",
        "customfield_10001": "safe_value",
    }
    client = _make_client(source_fields)
    client.get_fields.side_effect = Exception("API error")
    fields: dict = {}
    _copy_custom_fields(fields, "SRC-1", client)
    # Without metadata, the rank field slips through (graceful degradation)
    assert "customfield_11430" in fields
    assert fields["customfield_10001"] == "safe_value"


def test_field_without_schema_key_not_skipped():
    """Fields whose metadata has no 'schema' key are still copied normally."""
    source_fields = {
        "customfield_10001": "value1",
    }
    field_metadata = [
        {"id": "customfield_10001", "name": "No Schema Field"},
    ]
    client = _make_client(source_fields, field_metadata)
    fields: dict = {}
    _copy_custom_fields(fields, "SRC-1", client)
    assert fields["customfield_10001"] == "value1"


def test_non_copyable_schema_types_constant():
    """Verify the constant includes the known problematic schema types."""
    assert "com.pyxis.greenhopper.jira:gh-lexo-rank" in _NON_COPYABLE_SCHEMA_TYPES
    assert "com.pyxis.greenhopper.jira:gh-global-rank" in _NON_COPYABLE_SCHEMA_TYPES
    assert "com.atlassian.jpo:jpo-custom-field-baseline-start" in _NON_COPYABLE_SCHEMA_TYPES
    assert "com.atlassian.jpo:jpo-custom-field-baseline-end" in _NON_COPYABLE_SCHEMA_TYPES


def test_output_messages(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify that skip and copy messages are printed correctly."""
    source_fields = {
        "customfield_11430": "0|i00abc:",
        "customfield_10001": "safe_value",
    }
    field_metadata = [
        {
            "id": "customfield_11430",
            "name": "Rank",
            "schema": {"custom": "com.pyxis.greenhopper.jira:gh-lexo-rank"},
        },
        {
            "id": "customfield_10001",
            "name": "Some Field",
            "schema": {"type": "string"},
        },
    ]
    client = _make_client(source_fields, field_metadata)
    fields: dict = {}
    _copy_custom_fields(fields, "SRC-1", client)
    captured = capsys.readouterr()
    assert "Skipped 1 non-copyable fields" in captured.out
    assert "customfield_11430" in captured.out
    assert "Copied 1 custom fields from SRC-1" in captured.out
