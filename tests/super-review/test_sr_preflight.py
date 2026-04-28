#!/usr/bin/env python3
"""Tests for sr_preflight.py — Python version and dependency checks."""

import importlib.util
import sys
from pathlib import Path
from unittest import mock

import pytest

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "super-review" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_MODULE_PATH = Path(_SCRIPTS_DIR) / "sr_preflight.py"
_spec = importlib.util.spec_from_file_location("sr_preflight", _MODULE_PATH)
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

    def test_passes_on_exact_310(self, capsys: pytest.CaptureFixture[str]) -> None:
        with mock.patch.object(sys, "version_info", (3, 10, 0, "final", 0)):
            assert _mod._check_python() is True
        assert "[PASS] Python 3.10" in capsys.readouterr().out


class TestCheckSubagentCapability:
    def test_non_cascade_always_passes(self, capsys: pytest.CaptureFixture[str]) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            assert _mod._check_subagent_capability() is True
        assert "agent has built-in sub-agents" in capsys.readouterr().out

    def test_cascade_without_codex_skill_fails(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            mock.patch.dict("os.environ", {"WINDSURF_CASCADE_TERMINAL": "1"}, clear=True),
            mock.patch.object(_mod, "CODEX_SUBAGENT_DIR", Path("/nonexistent/codex-subagent")),
        ):
            assert _mod._check_subagent_capability() is False
        assert "codex-subagent skill not found" in capsys.readouterr().out
