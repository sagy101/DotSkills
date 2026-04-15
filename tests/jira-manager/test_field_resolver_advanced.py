#!/usr/bin/env python3
"""Advanced tests for field_resolver.py — resolve_set_field cascade, apply_set_pairs,
build_update_fields, validate_required_fields."""

import argparse
import importlib.util
import sys
from pathlib import Path
from unittest import mock

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "jira-manager" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_MODULE_PATH = Path(_SCRIPTS_DIR) / "field_resolver.py"
_spec = importlib.util.spec_from_file_location("field_resolver", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["field_resolver"] = _mod

resolve_set_field = _mod.resolve_set_field
_resolve_from_catalog = _mod._resolve_from_catalog
_resolve_from_fallbacks = _mod._resolve_from_fallbacks
apply_set_pairs = _mod.apply_set_pairs
build_update_fields = _mod.build_update_fields
validate_required_fields = _mod.validate_required_fields


def _make_config(
    catalog: dict[str, object] | None = None,
    mappings: dict[str, str] | None = None,
    fields_index: dict[str, object] | None = None,
    create_meta: dict[str, object] | None = None,
) -> mock.MagicMock:
    config = mock.MagicMock()
    config.field_catalog = catalog or {}
    if fields_index:
        config.field_catalog["_fields_index"] = fields_index

    def get_field_id(name: str) -> str | None:
        return (mappings or {}).get(name)

    config.get_field_id = get_field_id

    config.create_meta = create_meta or {}
    return config


def _make_args(**kwargs: object) -> argparse.Namespace:
    """Build a namespace with common defaults for field_resolver functions."""
    defaults: dict[str, object] = {
        "summary": None,
        "description": None,
        "description_file": None,
        "story_points": None,
        "labels": None,
        "status": None,
        "priority": None,
        "assignee": None,
        "component": None,
        "fix_version": None,
        "sprint": None,
        "set": None,
        "fields": None,
        "rewrite_links": False,
        "no_convert": True,
        "attachment": [],
        "dry_run": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# resolve_set_field — 4-level cascade
# ---------------------------------------------------------------------------


class TestResolveSetField:
    def test_level1_catalog_status(self):
        """Status field returns (None, None, status_value)."""
        config = _make_config(
            catalog={
                "status": {
                    "type": "status",
                    "id": "status",
                    "values": {"done": {"id": "10", "name": "Done"}},
                }
            }
        )
        jira_id, jira_val, status_val = resolve_set_field(config, "status", "Done")
        assert jira_id is None
        assert jira_val is None
        assert status_val == "Done"

    def test_level1_catalog_priority(self):
        """Priority returns name object."""
        config = _make_config(
            catalog={
                "priority": {
                    "type": "priority",
                    "id": "priority",
                    "values": {"high": {"id": "2", "name": "High"}},
                }
            }
        )
        jira_id, jira_val, status_val = resolve_set_field(config, "priority", "High")
        assert jira_id == "priority"
        assert jira_val == {"name": "High"}
        assert status_val is None

    def test_level1_catalog_component(self):
        """Component returns array of id objects."""
        config = _make_config(
            catalog={
                "components": {
                    "type": "component",
                    "id": "components",
                    "values": {"backend": {"id": "100", "name": "Backend"}},
                }
            }
        )
        jira_id, jira_val, status_val = resolve_set_field(config, "components", "Backend")
        assert jira_id == "components"
        assert jira_val == [{"id": "100"}]

    def test_level1_catalog_unresolved_priority(self):
        """Priority not in catalog values — uses raw name."""
        config = _make_config(
            catalog={"priority": {"type": "priority", "id": "priority", "values": {}}}
        )
        jira_id, jira_val, _ = resolve_set_field(config, "priority", "Custom")
        assert jira_val == {"name": "Custom"}

    def test_level2_field_mappings(self):
        """Falls through to field_mappings when not in catalog."""
        config = _make_config(mappings={"story_points": "customfield_10133"})
        jira_id, jira_val, _ = resolve_set_field(config, "story_points", "5")
        assert jira_id == "customfield_10133"
        assert jira_val == 5.0  # numeric parse

    def test_level2_field_mappings_non_numeric(self):
        config = _make_config(mappings={"epic_name": "customfield_10633"})
        jira_id, jira_val, _ = resolve_set_field(config, "epic_name", "My Epic")
        assert jira_id == "customfield_10633"
        assert jira_val == "My Epic"

    def test_level3_fields_index(self):
        """Falls through to _fields_index."""
        config = _make_config(fields_index={"custom_qbr": {"id": "customfield_99999"}})
        jira_id, jira_val, _ = resolve_set_field(config, "custom_qbr", "value")
        assert jira_id == "customfield_99999"
        assert jira_val == "value"

    def test_level4_raw_passthrough(self):
        """Nothing matched — use field name as-is."""
        config = _make_config()
        jira_id, jira_val, _ = resolve_set_field(config, "customfield_12345", "hello")
        assert jira_id == "customfield_12345"
        assert jira_val == "hello"

    def test_parent_auto_wraps_as_object(self):
        """--set 'parent=KEY' should auto-wrap as {"key": "KEY"} via _OBJECT_KEY_FIELDS."""
        config = _make_config()
        jira_id, jira_val, status_val = resolve_set_field(config, "parent", "API-8615")
        assert jira_id == "parent"
        assert jira_val == {"key": "API-8615"}
        assert status_val is None

    def test_parent_auto_wrap_via_apply_set_pairs(self):
        """apply_set_pairs with parent= produces the correct object format."""
        config = _make_config()
        args = _make_args(set=["parent=PROJ-100"])
        fields: dict = {}
        apply_set_pairs(fields, args, config)
        assert fields["parent"] == {"key": "PROJ-100"}


# ---------------------------------------------------------------------------
# _resolve_from_catalog — type-specific formatting
# ---------------------------------------------------------------------------


class TestResolveFromCatalog:
    def test_status_type(self):
        config = _make_config()
        entry = {"type": "status", "id": "status", "values": {}}
        jira_id, jira_val, status_val = _resolve_from_catalog(config, "status", "Done", entry)
        assert jira_id is None
        assert status_val == "Done"

    def test_resolution_type(self):
        """Resolution is a name-object type."""
        config = _make_config(
            catalog={
                "resolution": {
                    "type": "resolution",
                    "id": "resolution",
                    "values": {"fixed": {"id": "1", "name": "Fixed"}},
                }
            }
        )
        entry = config.field_catalog["resolution"]
        jira_id, jira_val, _ = _resolve_from_catalog(config, "resolution", "Fixed", entry)
        assert jira_val == {"name": "Fixed"}

    def test_version_type(self):
        """Version is an array-object type."""
        config = _make_config(
            catalog={
                "fix_versions": {
                    "type": "version",
                    "id": "fixVersions",
                    "values": {"v1": {"id": "200", "name": "v1.0"}},
                }
            }
        )
        entry = config.field_catalog["fix_versions"]
        jira_id, jira_val, _ = _resolve_from_catalog(config, "fix_versions", "v1.0", entry)
        assert jira_id == "fixVersions"
        assert jira_val == [{"id": "200"}]


# ---------------------------------------------------------------------------
# apply_set_pairs
# ---------------------------------------------------------------------------


class TestApplySetPairs:
    def test_single_set(self):
        config = _make_config(
            catalog={
                "priority": {
                    "type": "priority",
                    "id": "priority",
                    "values": {"high": {"id": "2", "name": "High"}},
                }
            }
        )
        args = _make_args(set=["priority=High"])
        fields = {}
        status = apply_set_pairs(fields, args, config)
        assert fields["priority"] == {"name": "High"}
        assert status is None

    def test_status_extraction(self):
        config = _make_config(catalog={"status": {"type": "status", "id": "status", "values": {}}})
        args = _make_args(set=["status=In Progress"])
        fields = {}
        status = apply_set_pairs(fields, args, config)
        assert status == "In Progress"
        assert "status" not in fields

    def test_multiple_set_pairs(self):
        config = _make_config(mappings={"story_points": "customfield_10133"})
        args = _make_args(set=["story_points=3", "customfield_99=hello"])
        fields = {}
        apply_set_pairs(fields, args, config)
        assert fields["customfield_10133"] == 3.0
        assert fields["customfield_99"] == "hello"

    def test_value_with_equals_sign(self):
        """URL-like values contain = signs."""
        config = _make_config()
        args = _make_args(set=["customfield_100=https://example.com?a=1"])
        fields = {}
        apply_set_pairs(fields, args, config)
        # partition on first = only
        assert fields["customfield_100"] == "https://example.com?a=1"

    def test_no_set_pairs(self):
        config = _make_config()
        args = _make_args(set=None)
        fields = {}
        status = apply_set_pairs(fields, args, config)
        assert status is None
        assert fields == {}

    def test_invalid_format_exits(self):
        import pytest

        config = _make_config()
        args = _make_args(set=["no_equals"])
        fields = {}
        with pytest.raises(SystemExit):
            apply_set_pairs(fields, args, config)


# ---------------------------------------------------------------------------
# build_update_fields
# ---------------------------------------------------------------------------


class TestBuildUpdateFields:
    def test_summary_only(self):
        config = _make_config()
        args = _make_args(summary="New Title")
        fields, status = build_update_fields(args, config)
        assert fields["summary"] == "New Title"
        assert status is None

    def test_summary_with_priority(self):
        config = _make_config(
            catalog={
                "priority": {
                    "type": "priority",
                    "id": "priority",
                    "values": {"high": {"id": "2", "name": "High"}},
                }
            }
        )
        args = _make_args(summary="Title", priority="High")
        fields, _ = build_update_fields(args, config)
        assert fields["summary"] == "Title"
        assert fields["priority"] == {"name": "High"}

    def test_extra_fields_json(self):
        config = _make_config()
        args = _make_args(fields='{"customfield_123": "val"}')
        fields, _ = build_update_fields(args, config)
        assert fields["customfield_123"] == "val"

    def test_set_overrides_named(self):
        """--set and --priority both set priority — --set runs after named fields."""
        config = _make_config(
            catalog={
                "priority": {
                    "type": "priority",
                    "id": "priority",
                    "values": {
                        "low": {"id": "3", "name": "Low"},
                        "high": {"id": "2", "name": "High"},
                    },
                }
            }
        )
        args = _make_args(priority="High", set=["priority=Low"])
        fields, _ = build_update_fields(args, config)
        assert fields["priority"] == {"name": "Low"}

    def test_no_fields(self):
        config = _make_config()
        args = _make_args()
        fields, status = build_update_fields(args, config)
        assert fields == {}
        assert status is None

    def test_assignee_resolved_via_client(self):
        """When a client is passed, assignee display name resolves to accountId."""
        config = _make_config()
        client = mock.MagicMock()
        client.search_users.return_value = [
            {"displayName": "Jane Smith", "accountId": "acc123"},
        ]
        args = _make_args(assignee="Jane Smith")
        fields, _ = build_update_fields(args, config, client=client)
        assert fields["assignee"] == {"accountId": "acc123"}

    def test_assignee_without_client_uses_name(self):
        """Without a client, assignee falls back to name-based format."""
        config = _make_config()
        args = _make_args(assignee="Jane Smith")
        fields, _ = build_update_fields(args, config)
        assert fields["assignee"] == {"name": "Jane Smith"}


# ---------------------------------------------------------------------------
# validate_required_fields
# ---------------------------------------------------------------------------


class TestValidateRequiredFields:
    def test_all_present(self):
        config = _make_config(
            create_meta={
                "story": {
                    "id": "28",
                    "required_fields": [
                        {"id": "issuetype", "name": "Issue Type"},
                        {"id": "project", "name": "Project"},
                        {"id": "summary", "name": "Summary"},
                    ],
                }
            }
        )
        fields = {"customfield_1": "val"}
        missing = validate_required_fields(config, "story", fields)
        assert missing == []  # implicit fields cover issuetype, project, summary

    def test_missing_custom_required(self):
        config = _make_config(
            create_meta={
                "bug": {
                    "id": "15",
                    "required_fields": [
                        {"id": "issuetype", "name": "Issue Type"},
                        {"id": "project", "name": "Project"},
                        {"id": "summary", "name": "Summary"},
                        {"id": "customfield_29823", "name": "Bug source"},
                    ],
                }
            }
        )
        fields = {}
        missing = validate_required_fields(config, "bug", fields)
        assert len(missing) == 1
        assert missing[0]["id"] == "customfield_29823"

    def test_no_create_meta(self):
        config = _make_config(create_meta={})
        missing = validate_required_fields(config, "story", {})
        assert missing == []

    def test_unknown_type(self):
        config = _make_config(create_meta={"story": {"id": "28", "required_fields": []}})
        missing = validate_required_fields(config, "unknown_type", {})
        assert missing == []

    def test_parent_is_implicit(self):
        """Parent field should not be flagged as missing for subtasks."""
        config = _make_config(
            create_meta={
                "sub_task": {
                    "id": "10",
                    "required_fields": [
                        {"id": "parent", "name": "Parent"},
                        {"id": "issuetype", "name": "Issue Type"},
                        {"id": "project", "name": "Project"},
                        {"id": "summary", "name": "Summary"},
                    ],
                }
            }
        )
        missing = validate_required_fields(config, "sub-task", {})
        assert missing == []

    def test_provided_field_not_flagged(self):
        config = _make_config(
            create_meta={
                "bug": {
                    "id": "15",
                    "required_fields": [
                        {"id": "issuetype", "name": "Issue Type"},
                        {"id": "project", "name": "Project"},
                        {"id": "summary", "name": "Summary"},
                        {"id": "customfield_100", "name": "Required Field"},
                    ],
                }
            }
        )
        fields = {"customfield_100": "value"}
        missing = validate_required_fields(config, "bug", fields)
        assert missing == []


if __name__ == "__main__":
    import subprocess

    sys.exit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
