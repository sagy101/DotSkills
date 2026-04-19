#!/usr/bin/env python3
"""Tests for confluence_preflight.py connectivity behavior."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

_SCRIPTS_DIR = str(
    Path(__file__).resolve().parent.parent.parent / "confluence-publisher" / "scripts"
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_MODULE_PATH = Path(_SCRIPTS_DIR) / "confluence_preflight.py"
_spec = importlib.util.spec_from_file_location("confluence_preflight", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


class TestCheckConnectivity:
    def test_runs_connectivity_inside_skill_venv(self, capsys: pytest.CaptureFixture[str]) -> None:
        fake_venv_python = Path(sys.executable)
        completed = SimpleNamespace(
            returncode=0,
            stdout='{"ok": true, "root_title": "Blueprint AI", "root_page_id": "798327325"}\n',
            stderr="",
        )
        with (
            mock.patch.object(_mod, "VENV_PYTHON", fake_venv_python),
            mock.patch.object(_mod.subprocess, "run", return_value=completed) as mock_run,
        ):
            assert _mod._check_connectivity({}, creds_ok=True) is True

        captured = capsys.readouterr()
        assert 'Connectivity — API OK, root page: "Blueprint AI" (id=798327325)' in captured.out
        mock_run.assert_called_once()
        args = mock_run.call_args.args[0]
        assert args[0] == str(fake_venv_python)
        assert args[1] == "-c"
        assert "from confluence_config import connect, load_config" in args[2]
        assert mock_run.call_args.kwargs["cwd"] == str(_mod.SCRIPT_DIR)

    def test_reports_json_error_from_venv_check(self, capsys: pytest.CaptureFixture[str]) -> None:
        completed = SimpleNamespace(
            returncode=1,
            stdout='{"ok": false, "error": "root page 633932397 not found"}\n',
            stderr="",
        )
        with (
            mock.patch.object(_mod, "VENV_PYTHON", Path(sys.executable)),
            mock.patch.object(_mod.subprocess, "run", return_value=completed),
        ):
            assert _mod._check_connectivity({}, creds_ok=True) is False

        captured = capsys.readouterr()
        assert "Connectivity — root page 633932397 not found" in captured.out

    def test_falls_back_to_stderr_when_json_missing(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        completed = SimpleNamespace(
            returncode=1,
            stdout="unexpected output\n",
            stderr="Traceback...\nModuleNotFoundError: No module named 'atlassian'\n",
        )
        with (
            mock.patch.object(_mod, "VENV_PYTHON", Path(sys.executable)),
            mock.patch.object(_mod.subprocess, "run", return_value=completed),
        ):
            assert _mod._check_connectivity({}, creds_ok=True) is False

        captured = capsys.readouterr()
        assert "Connectivity — ModuleNotFoundError: No module named 'atlassian'" in captured.out
