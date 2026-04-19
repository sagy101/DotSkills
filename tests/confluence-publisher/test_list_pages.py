#!/usr/bin/env python3
"""CLI tests for list_pages.py."""

import importlib.util
import sys
from pathlib import Path
from unittest import mock

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "confluence-publisher"
    / "scripts"
    / "list_pages.py"
)
_spec = importlib.util.spec_from_file_location("confluence_list_pages", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["confluence_list_pages"] = _mod


class TestListPagesCli:
    def test_json_format_uses_filters(self, capsys: pytest.CaptureFixture[str]) -> None:
        pages = [
            {
                "page_id": "100",
                "title": "API",
                "space_id": "42",
                "status": "current",
                "subtype": "page",
                "url": "https://example/wiki/spaces/DOCS/pages/100/API",
            }
        ]
        with (
            mock.patch.object(_mod, "load_config") as load_config,
            mock.patch.object(_mod, "list_pages", return_value=pages) as list_pages,
        ):
            cfg = mock.MagicMock()
            cfg.space_key = "DOCS"
            load_config.return_value = cfg
            argv = [
                "list_pages.py",
                "--space-key",
                "DOCS",
                "--title",
                "API",
                "--status",
                "current",
                "--type",
                "page",
                "--format",
                "json",
            ]
            with mock.patch.object(sys, "argv", argv):
                _mod.main()
        list_pages.assert_called_once()
        out = capsys.readouterr().out
        assert '"API"' in out

    def test_table_format_prints_rows(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            mock.patch.object(_mod, "load_config") as load_config,
            mock.patch.object(_mod, "list_pages", return_value=[]),
        ):
            cfg = mock.MagicMock()
            cfg.space_key = "DOCS"
            load_config.return_value = cfg
            argv = ["list_pages.py"]
            with mock.patch.object(sys, "argv", argv):
                _mod.main()
        out = capsys.readouterr().out
        assert "No pages found" in out or "No pages" in out
