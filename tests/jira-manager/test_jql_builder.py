#!/usr/bin/env python3
"""Tests for jql_builder.py — JQL function detection, filter building, board JQL."""

import importlib.util
import sys
from pathlib import Path
from unittest import mock

_MODULE_PATH = (
    Path(__file__).resolve().parent.parent.parent / "jira-manager" / "scripts" / "jql_builder.py"
)
_spec = importlib.util.spec_from_file_location("jql_builder", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["jql_builder"] = _mod

_format_jql_value = _mod._format_jql_value
_JQL_FUNCTION_RE = _mod._JQL_FUNCTION_RE
build_jql_from_filters = _mod.build_jql_from_filters


# ---------------------------------------------------------------------------
# _format_jql_value — JQL function detection
# ---------------------------------------------------------------------------


class TestFormatJqlValue:
    def test_plain_string_is_quoted(self):
        assert _format_jql_value("In Progress") == '"In Progress"'

    def test_plain_word_is_quoted(self):
        assert _format_jql_value("Done") == '"Done"'

    def test_currentUser_not_quoted(self):
        assert _format_jql_value("currentUser()") == "currentUser()"

    def test_now_not_quoted(self):
        assert _format_jql_value("now()") == "now()"

    def test_startOfDay_not_quoted(self):
        assert _format_jql_value("startOfDay()") == "startOfDay()"

    def test_function_with_args_not_quoted(self):
        assert _format_jql_value("startOfWeek(-1w)") == "startOfWeek(-1w)"

    def test_endOfMonth_not_quoted(self):
        assert _format_jql_value("endOfMonth()") == "endOfMonth()"

    def test_value_with_parens_in_middle_is_quoted(self):
        # "foo(bar" is not a function call — no closing paren at end
        result = _format_jql_value("foo(bar")
        assert result == '"foo(bar"'

    def test_empty_string_is_quoted(self):
        assert _format_jql_value("") == '""'

    def test_whitespace_is_trimmed(self):
        assert _format_jql_value("  currentUser()  ") == "currentUser()"

    def test_quotes_in_value_are_escaped(self):
        result = _format_jql_value('say "hello"')
        assert '\\"' in result


# ---------------------------------------------------------------------------
# _JQL_FUNCTION_RE — regex edge cases
# ---------------------------------------------------------------------------


class TestJqlFunctionRegex:
    def test_underscore_function(self):
        assert _JQL_FUNCTION_RE.match("my_func()")

    def test_numeric_start_not_matched(self):
        assert not _JQL_FUNCTION_RE.match("123func()")

    def test_nested_parens(self):
        assert _JQL_FUNCTION_RE.match("func(inner())")

    def test_no_parens(self):
        assert not _JQL_FUNCTION_RE.match("nofunc")


# ---------------------------------------------------------------------------
# build_jql_from_filters
# ---------------------------------------------------------------------------


class TestBuildJqlFromFilters:
    def _make_config(self, project_key: str = "TEST") -> mock.MagicMock:
        return mock.MagicMock(project_key=project_key)

    def test_single_filter(self):
        config = self._make_config()
        jql = build_jql_from_filters(["status=Done"], config)
        assert 'status = "Done"' in jql
        assert "project = TEST" in jql

    def test_function_value_not_quoted(self):
        config = self._make_config()
        jql = build_jql_from_filters(["assignee=currentUser()"], config)
        assert "assignee = currentUser()" in jql
        assert '"currentUser()"' not in jql

    def test_multiple_filters(self):
        config = self._make_config()
        jql = build_jql_from_filters(["assignee=currentUser()", "status=In Progress"], config)
        assert "assignee = currentUser()" in jql
        assert 'status = "In Progress"' in jql
        assert " AND " in jql

    def test_no_project_scope(self):
        config = self._make_config()
        jql = build_jql_from_filters(["status=Done"], config, include_project_scope=False)
        assert "project" not in jql
        assert 'status = "Done"' in jql

    def test_order_by_appended(self):
        config = self._make_config()
        jql = build_jql_from_filters(["status=Done"], config)
        assert jql.endswith("ORDER BY key ASC")

    def test_invalid_filter_exits(self):
        import pytest

        config = self._make_config()
        with pytest.raises(SystemExit):
            build_jql_from_filters(["no_equals_sign"], config)


if __name__ == "__main__":
    import subprocess

    sys.exit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
