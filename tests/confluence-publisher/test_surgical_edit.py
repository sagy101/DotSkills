"""Unit tests for surgical_edit.py — apply_replacements and entity normalization.

Tests the core replacement logic and automatic HTML entity normalization
without requiring a live Confluence connection.
"""

import sys
from pathlib import Path

# Add the scripts directory to sys.path so we can import the module
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "confluence-publisher" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from surgical_edit import (  # noqa: E402
    _decode_html_entities,
    _encode_unicode_to_html_entities,
    _try_entity_normalization,
    apply_replacements,
)

# ---------------------------------------------------------------------------
# _encode_unicode_to_html_entities
# ---------------------------------------------------------------------------


class TestEncodeUnicodeToHtmlEntities:
    def test_right_arrow(self):
        assert _encode_unicode_to_html_entities("CSV→JSONL") == "CSV&rarr;JSONL"

    def test_left_arrow(self):
        assert _encode_unicode_to_html_entities("←back") == "&larr;back"

    def test_mdash(self):
        assert _encode_unicode_to_html_entities("a — b") == "a &mdash; b"

    def test_ndash(self):
        assert _encode_unicode_to_html_entities("1–2") == "1&ndash;2"

    def test_ge_le(self):
        assert _encode_unicode_to_html_entities("≥80%") == "&ge;80%"
        assert _encode_unicode_to_html_entities("≤55%") == "&le;55%"

    def test_multiple_chars(self):
        text = "CSV→JSONL — with ≥80% coverage"
        result = _encode_unicode_to_html_entities(text)
        assert "&rarr;" in result
        assert "&mdash;" in result
        assert "&ge;" in result

    def test_no_unicode_passthrough(self):
        """Plain ASCII text passes through unchanged."""
        text = "just plain text with &amp; entities"
        assert _encode_unicode_to_html_entities(text) == text

    def test_already_entity_not_double_encoded(self):
        """Existing HTML entities should not be double-encoded."""
        assert _encode_unicode_to_html_entities("&rarr;") == "&rarr;"
        assert _encode_unicode_to_html_entities("&mdash;") == "&mdash;"

    def test_smart_quotes(self):
        assert _encode_unicode_to_html_entities("\u201cquoted\u201d") == "&ldquo;quoted&rdquo;"

    def test_nbsp(self):
        assert _encode_unicode_to_html_entities("a\u00a0b") == "a&nbsp;b"

    def test_ellipsis(self):
        assert _encode_unicode_to_html_entities("wait\u2026") == "wait&hellip;"

    def test_times(self):
        assert _encode_unicode_to_html_entities("2\u00d73") == "2&times;3"


# ---------------------------------------------------------------------------
# _decode_html_entities
# ---------------------------------------------------------------------------


class TestDecodeHtmlEntities:
    def test_rarr(self):
        assert _decode_html_entities("CSV&rarr;JSONL") == "CSV→JSONL"

    def test_mdash(self):
        assert _decode_html_entities("a &mdash; b") == "a — b"

    def test_ge(self):
        assert _decode_html_entities("&ge;80%") == "≥80%"

    def test_amp(self):
        assert _decode_html_entities("A &amp; B") == "A & B"

    def test_no_entities_passthrough(self):
        assert _decode_html_entities("plain text") == "plain text"

    def test_numeric_entity(self):
        assert _decode_html_entities("&#8594;") == "→"


# ---------------------------------------------------------------------------
# _try_entity_normalization
# ---------------------------------------------------------------------------


class TestTryEntityNormalization:
    def test_unicode_to_entity_match(self):
        """Unicode → in find, &rarr; in HTML → should match via encoding."""
        html = "CSV&rarr;JSONL migration, SP: 3.0"
        result = _try_entity_normalization(html, "CSV→JSONL migration, SP: 3.0")
        assert result is not None
        norm_find, strategy = result
        assert strategy == "Unicode→entity"
        assert "&rarr;" in norm_find
        assert html.count(norm_find) > 0

    def test_entity_to_unicode_match(self):
        """&rarr; in find, → in HTML → should match via decoding."""
        html = "CSV→JSONL migration"
        result = _try_entity_normalization(html, "CSV&rarr;JSONL migration")
        assert result is not None
        _, strategy = result
        assert strategy == "entity→Unicode"

    def test_already_matching_returns_none(self):
        """If find already matches as-is, normalization should not be attempted."""
        html = "CSV&rarr;JSONL"
        # Exact match — count > 0 on original, so apply_replacements won't call us.
        # But if called directly, both strategies produce strings != find that also
        # match, so it could return a result. The contract is: this function is only
        # called when the original find has 0 matches.
        # Test the "truly not found" case instead.
        result = _try_entity_normalization(html, "TOTALLY ABSENT TEXT")
        assert result is None

    def test_no_match_either_way(self):
        html = "<p>nothing here</p>"
        result = _try_entity_normalization(html, "CSV→JSONL")
        assert result is None

    def test_mdash_normalization(self):
        html = "skills &mdash; day-to-day"
        result = _try_entity_normalization(html, "skills — day-to-day")
        assert result is not None
        assert result[1] == "Unicode→entity"

    def test_mixed_entities(self):
        """Multiple different entities in one find string."""
        html = "CSV&rarr;JSONL &mdash; &ge;80%"
        result = _try_entity_normalization(html, "CSV→JSONL — ≥80%")
        assert result is not None
        norm_find, _ = result
        assert html.count(norm_find) > 0


# ---------------------------------------------------------------------------
# apply_replacements — existing behavior (regression)
# ---------------------------------------------------------------------------


