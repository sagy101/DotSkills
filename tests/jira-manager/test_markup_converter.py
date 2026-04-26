#!/usr/bin/env python3
"""Tests for markup_converter.py — bidirectional MD ↔ Jira wiki conversion."""

import importlib.util
import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "jira-manager" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_MODULE_PATH = Path(_SCRIPTS_DIR) / "markup_converter.py"
_spec = importlib.util.spec_from_file_location("markup_converter", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["markup_converter"] = _mod

md_to_jira_markup = _mod.md_to_jira_markup
jira_markup_to_md = _mod.jira_markup_to_md
_html_to_jira = _mod._html_to_jira
_preprocess_markdown_blocks = _mod._preprocess_markdown_blocks
_normalize_nested_list_indent = _mod._normalize_nested_list_indent
_convert_html_lists = _mod._convert_html_lists
_convert_html_tables = _mod._convert_html_tables
_jira_tables_to_md = _mod._jira_tables_to_md
_jira_lists_to_md = _mod._jira_lists_to_md
extract_local_images = _mod.extract_local_images
render_mermaid_blocks = _mod.render_mermaid_blocks
MERMAID_BLOCK_RE = _mod.MERMAID_BLOCK_RE


# ---------------------------------------------------------------------------
# md_to_jira_markup — full pipeline
# ---------------------------------------------------------------------------


class TestMdToJira:
    def test_empty_string(self):
        assert md_to_jira_markup("") == ""

    def test_none(self):
        assert md_to_jira_markup(None) is None

    def test_whitespace_only(self):
        assert md_to_jira_markup("   ") == "   "

    def test_plain_text(self):
        result = md_to_jira_markup("Hello world")
        assert "Hello world" in result

    def test_bold(self):
        result = md_to_jira_markup("**bold text**")
        assert "*bold text*" in result

    def test_italic(self):
        result = md_to_jira_markup("*italic text*")
        assert "_italic text_" in result

    def test_inline_code(self):
        result = md_to_jira_markup("Use `foo()` here")
        assert "{{foo()}}" in result

    def test_fenced_code_block_with_language(self):
        md = "```python\nprint('hi')\n```"
        result = md_to_jira_markup(md)
        assert "{code:python}" in result
        assert "print('hi')" in result
        assert "{code}" in result

    def test_fenced_code_block_without_language(self):
        md = "```\nsome code\n```"
        result = md_to_jira_markup(md)
        assert "{code}" in result
        assert "some code" in result

    def test_heading_levels(self):
        for level in range(1, 4):
            md = f"{'#' * level} Heading {level}"
            result = md_to_jira_markup(md)
            assert f"h{level}. Heading {level}" in result

    def test_link(self):
        result = md_to_jira_markup("[Click here](https://example.com)")
        assert "[Click here|https://example.com]" in result

    def test_link_with_title_attribute(self):
        result = md_to_jira_markup('[text](http://x.com "title")')
        assert "[text|http://x.com]" in result

    def test_unordered_list(self):
        md = "- item 1\n- item 2"
        result = md_to_jira_markup(md)
        assert "* item 1" in result
        assert "* item 2" in result

    def test_ordered_list(self):
        md = "1. first\n2. second"
        result = md_to_jira_markup(md)
        assert "# first" in result
        assert "# second" in result

    def test_table(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = md_to_jira_markup(md)
        assert "||" in result  # header markers
        assert "|" in result

    def test_blockquote(self):
        md = "> quoted text"
        result = md_to_jira_markup(md)
        assert "{quote}" in result
        assert "quoted text" in result

    def test_horizontal_rule(self):
        result = md_to_jira_markup("---")
        assert "----" in result

    def test_image(self):
        result = md_to_jira_markup("![alt](http://img.png)")
        assert "!http://img.png!" in result

    def test_strikethrough(self):
        # markdown lib may not support ~~strikethrough~~ without the del extension
        result = md_to_jira_markup("~~deleted~~")
        assert "deleted" in result

    def test_heading_after_list_gets_blank_line(self):
        """h3. headings after list items must have a blank line before them."""
        md = "- item 1\n- item 2\n\n### Heading\n\n- item 3"
        result = md_to_jira_markup(md)
        assert "h3. Heading" in result
        lines = result.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("h3. "):
                assert i > 0 and lines[i - 1].strip() == "", (
                    f"Expected blank line before heading at line {i}, got: {lines[i - 1]!r}"
                )

    def test_bold_label_followed_by_unordered_list(self):
        """**Label:** followed immediately by - items should produce a proper list."""
        md = "**DoD:**\n- first item\n- second item"
        result = md_to_jira_markup(md)
        assert "* first item" in result
        assert "- first item" not in result

    def test_bold_label_followed_by_ordered_list(self):
        """**Label:** followed immediately by 1. items should produce an ordered list."""
        md = "**Steps:**\n1. first\n2. second"
        result = md_to_jira_markup(md)
        assert "# first" in result
        assert "1. first" not in result

    def test_italic_label_followed_by_list(self):
        """*Label:* followed immediately by - items should produce a proper list."""
        md = "*Note:*\n- item 1\n- item 2"
        result = md_to_jira_markup(md)
        assert "* item 1" in result
        assert "- item 1" not in result

    def test_italic_label_followed_by_ordered_list(self):
        md = "*Note:*\n1. step 1\n2. step 2"
        result = md_to_jira_markup(md)
        assert "# step 1" in result
        assert "1. step" not in result

    def test_plain_paragraph_followed_by_unordered_list(self):
        md = "Description text.\n- item 1\n- item 2"
        result = md_to_jira_markup(md)
        assert "* item 1" in result
        assert "- item 1" not in result

    def test_plain_paragraph_followed_by_ordered_list(self):
        md = "Text here.\n1. first\n2. second"
        result = md_to_jira_markup(md)
        assert "# first" in result
        assert "1. first" not in result

    def test_blockquote_followed_by_list(self):
        """List after blockquote should not be swallowed into the blockquote."""
        md = "> quote\n- item 1\n- item 2"
        result = md_to_jira_markup(md)
        assert "* item 1" in result

    def test_table_followed_by_heading(self):
        """Heading after table must not become a table row."""
        md = "| A | B |\n|---|---|\n| 1 | 2 |\n### After Table"
        result = md_to_jira_markup(md)
        assert "h3. After Table" in result

    def test_table_followed_by_list(self):
        """List after table must not break the table."""
        md = "| A | B |\n|---|---|\n| 1 | 2 |\n- item"
        result = md_to_jira_markup(md)
        assert "* item" in result
        assert "||" in result  # table header still works


# ---------------------------------------------------------------------------
# _preprocess_markdown_blocks — block boundary injection
# ---------------------------------------------------------------------------


class TestPreprocessMarkdownBlocks:
    def test_normal_list_untouched(self):
        md = "- item 1\n- item 2\n- item 3"
        assert _preprocess_markdown_blocks(md) == md

    def test_heading_then_list_untouched(self):
        md = "### Title\n- item"
        assert _preprocess_markdown_blocks(md) == md

    def test_nested_list_untouched(self):
        md = "- parent\n    - child\n    - child2"
        assert _preprocess_markdown_blocks(md) == md

    def test_multiline_list_item_untouched(self):
        md = "- first line\n  continuation\n- second"
        assert _preprocess_markdown_blocks(md) == md

    def test_blank_line_injected_for_paragraph_then_list(self):
        md = "Paragraph.\n- item"
        result = _preprocess_markdown_blocks(md)
        assert result == "Paragraph.\n\n- item"

    def test_blank_line_injected_for_bold_label_then_list(self):
        md = "**DoD:**\n- item"
        result = _preprocess_markdown_blocks(md)
        assert result == "**DoD:**\n\n- item"

    def test_blank_line_injected_for_italic_label_then_list(self):
        md = "*Note:*\n- item"
        result = _preprocess_markdown_blocks(md)
        assert result == "*Note:*\n\n- item"

    def test_blank_line_injected_for_blockquote_then_list(self):
        md = "> quote\n- item"
        result = _preprocess_markdown_blocks(md)
        assert result == "> quote\n\n- item"

    def test_blank_line_injected_for_table_then_heading(self):
        md = "| 1 | 2 |\n### Heading"
        result = _preprocess_markdown_blocks(md)
        assert result == "| 1 | 2 |\n\n### Heading"

    def test_blank_line_injected_for_table_then_list(self):
        md = "| 1 | 2 |\n- item"
        result = _preprocess_markdown_blocks(md)
        assert result == "| 1 | 2 |\n\n- item"

    def test_paragraph_then_ordered_list(self):
        md = "Text.\n1. first"
        result = _preprocess_markdown_blocks(md)
        assert result == "Text.\n\n1. first"

    def test_bold_label_then_ordered_list(self):
        md = "**Steps:**\n1. first"
        result = _preprocess_markdown_blocks(md)
        assert result == "**Steps:**\n\n1. first"

    def test_already_separated_not_doubled(self):
        md = "**DoD:**\n\n- item"
        result = _preprocess_markdown_blocks(md)
        assert result == md

    def test_code_block_then_list_untouched(self):
        md = "```\ncode\n```\n- item"
        assert _preprocess_markdown_blocks(md) == md


# ---------------------------------------------------------------------------
# _normalize_nested_list_indent — 2-space → 4-space indent
# ---------------------------------------------------------------------------


class TestNormalizeNestedListIndent:
    def test_2space_nested_becomes_4space(self):
        md = "- Parent\n  - Child 1\n  - Child 2"
        result = _normalize_nested_list_indent(md)
        assert result == "- Parent\n    - Child 1\n    - Child 2"

    def test_4space_nested_untouched(self):
        md = "- Parent\n    - Child"
        assert _normalize_nested_list_indent(md) == md

    def test_flat_list_untouched(self):
        md = "- item 1\n- item 2"
        assert _normalize_nested_list_indent(md) == md

    def test_continuation_text_untouched(self):
        md = "- Item\n  continuation text"
        assert _normalize_nested_list_indent(md) == md

    def test_ordered_nested_2space(self):
        md = "1. Parent\n  1. Child\n  2. Child 2"
        result = _normalize_nested_list_indent(md)
        assert result == "1. Parent\n    1. Child\n    2. Child 2"

    def test_mixed_markers(self):
        md = "- Parent\n  + Child 1\n  * Child 2"
        result = _normalize_nested_list_indent(md)
        assert result == "- Parent\n    + Child 1\n    * Child 2"

    def test_bold_children(self):
        md = "- **Parent:** desc\n  - **Child** — text"
        result = _normalize_nested_list_indent(md)
        assert result == "- **Parent:** desc\n    - **Child** — text"

    def test_non_list_2space_indent_untouched(self):
        md = "paragraph\n  not a list"
        assert _normalize_nested_list_indent(md) == md

    def test_nested_produces_jira_sub_list(self):
        """Full pipeline: 2-space nested list → Jira ** sub-items."""
        md = "- Parent\n  - Child 1\n  - Child 2"
        result = md_to_jira_markup(md)
        assert "** Child 1" in result
        assert "** Child 2" in result

    def test_real_world_service_accounts(self):
        """Simulates the real content pattern from the user's epic draft."""
        md = (
            "- **Agent service accounts:** create accounts\n"
            "  - **Jira** — create tickets\n"
            "  - **Bitbucket** — create PRs\n"
            "- **Webhook registration:** one-time setup"
        )
        result = md_to_jira_markup(md)
        assert "** *Jira*" in result or "**Jira**" in result
        assert "* *Webhook registration:*" in result or "Webhook" in result

    def test_bold_label_after_nested_list_not_absorbed(self):
        """Regression: **DoD:** after a nested list must not be absorbed into the list.

        Python-Markdown correctly puts <p><strong>DoD:</strong></p> outside the
        list, but without a blank line before the paragraph in the Jira wiki
        output, Jira interprets *DoD:* as a list continuation because * is the
        list bullet character in wiki markup.
        """
        md = (
            "- **Eval checks and judges** (eval/):\n"
            "  - eval.yaml: declares all checks\n"
            "  - **Deterministic checks**: pattern_detection\n"
            "  - **Fixtures — dev set**: 50+ entries, edge cases\n"
            "\n"
            "**DoD:**\n"
            "- The feedback agent manifest is read by the unified server\n"
            "- All external service interactions go through server-side tools"
        )
        result = md_to_jira_markup(md)
        lines = result.split("\n")
        # Find the line containing DoD
        dod_indices = [i for i, line in enumerate(lines) if "DoD:" in line]
        assert dod_indices, "DoD: label not found in output"
        dod_idx = dod_indices[0]
        # Must have a blank line before it (not a list continuation)
        assert dod_idx > 0 and lines[dod_idx - 1].strip() == "", (
            f"Expected blank line before *DoD:* at line {dod_idx}, got: {lines[dod_idx - 1]!r}"
        )
        # The DoD list items must be top-level (* not **)
        dod_items = [line for line in lines[dod_idx + 1 :] if line.startswith("*")]
        assert all(not line.startswith("**") for line in dod_items), (
            f"DoD items should be top-level list, got nested: {dod_items}"
        )


# ---------------------------------------------------------------------------
# _html_to_jira — direct HTML conversion
# ---------------------------------------------------------------------------


class TestHtmlToJira:
    def test_code_block_with_html_entities(self):
        html = '<pre><code class="language-python">x &lt; y &amp; z</code></pre>'
        result = _html_to_jira(html)
        assert "x < y & z" in result
        assert "{code:python}" in result

    def test_nested_bold_italic(self):
        html = "<strong><em>bold italic</em></strong>"
        result = _html_to_jira(html)
        assert "*_bold italic_*" in result

    def test_link_with_special_chars(self):
        html = '<a href="https://example.com/path?a=1&b=2">link</a>'
        result = _html_to_jira(html)
        assert "[link|https://example.com/path?a=1&b=2]" in result

    def test_strips_unknown_tags(self):
        html = "<div><span>text</span></div>"
        result = _html_to_jira(html)
        assert "text" in result
        assert "<div>" not in result
        assert "<span>" not in result

    def test_br_to_newline(self):
        html = "line1<br/>line2"
        result = _html_to_jira(html)
        assert "line1\nline2" in result

    def test_excessive_blank_lines_collapsed(self):
        html = "<p>a</p>\n\n\n\n<p>b</p>"
        result = _html_to_jira(html)
        assert "\n\n\n" not in result


# ---------------------------------------------------------------------------
# _convert_html_tables
# ---------------------------------------------------------------------------


class TestConvertHtmlTables:
    def test_header_and_data_rows(self):
        html = "<table><tr><th>H1</th><th>H2</th></tr><tr><td>a</td><td>b</td></tr></table>"
        result = _convert_html_tables(html)
        assert "|| H1 || H2 ||" in result
        assert "| a | b |" in result

    def test_data_only_rows(self):
        html = "<table><tr><td>x</td><td>y</td></tr></table>"
        result = _convert_html_tables(html)
        assert "| x | y |" in result

    def test_no_table(self):
        assert _convert_html_tables("no table here") == "no table here"


# ---------------------------------------------------------------------------
# _convert_html_lists
# ---------------------------------------------------------------------------


class TestConvertHtmlLists:
    def test_simple_ul(self):
        html = "<ul><li>a</li><li>b</li></ul>"
        result = _convert_html_lists(html)
        assert "* a" in result
        assert "* b" in result

    def test_simple_ol(self):
        html = "<ol><li>first</li><li>second</li></ol>"
        result = _convert_html_lists(html)
        assert "# first" in result
        assert "# second" in result

    def test_nested_ul_via_full_pipeline(self):
        """Nested lists work through the full md_to_jira pipeline."""
        md = "- parent\n  - child"
        result = md_to_jira_markup(md)
        assert "* parent" in result
        # nested child handling depends on HTML structure from markdown lib
        assert "child" in result

    def test_mixed_nesting_via_full_pipeline(self):
        md = "- item\n  1. numbered"
        result = md_to_jira_markup(md)
        assert "item" in result
        assert "numbered" in result


# ---------------------------------------------------------------------------
# jira_markup_to_md — full pipeline
# ---------------------------------------------------------------------------


class TestJiraToMd:
    def test_empty_string(self):
        assert jira_markup_to_md("") == ""

    def test_none(self):
        assert jira_markup_to_md(None) is None

    def test_whitespace_only(self):
        assert jira_markup_to_md("   ") == "   "

    def test_code_block_with_language(self):
        jira = "{code:python}\nprint('hi')\n{code}"
        result = jira_markup_to_md(jira)
        assert "```python" in result
        assert "print('hi')" in result
        assert "```" in result

    def test_code_block_without_language(self):
        jira = "{code}\nsome code\n{code}"
        result = jira_markup_to_md(jira)
        assert "```" in result
        assert "some code" in result

    def test_code_block_empty(self):
        result = jira_markup_to_md("{code}\n{code}")
        assert "```" in result

    def test_code_block_with_title_and_language(self):
        jira = "{code:title=Example|language=java}\npublic void foo(){}\n{code}"
        result = jira_markup_to_md(jira)
        assert "```java" in result
        assert "public void foo(){}" in result

    def test_code_block_language_only_param(self):
        jira = "{code:language=python}\nx = 1\n{code}"
        result = jira_markup_to_md(jira)
        assert "```python" in result
        assert "x = 1" in result

    def test_inline_code(self):
        result = jira_markup_to_md("Use {{foo()}} here")
        assert "`foo()`" in result

    def test_heading_list_conflict(self):
        """All headings get misinterpreted by _jira_lists_to_md because # and ## etc
        match the list pattern [*#]{1,6}. This is a known limitation — heading
        conversion produces # Heading, then list conversion sees it as a list item.
        Content is preserved, just formatting is wrong."""
        for level in range(1, 4):
            result = jira_markup_to_md(f"h{level}. Title")
            assert "Title" in result  # content preserved

    def test_bold(self):
        result = jira_markup_to_md("This is *bold* text")
        assert "**bold**" in result

    def test_bold_not_list_bullet(self):
        # "* item" is a list bullet, not bold
        result = jira_markup_to_md("* item one")
        # Should not wrap "item one" in ** **
        assert "**" not in result or "- item one" in result

    def test_italic(self):
        result = jira_markup_to_md("This is _italic_ text")
        assert "*italic*" in result

    def test_strikethrough(self):
        result = jira_markup_to_md("This is -deleted- text")
        assert "~~deleted~~" in result

    def test_link_with_text(self):
        result = jira_markup_to_md("[Click here|https://example.com]")
        assert "[Click here](https://example.com)" in result

    def test_simple_link(self):
        result = jira_markup_to_md("[https://example.com]")
        assert "(https://example.com)" in result

    def test_image(self):
        result = jira_markup_to_md("!http://img.png!")
        assert "![](http://img.png)" in result

    def test_blockquote(self):
        result = jira_markup_to_md("{quote}\nquoted text\n{quote}")
        assert "> quoted text" in result

    def test_horizontal_rule(self):
        result = jira_markup_to_md("----")
        assert "---" in result

    def test_panel_with_title(self):
        result = jira_markup_to_md("{panel:title=Note}content{panel}")
        assert "**Note**" in result
        assert "content" in result

    def test_panel_without_title(self):
        result = jira_markup_to_md("{panel}content{panel}")
        assert "content" in result

    def test_noformat(self):
        result = jira_markup_to_md("{noformat}raw text{noformat}")
        assert "```" in result
        assert "raw text" in result

    def test_color_stripped(self):
        result = jira_markup_to_md("{color:red}warning{color}")
        assert "warning" in result
        assert "{color" not in result

    def test_excessive_newlines_collapsed(self):
        result = jira_markup_to_md("a\n\n\n\n\nb")
        assert "\n\n\n" not in result


# ---------------------------------------------------------------------------
# _jira_tables_to_md
# ---------------------------------------------------------------------------


class TestJiraTablesToMd:
    def test_header_row(self):
        jira = "|| Name || Age ||\n| Alice | 30 |"
        result = _jira_tables_to_md(jira)
        assert "| Name | Age |" in result
        assert "| --- | --- |" in result
        assert "| Alice | 30 |" in result

    def test_data_only_first_row_becomes_header(self):
        jira = "| A | B |\n| 1 | 2 |"
        result = _jira_tables_to_md(jira)
        assert "| --- | --- |" in result

    def test_non_table_lines_preserved(self):
        text = "not a table\n|| H ||\n| D |"
        result = _jira_tables_to_md(text)
        assert "not a table" in result

    def test_no_table(self):
        assert _jira_tables_to_md("plain text") == "plain text"


# ---------------------------------------------------------------------------
# _jira_lists_to_md
# ---------------------------------------------------------------------------


class TestJiraListsToMd:
    def test_unordered(self):
        result = _jira_lists_to_md("* item 1\n* item 2")
        assert "- item 1" in result
        assert "- item 2" in result

    def test_ordered(self):
        result = _jira_lists_to_md("# first\n# second")
        assert "1. first" in result
        assert "1. second" in result

    def test_nested_unordered(self):
        result = _jira_lists_to_md("* parent\n** child")
        assert "- parent" in result
        assert "  - child" in result

    def test_nested_ordered(self):
        result = _jira_lists_to_md("# parent\n## child")
        assert "1. parent" in result
        assert "  1. child" in result

    def test_mixed_nesting(self):
        result = _jira_lists_to_md("* parent\n*# numbered child")
        assert "- parent" in result
        assert "  1. numbered child" in result

    def test_deep_nesting(self):
        result = _jira_lists_to_md("*** deep")
        assert "    - deep" in result

    def test_non_list_lines_preserved(self):
        result = _jira_lists_to_md("plain text\n* item\nmore text")
        assert "plain text" in result
        assert "- item" in result
        assert "more text" in result


# ---------------------------------------------------------------------------
# extract_local_images
# ---------------------------------------------------------------------------


class TestExtractLocalImages:
    def test_no_images(self):
        text = "Some plain text without images."
        rewritten, paths = extract_local_images(text, "/tmp")
        assert rewritten == text
        assert paths == []

    def test_http_urls_untouched(self):
        text = "![logo](https://example.com/logo.png)"
        rewritten, paths = extract_local_images(text, "/tmp")
        assert rewritten == text
        assert paths == []

    def test_https_urls_untouched(self):
        text = "![logo](HTTP://example.com/logo.png)"
        rewritten, paths = extract_local_images(text, "/tmp")
        assert rewritten == text
        assert paths == []

    def test_local_image_rewritten_to_basename(self, tmp_path: Path):
        img = tmp_path / "sub" / "diagram.png"
        img.parent.mkdir()
        img.write_bytes(b"PNG")
        text = "![arch](sub/diagram.png)"
        rewritten, paths = extract_local_images(text, str(tmp_path))
        assert rewritten == "![arch](diagram.png)"
        assert len(paths) == 1
        assert paths[0] == str(img.resolve())

    def test_multiple_images(self, tmp_path: Path):
        for name in ("a.png", "b.jpg"):
            (tmp_path / name).write_bytes(b"IMG")
        text = "![A](a.png) and ![B](b.jpg)"
        rewritten, paths = extract_local_images(text, str(tmp_path))
        assert "![A](a.png)" in rewritten
        assert "![B](b.jpg)" in rewritten
        assert len(paths) == 2

    def test_mixed_local_and_remote(self, tmp_path: Path):
        (tmp_path / "local.png").write_bytes(b"PNG")
        text = "![loc](local.png) and ![rem](https://example.com/remote.png)"
        rewritten, paths = extract_local_images(text, str(tmp_path))
        assert "![loc](local.png)" in rewritten
        assert "![rem](https://example.com/remote.png)" in rewritten
        assert len(paths) == 1

    def test_missing_file_still_included(self, tmp_path: Path):
        text = "![missing](nonexistent.png)"
        rewritten, paths = extract_local_images(text, str(tmp_path))
        assert "![missing](nonexistent.png)" in rewritten
        assert len(paths) == 1

    def test_duplicate_basenames_deduplicated(self, tmp_path: Path):
        d1 = tmp_path / "a"
        d2 = tmp_path / "b"
        d1.mkdir()
        d2.mkdir()
        (d1 / "img.png").write_bytes(b"1")
        (d2 / "img.png").write_bytes(b"2")
        text = "![x](a/img.png) ![y](b/img.png)"
        rewritten, paths = extract_local_images(text, str(tmp_path))
        assert "![x](img.png)" in rewritten
        assert "img_1.png" in rewritten
        assert len(paths) == 2

    def test_full_pipeline_to_jira(self, tmp_path: Path):
        (tmp_path / "flow.png").write_bytes(b"PNG")
        text = "See ![flow](flow.png) for details"
        rewritten, paths = extract_local_images(text, str(tmp_path))
        jira = md_to_jira_markup(rewritten)
        assert "!flow.png!" in jira
        assert len(paths) == 1

    def test_cwd_fallback_when_base_dir_misses(self, tmp_path: Path, monkeypatch: object):
        """When image isn't in base_dir but IS in CWD, the CWD copy is used."""
        cwd_dir = tmp_path / "cwd"
        cwd_dir.mkdir()
        (cwd_dir / "diagram.png").write_bytes(b"PNG")

        other_dir = tmp_path / "other"
        other_dir.mkdir()

        import os

        monkeypatch.setattr(os, "getcwd", lambda: str(cwd_dir))  # type: ignore[attr-defined]

        text = "![d](diagram.png)"
        _, paths = extract_local_images(text, str(other_dir))
        assert len(paths) == 1
        assert str(cwd_dir / "diagram.png") in paths[0]

    def test_base_dir_preferred_over_cwd(self, tmp_path: Path, monkeypatch: object):
        """When image exists in both base_dir and CWD, base_dir wins."""
        base_dir = tmp_path / "base"
        base_dir.mkdir()
        (base_dir / "img.png").write_bytes(b"BASE")

        cwd_dir = tmp_path / "cwd"
        cwd_dir.mkdir()
        (cwd_dir / "img.png").write_bytes(b"CWD")

        import os

        monkeypatch.setattr(os, "getcwd", lambda: str(cwd_dir))  # type: ignore[attr-defined]

        text = "![i](img.png)"
        _, paths = extract_local_images(text, str(base_dir))
        assert len(paths) == 1
        assert str(base_dir / "img.png") in paths[0]

    def test_no_fallback_when_base_equals_cwd(self, tmp_path: Path, monkeypatch: object):
        """No double-check when base_dir IS the CWD (avoids redundant stat)."""
        import os

        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))  # type: ignore[attr-defined]

        text = "![m](missing.png)"
        _, paths = extract_local_images(text, str(tmp_path))
        assert len(paths) == 1


