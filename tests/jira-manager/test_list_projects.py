#!/usr/bin/env python3
"""Tests for list_projects.py."""

import importlib.util
import io
import sys
from pathlib import Path
from unittest import mock

import pytest

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "jira-manager" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_MODULE_PATH = Path(_SCRIPTS_DIR) / "list_projects.py"
_spec = importlib.util.spec_from_file_location("list_projects", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["list_projects"] = _mod

format_projects_table = _mod.format_projects_table


class TestFormatProjectsTable:
    def test_empty(self) -> None:
        assert format_projects_table([]) == "No visible projects found."

    def test_renders_rows(self) -> None:
        projects = [
            {
                "key": "API",
                "name": "API Team",
                "projectTypeKey": "software",
                "style": "classic",
            }
        ]

        table = format_projects_table(projects)

        assert "API Team" in table
        assert "software" in table
        assert "classic" in table


class TestListProjectsMain:
    def test_table_output(self) -> None:
        payload = [
            {"key": "API", "name": "API Team", "projectTypeKey": "software", "style": "classic"}
        ]
        stdout = io.StringIO()
        with (
            mock.patch.object(_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(_mod, "JiraClient") as mock_client_cls,
            mock.patch.object(sys, "argv", ["list_projects.py"]),
            mock.patch("sys.stdout", stdout),
        ):
            mock_client_cls.return_value.get_visible_projects.return_value = payload
            _mod.main()

        text = stdout.getvalue()
        assert "API Team" in text
        assert "software" in text
        assert "classic" in text

    def test_json_format_rejected(self) -> None:
        with (
            mock.patch.object(_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(sys, "argv", ["list_projects.py", "--format", "json"]),
            pytest.raises(SystemExit),
        ):
            _mod.main()
