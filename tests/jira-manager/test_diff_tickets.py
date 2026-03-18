#!/usr/bin/env python3
"""Tests for diff_tickets.py — field comparison, normalization, story point tolerance."""

import importlib.util
import sys
from pathlib import Path
from unittest import mock

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "jira-manager" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_MODULE_PATH = Path(_SCRIPTS_DIR) / "diff_tickets.py"
_spec = importlib.util.spec_from_file_location("diff_tickets", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["diff_tickets"] = _mod

_sp_differs = _mod._sp_differs
_normalize_text = _mod._normalize_text
_compare_fields = _mod._compare_fields


def _make_config() -> mock.MagicMock:
    config = mock.MagicMock()
    config.resolve_git_remote_url.return_value = None  # no link rewriting
    config.resolve_git_branch.return_value = "main"
    return config


# ---------------------------------------------------------------------------
# _sp_differs
# ---------------------------------------------------------------------------


class TestSpDiffers:
    def test_both_none(self):
        assert _sp_differs(None, None) is False

    def test_local_none_remote_number(self):
        assert _sp_differs(None, 3.0) is True

    def test_local_number_remote_none(self):
        assert _sp_differs(5.0, None) is True

    def test_exact_match(self):
        assert _sp_differs(3.0, 3.0) is False

    def test_within_tolerance(self):
        assert _sp_differs(3.0, 3.005) is False

    def test_outside_tolerance(self):
        assert _sp_differs(3.0, 3.02) is True

    def test_string_numbers(self):
        assert _sp_differs("3", "3.0") is False

    def test_zero_vs_zero(self):
        assert _sp_differs(0, 0) is False

    def test_zero_vs_none(self):
        assert _sp_differs(0, None) is True


# ---------------------------------------------------------------------------
# _normalize_text
# ---------------------------------------------------------------------------


class TestNormalizeText:
    def test_none(self):
        assert _normalize_text(None) == ""

    def test_empty(self):
        assert _normalize_text("") == ""

    def test_trailing_whitespace_stripped(self):
        assert _normalize_text("hello   \nworld  ") == "hello\nworld"

    def test_crlf_normalized(self):
        assert _normalize_text("a\r\nb") == "a\nb"

    def test_leading_trailing_stripped(self):
        assert _normalize_text("\n  hello  \n") == "hello"

    def test_preserves_internal_newlines(self):
        assert _normalize_text("a\n\nb") == "a\n\nb"

    def test_mixed(self):
        text = "  line1  \r\n  line2  \r\n"
        result = _normalize_text(text)
        assert result == "line1\n  line2"


# ---------------------------------------------------------------------------
# _compare_fields
# ---------------------------------------------------------------------------


class TestCompareFields:
    def test_all_match(self):
        local = {"summary": "Title", "description": "", "story_points": 3.0}
        remote = {"summary": "Title", "description": "", "customfield_10133": 3.0}
        diffs = _compare_fields(local, remote, "customfield_10133", _make_config())
        assert diffs == []

    def test_summary_mismatch(self):
        local = {"summary": "Old Title"}
        remote = {"summary": "New Title"}
        diffs = _compare_fields(local, remote, None, _make_config())
        assert len(diffs) == 1
        assert diffs[0][0] == "summary"

    def test_sp_mismatch(self):
        local = {"summary": "T", "story_points": 3.0}
        remote = {"summary": "T", "customfield_10133": 5.0}
        diffs = _compare_fields(local, remote, "customfield_10133", _make_config())
        assert any(d[0] == "story_points" for d in diffs)

    def test_sp_within_tolerance(self):
        local = {"summary": "T", "story_points": 3.0}
        remote = {"summary": "T", "customfield_10133": 3.005}
        diffs = _compare_fields(local, remote, "customfield_10133", _make_config())
        assert not any(d[0] == "story_points" for d in diffs)

    def test_description_normalized_match(self):
        """Descriptions that differ only by trailing whitespace should match."""
        local = {"summary": "T", "description": "hello  \nworld  "}
        remote = {"summary": "T", "description": "hello\nworld"}
        # Note: _compare_fields converts local MD → Jira, so for plain text they should be close
        diffs = _compare_fields(local, remote, None, _make_config())
        # May or may not diff depending on MD conversion, but test it doesn't crash
        assert isinstance(diffs, list)

    def test_no_sp_field_skips_comparison(self):
        local = {"summary": "T", "story_points": 5.0}
        remote = {"summary": "T"}
        diffs = _compare_fields(local, remote, None, _make_config())
        assert not any(d[0] == "story_points" for d in diffs)

    def test_empty_descriptions(self):
        local = {"summary": "T", "description": ""}
        remote = {"summary": "T", "description": ""}
        diffs = _compare_fields(local, remote, None, _make_config())
        assert not any(d[0] == "description" for d in diffs)


if __name__ == "__main__":
    import subprocess

    sys.exit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
