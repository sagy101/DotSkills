#!/usr/bin/env python3
"""Tests for transforms.py — Markdown → Confluence storage format conversion."""

import importlib.util
import sys
from pathlib import Path

_SCRIPTS_DIR = str(
    Path(__file__).resolve().parent.parent.parent / "confluence-publisher" / "scripts"
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_MODULE_PATH = Path(_SCRIPTS_DIR) / "transforms.py"
_spec = importlib.util.spec_from_file_location("transforms", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["transforms"] = _mod

markdown_to_confluence_storage = _mod.markdown_to_confluence_storage
_preprocess_markdown_blocks = _mod._preprocess_markdown_blocks


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

    def test_paragraph_then_list(self):
        md = "Paragraph.\n- item"
        assert _preprocess_markdown_blocks(md) == "Paragraph.\n\n- item"

    def test_bold_label_then_list(self):
        md = "**DoD:**\n- item"
        assert _preprocess_markdown_blocks(md) == "**DoD:**\n\n- item"

    def test_italic_label_then_list(self):
        md = "*Note:*\n- item"
        assert _preprocess_markdown_blocks(md) == "*Note:*\n\n- item"

    def test_blockquote_then_list(self):
        md = "> quote\n- item"
        assert _preprocess_markdown_blocks(md) == "> quote\n\n- item"

    def test_table_then_heading(self):
        md = "| 1 | 2 |\n### Heading"
        assert _preprocess_markdown_blocks(md) == "| 1 | 2 |\n\n### Heading"

    def test_table_then_list(self):
        md = "| 1 | 2 |\n- item"
        assert _preprocess_markdown_blocks(md) == "| 1 | 2 |\n\n- item"

    def test_paragraph_then_ordered_list(self):
        md = "Text.\n1. first"
        assert _preprocess_markdown_blocks(md) == "Text.\n\n1. first"

    def test_bold_label_then_ordered_list(self):
        md = "**Steps:**\n1. first"
        assert _preprocess_markdown_blocks(md) == "**Steps:**\n\n1. first"

    def test_already_separated_not_doubled(self):
        md = "**DoD:**\n\n- item"
        assert _preprocess_markdown_blocks(md) == md

    def test_code_block_then_list_untouched(self):
        md = "```\ncode\n```\n- item"
        assert _preprocess_markdown_blocks(md) == md


# ---------------------------------------------------------------------------
# markdown_to_confluence_storage — full pipeline
# ---------------------------------------------------------------------------


class TestMarkdownToConfluenceStorage:
    def test_bold_label_followed_by_unordered_list(self):
        md = "**DoD:**\n- first\n- second"
        result = markdown_to_confluence_storage(md)
        assert "<ul>" in result
        assert "<li>first</li>" in result

    def test_italic_label_followed_by_list(self):
        md = "*Note:*\n- item 1\n- item 2"
        result = markdown_to_confluence_storage(md)
        assert "<ul>" in result
        assert "<li>item 1</li>" in result

    def test_plain_paragraph_followed_by_list(self):
        md = "Description text.\n- item 1\n- item 2"
        result = markdown_to_confluence_storage(md)
        assert "<ul>" in result
        assert "<li>item 1</li>" in result
        assert "- item 1" not in result

    def test_bold_label_followed_by_ordered_list(self):
        md = "**Steps:**\n1. first\n2. second"
        result = markdown_to_confluence_storage(md)
        assert "<ol>" in result
        assert "first" in result
        assert "1. first" not in result

    def test_blockquote_then_list(self):
        md = "> quote\n- item 1\n- item 2"
        result = markdown_to_confluence_storage(md)
        assert "<ul>" in result
        assert "<li>item 1</li>" in result

    def test_table_then_heading(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |\n### After Table"
        result = markdown_to_confluence_storage(md)
        assert "<h3" in result
        assert "After Table" in result

    def test_table_then_list(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |\n- item"
        result = markdown_to_confluence_storage(md)
        assert "<ul>" in result
        assert "<li>item</li>" in result

    def test_heading(self):
        result = markdown_to_confluence_storage("### My Heading")
        assert "<h3" in result
        assert "My Heading" in result

    def test_code_block_with_language(self):
        md = "```python\nprint('hi')\n```"
        result = markdown_to_confluence_storage(md)
        assert 'ac:name="code"' in result
        assert 'ac:name="language">python' in result

    def test_code_block_without_language(self):
        md = "```\nsome code\n```"
        result = markdown_to_confluence_storage(md)
        assert 'ac:name="code"' in result
        assert "some code" in result

    def test_bold_and_italic(self):
        result = markdown_to_confluence_storage("**bold** and *italic*")
        assert "<strong>bold</strong>" in result
        assert "<em>italic</em>" in result

    def test_link(self):
        result = markdown_to_confluence_storage("[text](https://example.com)")
        assert 'href="https://example.com"' in result

    def test_table(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = markdown_to_confluence_storage(md)
        assert "<table>" in result
        assert "<th>A</th>" in result

    def test_unordered_list(self):
        md = "- one\n- two"
        result = markdown_to_confluence_storage(md)
        assert "<ul>" in result
        assert "<li>one</li>" in result

    def test_ordered_list(self):
        md = "1. first\n2. second"
        result = markdown_to_confluence_storage(md)
        assert "<ol>" in result
        assert "first" in result
        assert "1. first" not in result


if __name__ == "__main__":
    import subprocess

    sys.exit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
