#!/usr/bin/env python3
"""Tests for rp_preflight.py — Python version and prompt file checks."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "review-prompts" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_MODULE_PATH = Path(_SCRIPTS_DIR) / "rp_preflight.py"
_spec = importlib.util.spec_from_file_location("rp_preflight", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


class TestCheckPython:
    def test_passes_on_310_plus(self, capsys: pytest.CaptureFixture[str]) -> None:
        with mock.patch.object(sys, "version_info", (3, 12, 0, "final", 0)):
            assert _mod._check_python() is True
        assert "[PASS] Python 3.12" in capsys.readouterr().out

    def test_fails_on_39(self, capsys: pytest.CaptureFixture[str]) -> None:
        with mock.patch.object(sys, "version_info", (3, 9, 19, "final", 0)):
            assert _mod._check_python() is False
        assert "[FAIL] Python 3.9" in capsys.readouterr().out


class TestCheckBuildScript:
    def test_passes_when_script_exists(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert _mod._check_build_script() is True
        assert "[PASS] build-prompt.py" in capsys.readouterr().out

    def test_fails_when_script_missing(self, capsys: pytest.CaptureFixture[str]) -> None:
        with mock.patch.object(_mod, "SCRIPT_DIR", Path("/nonexistent")):
            assert _mod._check_build_script() is False
        assert "[FAIL] build-prompt.py" in capsys.readouterr().out


class TestCheckPromptFiles:
    def test_passes_when_prompts_exist(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert _mod._check_prompt_files() is True
        assert "[PASS] Prompt files" in capsys.readouterr().out

    def test_fails_when_dir_missing(self, capsys: pytest.CaptureFixture[str]) -> None:
        with mock.patch.object(_mod, "PROMPTS_DIR", Path("/nonexistent")):
            assert _mod._check_prompt_files() is False
        assert "[FAIL] Prompt files" in capsys.readouterr().out


class TestCheckBuildRuns:
    def test_passes_when_list_succeeds(self, capsys: pytest.CaptureFixture[str]) -> None:
        completed = SimpleNamespace(
            returncode=0,
            stdout="code-review\nsecurity\narchitecture\n",
            stderr="",
        )
        with mock.patch.object(_mod.subprocess, "run", return_value=completed):
            assert _mod._check_build_runs() is True
        assert "3 type(s)" in capsys.readouterr().out

    def test_fails_when_list_errors(self, capsys: pytest.CaptureFixture[str]) -> None:
        completed = SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="FileNotFoundError: prompts/_shared.md\n",
        )
        with mock.patch.object(_mod.subprocess, "run", return_value=completed):
            assert _mod._check_build_runs() is False
        assert "[FAIL] build-prompt.py test" in capsys.readouterr().out