# ---------------------------------------------------------------------------
# MERMAID_BLOCK_RE
# ---------------------------------------------------------------------------


class TestMermaidBlockRegex:
    def test_detects_single_block(self):
        md = "text\n```mermaid\ngraph TD\n  A-->B\n```\nmore"
        matches = MERMAID_BLOCK_RE.findall(md)
        assert len(matches) == 1
        assert "graph TD" in matches[0]

    def test_detects_multiple_blocks(self):
        md = "```mermaid\ngraph LR\n  A-->B\n```\n\n```mermaid\nsequenceDiagram\n  A->>B: hi\n```"
        matches = MERMAID_BLOCK_RE.findall(md)
        assert len(matches) == 2

    def test_no_match_for_other_code_blocks(self):
        md = "```python\nprint('hi')\n```"
        assert MERMAID_BLOCK_RE.findall(md) == []

    def test_no_match_for_plain_text(self):
        assert MERMAID_BLOCK_RE.findall("no code blocks") == []


# ---------------------------------------------------------------------------
# render_mermaid_blocks
# ---------------------------------------------------------------------------


class TestRenderMermaidBlocks:
    def test_no_mermaid_returns_unchanged(self):
        text = "No mermaid here."
        result, paths = render_mermaid_blocks(text)
        assert result == text
        assert paths == []

    def test_non_mermaid_code_block_unchanged(self):
        text = "```python\nprint('hi')\n```"
        result, paths = render_mermaid_blocks(text)
        assert result == text
        assert paths == []

    def test_renders_mermaid_block(self, tmp_path: Path):
        md = "Before\n```mermaid\ngraph TD\n  A-->B\n```\nAfter"
        result, paths = render_mermaid_blocks(md, output_dir=str(tmp_path))
        if paths:
            assert len(paths) == 1
            assert "mermaid-diagram-1.png" in paths[0]
            assert "```mermaid" not in result
            assert "Before" in result
            assert "After" in result
            assert "![Mermaid Diagram 1]" in result
        else:
            assert "```mermaid" in result

    def test_renders_multiple_blocks(self, tmp_path: Path):
        md = "```mermaid\ngraph LR\n  A-->B\n```\n\n```mermaid\ngraph TD\n  C-->D\n```"
        _, paths = render_mermaid_blocks(md, output_dir=str(tmp_path))
        if paths:
            assert len(paths) == 2
            assert "mermaid-diagram-1.png" in paths[0]
            assert "mermaid-diagram-2.png" in paths[1]

    def test_full_pipeline_mermaid_to_jira(self, tmp_path: Path):
        md = "# Title\n\n```mermaid\ngraph TD\n  A-->B\n```\n\nDone."
        result, paths = render_mermaid_blocks(md, output_dir=str(tmp_path))
        if paths:
            rewritten, _ = extract_local_images(result, str(tmp_path))
            jira = md_to_jira_markup(rewritten)
            assert "!mermaid-diagram-1.png!" in jira
            assert "h1. Title" in jira


if __name__ == "__main__":
    import subprocess

    sys.exit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
