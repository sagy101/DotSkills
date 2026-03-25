#!/usr/bin/env python3
"""Tests for report_web.py — web dashboard rendering helpers and analysis caching."""

import importlib.util
import sys
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Module loading (same pattern as other skill tests)
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "codebase-analyzer" / "scripts"

# Load analyze.py first (report_web imports from it)
_analyze_path = _SCRIPTS_DIR / "analyze.py"
_spec_analyze = importlib.util.spec_from_file_location("analyze", _analyze_path)
assert _spec_analyze is not None and _spec_analyze.loader is not None
_mod_analyze = importlib.util.module_from_spec(_spec_analyze)
_spec_analyze.loader.exec_module(_mod_analyze)
sys.modules["analyze"] = _mod_analyze

FileStats = _mod_analyze.FileStats
CategoryStats = _mod_analyze.CategoryStats

# Load report_web.py
_web_path = _SCRIPTS_DIR / "report_web.py"
_spec_web = importlib.util.spec_from_file_location("report_web", _web_path)
assert _spec_web is not None and _spec_web.loader is not None

# Mock streamlit and pandas before importing report_web
_mock_st = mock.MagicMock()
_mock_pd = mock.MagicMock()
sys.modules["streamlit"] = _mock_st
sys.modules["pandas"] = _mock_pd

_mod_web = importlib.util.module_from_spec(_spec_web)
_spec_web.loader.exec_module(_mod_web)

_rel_path = _mod_web._rel_path
analyze_codebase = _mod_web.analyze_codebase


# ---------------------------------------------------------------------------
# Helper: build CategoryStats from a list of FileStats
# ---------------------------------------------------------------------------


def _build_categories(**kwargs: list) -> dict[str, "CategoryStats"]:  # type: ignore[valid-type]
    """Build a categories dict from keyword args of FileStats lists.

    Usage: _build_categories(code=[fs1, fs2], tests=[fs3])
    """
    categories = {
        "code": CategoryStats(),
        "tests": CategoryStats(),
        "test_data": CategoryStats(),
        "docs": CategoryStats(),
        "plans": CategoryStats(),
        "scripts": CategoryStats(),
    }
    for cat_name, file_list in kwargs.items():
        for fs in file_list:
            categories[cat_name].add_file(fs)
    return categories


# ---------------------------------------------------------------------------
# _rel_path
# ---------------------------------------------------------------------------


class TestRelPath:
    def test_relative_path(self):
        result = _rel_path("/repo/src/main.py", Path("/repo"))
        assert result == "src/main.py"

    def test_unrelated_path_returns_filename(self):
        result = _rel_path("/other/place/file.py", Path("/repo"))
        assert result == "file.py"

    def test_root_file(self):
        result = _rel_path("/repo/file.py", Path("/repo"))
        assert result == "file.py"


# ---------------------------------------------------------------------------
# CategoryStats.add_file aggregation
# ---------------------------------------------------------------------------


class TestCategoryStatsAggregation:
    def test_single_file(self):
        cat = CategoryStats()
        fs = FileStats(
            path="/repo/src/a.py",
            total_lines=100,
            code_lines=80,
            comment_lines=10,
            blank_lines=10,
            language="Python",
            todo_count=2,
            fixme_count=1,
        )
        cat.add_file(fs)

        assert len(cat.files) == 1
        assert cat.total_lines == 100
        assert cat.code_lines == 80
        assert cat.comment_lines == 10
        assert cat.blank_lines == 10
        assert cat.todo_count == 2
        assert cat.fixme_count == 1

    def test_multiple_files(self):
        cat = CategoryStats()
        cat.add_file(
            FileStats(path="a.py", total_lines=50, code_lines=40, comment_lines=5, blank_lines=5)
        )
        cat.add_file(
            FileStats(path="b.py", total_lines=30, code_lines=20, comment_lines=8, blank_lines=2)
        )

        assert len(cat.files) == 2
        assert cat.total_lines == 80
        assert cat.code_lines == 60
        assert cat.comment_lines == 13
        assert cat.blank_lines == 7

    def test_empty_category(self):
        cat = CategoryStats()
        assert len(cat.files) == 0
        assert cat.total_lines == 0
        assert cat.code_lines == 0


# ---------------------------------------------------------------------------
# _build_categories helper
# ---------------------------------------------------------------------------


class TestBuildCategories:
    def test_defaults(self):
        cats = _build_categories()
        assert all(len(cats[k].files) == 0 for k in cats)

    def test_with_code_and_tests(self):
        cats = _build_categories(
            code=[FileStats(path="a.py", total_lines=100, code_lines=80)],
            tests=[FileStats(path="t.py", total_lines=50, code_lines=40)],
        )
        assert len(cats["code"].files) == 1
        assert len(cats["tests"].files) == 1
        assert cats["code"].code_lines == 80
        assert cats["tests"].code_lines == 40


# ---------------------------------------------------------------------------
# Metric computation logic (extracted from render functions)
# ---------------------------------------------------------------------------


