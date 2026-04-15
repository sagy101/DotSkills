#!/usr/bin/env python3
"""Tests for page_utils.py — page ID extraction, tiny link codec, title resolution."""

import importlib.util
import sys
from pathlib import Path
from unittest import mock

_MODULE_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "confluence-publisher"
    / "scripts"
    / "page_utils.py"
)
_spec = importlib.util.spec_from_file_location("confluence_page_utils", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["confluence_page_utils"] = _mod

decode_tiny_link = _mod.decode_tiny_link
encode_tiny_id = _mod.encode_tiny_id
extract_page_id = _mod.extract_page_id
resolve_title = _mod.resolve_title
strip_title_heading = _mod.strip_title_heading


# ---------------------------------------------------------------------------
# decode_tiny_link / encode_tiny_id roundtrip
# ---------------------------------------------------------------------------


class TestTinyLinkCodec:
    def test_roundtrip_known_id(self):
        page_id = 774112245
        encoded = encode_tiny_id(page_id)
        assert decode_tiny_link(encoded) == page_id

    def test_roundtrip_small_id(self):
        page_id = 42
        encoded = encode_tiny_id(page_id)
        assert decode_tiny_link(encoded) == page_id

    def test_roundtrip_large_id(self):
        page_id = 2**31 - 1
        encoded = encode_tiny_id(page_id)
        assert decode_tiny_link(encoded) == page_id


# ---------------------------------------------------------------------------
# extract_page_id
# ---------------------------------------------------------------------------


class TestExtractPageId:
    def test_plain_numeric(self):
        assert extract_page_id("774112245") == "774112245"

    def test_standard_url(self):
        url = "https://example.atlassian.net/wiki/spaces/SP/pages/774112245/My+Page"
        assert extract_page_id(url) == "774112245"

    def test_tiny_link(self):
        page_id = 774112245
        tiny = encode_tiny_id(page_id)
        url = f"https://example.atlassian.net/wiki/x/{tiny}"
        assert extract_page_id(url) == str(page_id)

    def test_invalid_raises(self):
        import pytest

        with pytest.raises(ValueError, match="Could not extract"):
            extract_page_id("not-a-page-ref")


# ---------------------------------------------------------------------------
# resolve_title
# ---------------------------------------------------------------------------


class TestResolveTitle:
    def _make_config(self, title_map: dict[str, str] | None = None) -> mock.MagicMock:
        """Create a mock ConfluenceConfig with title_map."""
        cfg = mock.MagicMock()
        cfg.title_map = title_map or {}
        return cfg

    def test_title_map_wins(self):
        config = self._make_config(title_map={"docs/foo.md": "Custom Title"})
        assert resolve_title("docs/foo.md", "# Ignored Heading\nBody", config) == "Custom Title"

    def test_first_heading(self):
        config = self._make_config()
        md = "# My Page Title\n\nSome body text"
        assert resolve_title("docs/foo.md", md, config) == "My Page Title"

    def test_filename_fallback(self):
        config = self._make_config()
        assert resolve_title("docs/my-feature.md", "No heading here", config) == "My Feature"

    def test_readme_uses_parent_dir(self):
        config = self._make_config()
        assert resolve_title("docs/my-section/README.md", "No heading", config) == "My Section"


# ---------------------------------------------------------------------------
# strip_title_heading
# ---------------------------------------------------------------------------


class TestStripTitleHeading:
    def test_strips_matching_h1(self):
        md = "# My Title\n\nBody text here"
        result = strip_title_heading(md, "My Title")
        assert result == "\nBody text here" or result == "Body text here"
        assert "Body text here" in result
        assert not result.startswith("# My Title")

    def test_preserves_non_matching_h1(self):
        md = "# Different Title\n\nBody text here"
        result = strip_title_heading(md, "My Title")
        assert result == md

    def test_preserves_no_h1(self):
        md = "## Subtitle\n\nBody text here"
        result = strip_title_heading(md, "Subtitle")
        assert result == md

    def test_strips_with_extra_whitespace(self):
        md = "#   My Title  \n\nBody"
        result = strip_title_heading(md, "My Title")
        assert "Body" in result
        assert not result.startswith("#")

    def test_preserves_h1_not_at_start(self):
        md = "Some preamble\n# My Title\n\nBody"
        result = strip_title_heading(md, "My Title")
        assert result == md


# ---------------------------------------------------------------------------
# Run with pytest or directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import subprocess

    sys.exit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