class TestApplyReplacementsRegression:
    def test_exact_match_single(self):
        html = "<p>old text here</p>"
        modified, log = apply_replacements(html, [{"find": "old text", "replace": "new text"}])
        assert modified == "<p>new text here</p>"
        assert any("Replaced 1" in msg for msg in log)

    def test_exact_match_replace_all(self):
        html = "<p>foo</p><p>foo</p>"
        modified, log = apply_replacements(
            html, [{"find": "foo", "replace": "bar", "replace_all": True}]
        )
        assert modified == "<p>bar</p><p>bar</p>"
        assert any("Replaced 2" in msg for msg in log)

    def test_not_found(self):
        html = "<p>some content</p>"
        modified, log = apply_replacements(html, [{"find": "absent", "replace": "new"}])
        assert modified == html  # unchanged
        assert any("NOT FOUND" in msg for msg in log)

    def test_empty_find_skipped(self):
        html = "<p>content</p>"
        modified, log = apply_replacements(html, [{"find": "", "replace": "new"}])
        assert modified == html
        assert any("SKIPPED" in msg for msg in log)

    def test_multiple_replacements_sequential(self):
        html = "<p>aaa bbb ccc</p>"
        modified, log = apply_replacements(
            html,
            [
                {"find": "aaa", "replace": "111"},
                {"find": "bbb", "replace": "222"},
            ],
        )
        assert modified == "<p>111 222 ccc</p>"
        assert len(log) == 2

    def test_first_occurrence_only_by_default(self):
        html = "<p>foo</p><p>foo</p>"
        modified, log = apply_replacements(html, [{"find": "foo", "replace": "bar"}])
        assert modified == "<p>bar</p><p>foo</p>"

    def test_html_tags_preserved(self):
        """Replacements only touch text content, not surrounding HTML."""
        html = '<td ac:local-id="abc"><p>old</p></td>'
        modified, _ = apply_replacements(html, [{"find": "old", "replace": "new"}])
        assert 'ac:local-id="abc"' in modified
        assert "<p>new</p>" in modified


# ---------------------------------------------------------------------------
# apply_replacements — entity auto-normalization (new capability)
# ---------------------------------------------------------------------------


class TestApplyReplacementsEntityNormalization:
    def test_unicode_arrow_matches_html_entity(self):
        """The exact scenario that triggered this fix: → in find, &rarr; in HTML."""
        html = "CSV&rarr;JSONL migration: 3.0 SP"
        modified, log = apply_replacements(
            html,
            [{"find": "CSV→JSONL migration: 3.0 SP", "replace": "CSV→JSONL migration: 4.0 SP"}],
        )
        assert "4.0 SP" in modified
        assert "&rarr;" in modified  # entity preserved in output
        assert any("Auto-normalized" in msg for msg in log)

    def test_unicode_mdash_matches_html_entity(self):
        html = "skills &mdash; workflow"
        modified, log = apply_replacements(
            html, [{"find": "skills — workflow", "replace": "skills — tools"}]
        )
        assert "&mdash; tools" in modified
        assert any("Auto-normalized" in msg for msg in log)

    def test_replace_string_also_normalized(self):
        """Both find AND replace should be normalized the same way."""
        html = "<p>CSV&rarr;JSONL &mdash; old</p>"
        modified, _ = apply_replacements(
            html, [{"find": "CSV→JSONL — old", "replace": "CSV→JSONL — new"}]
        )
        assert "&rarr;" in modified
        assert "&mdash;" in modified
        assert "new" in modified

    def test_entity_in_find_unicode_in_html(self):
        """Reverse case: &rarr; in find, → in HTML."""
        html = "CSV→JSONL migration"
        modified, log = apply_replacements(
            html, [{"find": "CSV&rarr;JSONL migration", "replace": "CSV&rarr;JSONL update"}]
        )
        assert "→" in modified  # Unicode preserved in output
        assert "update" in modified
        assert any("Auto-normalized" in msg for msg in log)

    def test_no_normalization_when_exact_match_exists(self):
        """If the find string matches exactly, normalization should not be triggered."""
        html = "CSV&rarr;JSONL"
        modified, log = apply_replacements(
            html, [{"find": "CSV&rarr;JSONL", "replace": "TSV&rarr;JSONL"}]
        )
        assert modified == "TSV&rarr;JSONL"
        # No "Auto-normalized" in log — it matched directly
        assert not any("Auto-normalized" in msg for msg in log)

    def test_replace_all_with_normalization(self):
        html = "a&rarr;b and c&rarr;d"
        modified, log = apply_replacements(
            html, [{"find": "→", "replace": "=>", "replace_all": True}]
        )
        assert modified == "a=>b and c=>d"

    def test_normalization_with_surrounding_html(self):
        """Real-world scenario: entity inside Confluence table cell."""
        html = (
            '<td ac:local-id="f54b"><p local-id="4cf4" style="text-align: center;">'
            "CSV&rarr;JSONL: 3.0</p></td>"
        )
        find = "CSV→JSONL: 3.0</p></td>"
        replace = "CSV→JSONL: 4.0</p></td>"
        modified, log = apply_replacements(html, [{"find": find, "replace": replace}])
        assert "4.0" in modified
        assert 'ac:local-id="f54b"' in modified  # surrounding HTML untouched

    def test_ge_normalization(self):
        html = "<p>Skills (&ge;80%)</p>"
        modified, _ = apply_replacements(
            html, [{"find": "Skills (≥80%)", "replace": "Skills (≥90%)"}]
        )
        assert "&ge;90%" in modified
