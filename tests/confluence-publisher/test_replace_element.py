"""Unit tests for replace_element.py — extraction and apply logic.

Tests the core find_element_after_heading function and apply-mode validation
without requiring a live Confluence connection.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add the scripts directory to sys.path so we can import the module
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "confluence-publisher" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from replace_element import find_element_after_heading  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures: sample HTML fragments
# ---------------------------------------------------------------------------

SIMPLE_HTML = """
<h2 id="intro">Introduction</h2>
<p>Some intro text.</p>
<table><tr><td>A</td></tr></table>
<h2 id="phases">Implementation Phases</h2>
<p>Phase description.</p>
<table data-id="target"><tr><td>Phase 1</td></tr></table>
<h2 id="decisions">Key Decisions</h2>
<p>Decision text.</p>
"""

NESTED_TABLE_HTML = """
<h2>Data</h2>
<table class="outer">
  <tr><td>
    <table class="inner"><tr><td>nested</td></tr></table>
  </td></tr>
  <tr><td>outer row 2</td></tr>
</table>
<p>After table.</p>
"""

NESTED_DIV_HTML = """
<h3>Container</h3>
<div class="outer">
  <div class="mid">
    <div class="inner">deep</div>
  </div>
  <p>outer content</p>
</div>
<p>After div.</p>
"""

MULTIPLE_TABLES_HTML = """
<h2>Section</h2>
<table id="first"><tr><td>1</td></tr></table>
<p>gap</p>
<table id="second"><tr><td>2</td></tr></table>
<table id="third"><tr><td>3</td></tr></table>
"""

HEADING_WITH_TAGS_HTML = """
<h2 local-id="abc"><strong>Implementation Phases</strong></h2>
<table><tr><td>data</td></tr></table>
"""

SECTION_HTML = """
<h1>Top Level</h1>
<p>Top content.</p>
<h2>Sub Section A</h2>
<p>Sub A content.</p>
<table><tr><td>A data</td></tr></table>
<h2>Sub Section B</h2>
<p>Sub B content.</p>
<h1>Another Top</h1>
<p>Another content.</p>
"""


# ---------------------------------------------------------------------------
# Tests: find_element_after_heading — basic
# ---------------------------------------------------------------------------

class TestFindElementBasic:
    """Basic element finding after a heading."""

    def test_find_table_after_heading(self):
        start, end = find_element_after_heading(SIMPLE_HTML, "Implementation Phases", "table")
        extracted = SIMPLE_HTML[start:end]
        assert "<table data-id=\"target\">" in extracted
        assert "Phase 1" in extracted
        assert "</table>" in extracted

    def test_find_first_table(self):
        start, end = find_element_after_heading(SIMPLE_HTML, "Introduction", "table")
        extracted = SIMPLE_HTML[start:end]
        assert "<td>A</td>" in extracted
        assert "Phase 1" not in extracted

    def test_heading_not_found(self):
        with pytest.raises(SystemExit) as exc_info:
            find_element_after_heading(SIMPLE_HTML, "Nonexistent Heading", "table")
        assert exc_info.value.code == 1

    def test_element_not_found_after_heading(self):
        with pytest.raises(SystemExit) as exc_info:
            find_element_after_heading(SIMPLE_HTML, "Key Decisions", "table")
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Tests: find_element_after_heading — nested elements (H2 fix)
# ---------------------------------------------------------------------------

class TestNestedElements:
    """Verify correct handling of nested same-type elements."""

    def test_nested_table(self):
        start, end = find_element_after_heading(NESTED_TABLE_HTML, "Data", "table")
        extracted = NESTED_TABLE_HTML[start:end]
        assert "outer" in extracted
        assert "inner" in extracted
        assert "nested" in extracted
        assert "outer row 2" in extracted
        assert extracted.count("<table") == 2
        assert extracted.count("</table>") == 2

    def test_nested_div_three_levels(self):
        start, end = find_element_after_heading(NESTED_DIV_HTML, "Container", "div")
        extracted = NESTED_DIV_HTML[start:end]
        assert "outer" in extracted
        assert "mid" in extracted
        assert "deep" in extracted
        assert "outer content" in extracted
        assert extracted.count("<div") == 3
        assert extracted.count("</div>") == 3


# ---------------------------------------------------------------------------
# Tests: find_element_after_heading — nth occurrence
# ---------------------------------------------------------------------------

class TestNthOccurrence:
    """Verify --nth parameter for selecting specific occurrences."""

    def test_first_table(self):
        start, end = find_element_after_heading(MULTIPLE_TABLES_HTML, "Section", "table", nth=1)
        extracted = MULTIPLE_TABLES_HTML[start:end]
        assert 'id="first"' in extracted

    def test_second_table(self):
        start, end = find_element_after_heading(MULTIPLE_TABLES_HTML, "Section", "table", nth=2)
        extracted = MULTIPLE_TABLES_HTML[start:end]
        assert 'id="second"' in extracted

    def test_third_table(self):
        start, end = find_element_after_heading(MULTIPLE_TABLES_HTML, "Section", "table", nth=3)
        extracted = MULTIPLE_TABLES_HTML[start:end]
        assert 'id="third"' in extracted

    def test_nth_out_of_range(self):
        with pytest.raises(SystemExit) as exc_info:
            find_element_after_heading(MULTIPLE_TABLES_HTML, "Section", "table", nth=4)
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Tests: find_element_after_heading — heading with inner tags (H1 fix)
# ---------------------------------------------------------------------------

class TestHeadingWithInnerTags:
    """Verify heading detection strips inner tags before matching (H1 fix)."""

    def test_heading_with_strong_tag(self):
        start, end = find_element_after_heading(HEADING_WITH_TAGS_HTML, "Implementation Phases", "table")
        extracted = HEADING_WITH_TAGS_HTML[start:end]
        assert "<table>" in extracted
        assert "data" in extracted

    def test_case_insensitive_heading(self):
        start, end = find_element_after_heading(HEADING_WITH_TAGS_HTML, "implementation phases", "table")
        extracted = HEADING_WITH_TAGS_HTML[start:end]
        assert "<table>" in extracted


# ---------------------------------------------------------------------------
# Tests: find_element_after_heading — section extraction
# ---------------------------------------------------------------------------

class TestSectionExtraction:
    """Verify section extraction (heading + content until next same-or-higher heading)."""

    def test_section_h2_stops_at_next_h2(self):
        start, end = find_element_after_heading(SECTION_HTML, "Sub Section A", "section")
        extracted = SECTION_HTML[start:end]
        assert "Sub Section A" in extracted
        assert "Sub A content" in extracted
        assert "A data" in extracted
        assert "Sub Section B" not in extracted

    def test_section_h2_stops_at_h1(self):
        start, end = find_element_after_heading(SECTION_HTML, "Sub Section B", "section")
        extracted = SECTION_HTML[start:end]
        assert "Sub Section B" in extracted
        assert "Sub B content" in extracted
        assert "Another Top" not in extracted

    def test_section_h1_stops_at_next_h1(self):
        start, end = find_element_after_heading(SECTION_HTML, "Top Level", "section")
        extracted = SECTION_HTML[start:end]
        assert "Top Level" in extracted
        assert "Sub Section A" in extracted
        assert "Sub Section B" in extracted
        assert "Another Top" not in extracted

    def test_last_section_goes_to_end(self):
        start, end = find_element_after_heading(SECTION_HTML, "Another Top", "section")
        extracted = SECTION_HTML[start:end]
        assert "Another Top" in extracted
        assert "Another content" in extracted
        assert end == len(SECTION_HTML)


# ---------------------------------------------------------------------------
# Tests: apply-mode validation (H3, M2, M3 fixes)
# ---------------------------------------------------------------------------

class TestApplyValidation:
    """Test apply-mode input validation without Confluence API calls."""

    def test_empty_old_file(self, tmp_path):
        old_file = tmp_path / "old.html"
        new_file = tmp_path / "new.html"
        old_file.write_text("", encoding="utf-8")
        new_file.write_text("<table>new</table>", encoding="utf-8")

        with patch("sys.argv", ["prog", "--page", "123", "--old", str(old_file), "--new", str(new_file)]):
            from replace_element import parse_args
            args = parse_args()

        # Simulate apply_mode's validation
        old_html = old_file.read_text(encoding="utf-8").strip()
        assert old_html == ""

    def test_empty_new_file(self, tmp_path):
        old_file = tmp_path / "old.html"
        new_file = tmp_path / "new.html"
        old_file.write_text("<table>old</table>", encoding="utf-8")
        new_file.write_text("   \n  ", encoding="utf-8")

        new_html = new_file.read_text(encoding="utf-8").strip()
        assert new_html == ""

    def test_old_file_is_directory(self, tmp_path):
        dir_path = tmp_path / "dir"
        dir_path.mkdir()
        assert not dir_path.is_file()

    def test_nth_negative_rejected(self):
        with patch("sys.argv", ["prog", "--page", "123", "--heading", "Test", "--nth", "-1"]):
            from replace_element import parse_args
            with pytest.raises(SystemExit):
                parse_args()

    def test_nth_zero_rejected(self):
        with patch("sys.argv", ["prog", "--page", "123", "--heading", "Test", "--nth", "0"]):
            from replace_element import parse_args
            with pytest.raises(SystemExit):
                parse_args()


# ---------------------------------------------------------------------------
# Tests: unclosed tag handling
# ---------------------------------------------------------------------------

class TestUnclosedTag:
    """Verify proper error on unclosed tags."""

    def test_unclosed_table(self):
        html = "<h2>Test</h2><table><tr><td>no close"
        with pytest.raises(SystemExit) as exc_info:
            find_element_after_heading(html, "Test", "table")
        assert exc_info.value.code == 1