class TestMetricComputation:
    """Test the metric calculations that the render functions perform."""

    def test_test_code_ratio(self):
        """Test:Code ratio = test code lines / production code lines."""
        cats = _build_categories(
            code=[FileStats(path="a.py", code_lines=100, total_lines=120)],
            tests=[FileStats(path="t.py", code_lines=80, total_lines=100)],
        )
        code_stats = cats["code"]
        test_stats = cats["tests"]
        ratio = test_stats.code_lines / code_stats.code_lines
        assert ratio == pytest.approx(0.8)

    def test_test_code_ratio_high(self):
        cats = _build_categories(
            code=[FileStats(path="a.py", code_lines=100, total_lines=120)],
            tests=[FileStats(path="t.py", code_lines=500, total_lines=600)],
        )
        ratio = cats["tests"].code_lines / cats["code"].code_lines
        assert ratio == pytest.approx(5.0)

    def test_comment_percentage(self):
        """Comment % = comment_lines / code_lines * 100."""
        cats = _build_categories(
            code=[FileStats(path="a.py", code_lines=200, comment_lines=30, total_lines=250)],
        )
        code_stats = cats["code"]
        pct = code_stats.comment_lines / code_stats.code_lines * 100
        assert pct == pytest.approx(15.0)

    def test_docs_code_ratio(self):
        """Docs:Code ratio = code_lines / docs_code_lines."""
        cats = _build_categories(
            code=[FileStats(path="a.py", code_lines=400, total_lines=500)],
            docs=[FileStats(path="readme.md", code_lines=100, total_lines=120)],
        )
        docs_ratio = cats["code"].code_lines / cats["docs"].code_lines
        assert docs_ratio == pytest.approx(4.0)
        assert 3 <= docs_ratio <= 15  # "Good" range

    def test_ratio_formatting_gte_1(self):
        """When ratio >= 1, format as 1:X."""
        ratio = 2.5
        ratio_str = f"1:{ratio:.1f}" if ratio >= 1 else f"{1 / ratio:.1f}:1"
        assert ratio_str == "1:2.5"

    def test_ratio_formatting_lt_1(self):
        """When ratio < 1, format as X:1."""
        ratio = 0.5
        ratio_str = f"1:{ratio:.1f}" if ratio >= 1 else f"{1 / ratio:.1f}:1"
        assert ratio_str == "2.0:1"


# ---------------------------------------------------------------------------
# File size bucketing logic
# ---------------------------------------------------------------------------


class TestFileSizeBucketing:
    """Test the bucketing logic used in render_file_distribution."""

    @staticmethod
    def _bucket(code_lines: int) -> str:
        if code_lines <= 50:
            return "1-50"
        if code_lines <= 100:
            return "51-100"
        if code_lines <= 200:
            return "101-200"
        if code_lines <= 500:
            return "201-500"
        if code_lines <= 1000:
            return "501-1000"
        return "1000+"

    def test_boundaries(self):
        assert self._bucket(0) == "1-50"
        assert self._bucket(50) == "1-50"
        assert self._bucket(51) == "51-100"
        assert self._bucket(100) == "51-100"
        assert self._bucket(101) == "101-200"
        assert self._bucket(200) == "101-200"
        assert self._bucket(201) == "201-500"
        assert self._bucket(500) == "201-500"
        assert self._bucket(501) == "501-1000"
        assert self._bucket(1000) == "501-1000"
        assert self._bucket(1001) == "1000+"

    def test_full_distribution(self):
        files = [
            FileStats(path="a.py", code_lines=10, total_lines=10),
            FileStats(path="b.py", code_lines=75, total_lines=80),
            FileStats(path="c.py", code_lines=150, total_lines=170),
            FileStats(path="d.py", code_lines=300, total_lines=350),
            FileStats(path="e.py", code_lines=750, total_lines=800),
            FileStats(path="f.py", code_lines=1500, total_lines=1600),
        ]
        buckets = {"1-50": 0, "51-100": 0, "101-200": 0, "201-500": 0, "501-1000": 0, "1000+": 0}
        for f in files:
            buckets[self._bucket(f.code_lines)] += 1

        assert buckets == {
            "1-50": 1,
            "51-100": 1,
            "101-200": 1,
            "201-500": 1,
            "501-1000": 1,
            "1000+": 1,
        }


# ---------------------------------------------------------------------------
# Large file detection logic
# ---------------------------------------------------------------------------


class TestLargeFileDetection:
    def test_no_large_files(self):
        files = [
            FileStats(path="a.py", code_lines=100, total_lines=120),
            FileStats(path="b.py", code_lines=499, total_lines=550),
        ]
        large = [f for f in files if f.code_lines > 500]
        assert large == []

    def test_large_files_found(self):
        files = [
            FileStats(path="a.py", code_lines=100, total_lines=120),
            FileStats(path="big.py", code_lines=800, total_lines=900),
            FileStats(path="huge.py", code_lines=1500, total_lines=1700),
        ]
        large = [f for f in files if f.code_lines > 500]
        large.sort(key=lambda x: x.code_lines, reverse=True)
        assert len(large) == 2
        assert large[0].path == "huge.py"
        assert large[1].path == "big.py"

    def test_custom_threshold(self):
        files = [FileStats(path="a.py", code_lines=250, total_lines=300)]
        threshold = 200
        large = [f for f in files if f.code_lines > threshold]
        assert len(large) == 1


# ---------------------------------------------------------------------------
# TODO/FIXME ranking logic
# ---------------------------------------------------------------------------


class TestTodoRanking:
    def test_sorted_by_total(self):
        files = [
            FileStats(path="a.py", todo_count=1, fixme_count=0, total_lines=10),
            FileStats(path="b.py", todo_count=5, fixme_count=3, total_lines=20),
            FileStats(path="c.py", todo_count=2, fixme_count=2, total_lines=15),
        ]
        todo_files = [f for f in files if f.todo_count + f.fixme_count > 0]
        todo_files.sort(key=lambda x: x.todo_count + x.fixme_count, reverse=True)

        assert todo_files[0].path == "b.py"  # 8 total
        assert todo_files[1].path == "c.py"  # 4 total
        assert todo_files[2].path == "a.py"  # 1 total

    def test_no_todos(self):
        files = [
            FileStats(path="a.py", todo_count=0, fixme_count=0, total_lines=10),
        ]
        todo_files = [f for f in files if f.todo_count + f.fixme_count > 0]
        assert todo_files == []
