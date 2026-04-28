#!/usr/bin/env python3
"""Tests for sc_preflight.py — Python version, PyYAML, scripts, and references checks."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "skill-creator" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_MODULE_PATH = Path(_SCRIPTS_DIR) / "sc_preflight.py"
_spec = importlib.util.spec_from_file_location("sc_preflight", _MODULE_PATH)
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


class TestCheckPyYAML:
    def test_passes_when_importable(self, capsys: pytest.CaptureFixture[str]) -> None:
        completed = SimpleNamespace(returncode=0, stdout="6.0.2\n", stderr="")
        with mock.patch.object(_mod.subprocess, "run", return_value=completed):
            assert _mod._check_pyyaml() is True
        assert "[PASS] PyYAML" in capsys.readouterr().out

    def test_fails_when_not_installed(self, capsys: pytest.CaptureFixture[str]) -> None:
        completed = SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="ModuleNotFoundError: No module named 'yaml'\n",
        )
        with mock.patch.object(_mod.subprocess, "run", return_value=completed):
            assert _mod._check_pyyaml() is False
        out = capsys.readouterr().out
        assert "[FAIL] PyYAML" in out
        assert "pip install" in out


class TestCheckScripts:
    def test_passes_when_all_present(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert _mod._check_scripts() is True
        assert "[PASS] Skill scripts" in capsys.readouterr().out

    def test_fails_when_dir_missing(self, capsys: pytest.CaptureFixture[str]) -> None:
        with mock.patch.object(_mod, "SCRIPT_DIR", Path("/nonexistent")):
            assert _mod._check_scripts() is False
        assert "[FAIL] Skill scripts" in capsys.readouterr().out


class TestCheckReferences:
    def test_passes_when_all_present(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert _mod._check_references() is True
        assert "[PASS] References" in capsys.readouterr().out

    def test_fails_when_dir_missing(self, capsys: pytest.CaptureFixture[str]) -> None:
        with mock.patch.object(_mod, "SKILL_DIR", Path("/nonexistent")):
            assert _mod._check_references() is False
        assert "[FAIL] References" in capsys.readouterr().out
