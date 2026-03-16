#!/usr/bin/env python3
"""Tests for fetch_tickets.py — table formatting, detail formatting, keys parsing."""

import importlib.util
import sys
from pathlib import Path
from unittest import mock

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "jira-manager" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_MODULE_PATH = Path(_SCRIPTS_DIR) / "fetch_tickets.py"
_spec = importlib.util.spec_from_file_location("fetch_tickets", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["fetch_tickets"] = _mod

format_issue_table = _mod.format_issue_table
format_issue_detail = _mod.format_issue_detail
_extract_sprint_from_value = _mod._extract_sprint_from_value


def _make_config(sp_field="customfield_10133", sprint_field="customfield_10631"):
    config = mock.MagicMock()
    def get_field_id(name):
        mapping = {"story_points": sp_field, "sprint": sprint_field}
        return mapping.get(name)
    config.get_field_id = get_field_id
    return config


def _make_issue(key="TEST-1", summary="Test issue", itype="Story",
                status="To Do", priority="High", sp=3.0, sprint_name=None):
    fields = {
        "summary": summary,
        "issuetype": {"name": itype},
        "status": {"name": status},
        "priority": {"name": priority},
        "customfield_10133": sp,
    }
    if sprint_name:
        fields["customfield_10631"] = [{"name": sprint_name}]
    return {"key": key, "fields": fields}


# ---------------------------------------------------------------------------
# format_issue_table — priority column
# ---------------------------------------------------------------------------

class TestFormatIssueTable:
    def test_header_includes_priority(self):
        config = _make_config()
        table = format_issue_table([], config)
        assert "Priority" in table

    def test_priority_value_in_row(self):
        config = _make_config()
        issue = _make_issue(priority="Critical")
        table = format_issue_table([issue], config)
        assert "Critical" in table

    def test_missing_priority_shows_question_mark(self):
        config = _make_config()
        issue = _make_issue()
        issue["fields"]["priority"] = None
        table = format_issue_table([issue], config)
        lines = table.split("\n")
        assert "?" in lines[2]  # data row

    def test_multiple_issues(self):
        config = _make_config()
        issues = [
            _make_issue("T-1", priority="High"),
            _make_issue("T-2", priority="Low"),
        ]
        table = format_issue_table(issues, config)
        assert "High" in table
        assert "Low" in table

    def test_story_points_displayed(self):
        config = _make_config()
        issue = _make_issue(sp=5.0)
        table = format_issue_table([issue], config)
        assert "5.0" in table

    def test_sprint_truncated(self):
        config = _make_config()
        issue = _make_issue(sprint_name="Very Long Sprint Name That Exceeds Limit")
        table = format_issue_table([issue], config)
        assert "\u2026" in table  # ellipsis


# ---------------------------------------------------------------------------
# format_issue_detail
# ---------------------------------------------------------------------------

class TestFormatIssueDetail:
    def test_includes_all_fields(self):
        config = _make_config()
        issue = _make_issue(priority="High", sp=3.0, sprint_name="Sprint 1")
        issue["fields"]["assignee"] = {"displayName": "Test User"}
        issue["fields"]["description"] = "A description"
        detail = format_issue_detail(issue, config, convert_markup=False)
        assert "Key:         TEST-1" in detail
        assert "Priority:    High" in detail
        assert "Story Pts:   3.0" in detail
        assert "Sprint:      Sprint 1" in detail
        assert "Assignee:    Test User" in detail
        assert "A description" in detail

    def test_no_description(self):
        config = _make_config()
        issue = _make_issue()
        issue["fields"]["description"] = ""
        detail = format_issue_detail(issue, config, convert_markup=False)
        assert "Description" not in detail

    def test_parent_shown(self):
        config = _make_config()
        issue = _make_issue()
        issue["fields"]["parent"] = {
            "key": "TEST-100",
            "fields": {"summary": "Parent Epic"},
        }
        detail = format_issue_detail(issue, config, convert_markup=False)
        assert "Parent:      TEST-100 - Parent Epic" in detail


# ---------------------------------------------------------------------------
# Sprint extraction
# ---------------------------------------------------------------------------

class TestSprintExtraction:
    def test_dict_sprint(self):
        assert _extract_sprint_from_value({"name": "Sprint 1"}) == "Sprint 1"

    def test_list_sprint_takes_last(self):
        sprints = [{"name": "Old"}, {"name": "Current"}]
        assert _extract_sprint_from_value(sprints) == "Current"

    def test_legacy_string_sprint(self):
        legacy = "com.atlassian.greenhopper.service.sprint.Sprint@abc[id=1,name=Sprint 5,state=ACTIVE]"
        assert _extract_sprint_from_value(legacy) == "Sprint 5"

    def test_empty_list(self):
        assert _extract_sprint_from_value([]) is None

    def test_none(self):
        assert _extract_sprint_from_value(None) is None


if __name__ == "__main__":
    import subprocess
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
