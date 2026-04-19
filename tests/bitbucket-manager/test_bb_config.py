#!/usr/bin/env python3
"""Tests for Bitbucket config credential resolution edge cases."""

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "bitbucket-manager" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_MODULE_PATH = Path(_SCRIPTS_DIR) / "bb_config.py"
_spec = importlib.util.spec_from_file_location("bb_config", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["bb_config"] = _mod

BitbucketConfig = _mod.BitbucketConfig
resolve_credentials = _mod.resolve_credentials


class TestResolveCredentials:
    def test_missing_env_file_falls_back_to_shell_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = BitbucketConfig(
            workspace="firelayers",
            env_file=str(tmp_path / "missing.env"),
            project_root=tmp_path,
        )
        monkeypatch.setenv("BITBUCKET_EMAIL", "user@example.com")
        monkeypatch.setenv("BITBUCKET_TOKEN", "secret-token")

        email, token = resolve_credentials(config)

        assert email == "user@example.com"
        assert token == "secret-token"
        captured = capsys.readouterr()
        assert "WARN: env_file not found" in captured.err

    def test_missing_env_file_and_missing_env_vars_explains_both_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = BitbucketConfig(
            workspace="firelayers",
            env_file=str(tmp_path / "missing.env"),
            project_root=tmp_path,
        )
        monkeypatch.delenv("BITBUCKET_EMAIL", raising=False)
        monkeypatch.delenv("BITBUCKET_TOKEN", raising=False)

        with pytest.raises(SystemExit) as exc_info:
            resolve_credentials(config)

        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        assert "WARN: env_file not found" in captured.err
        assert "fix the configured env_file path" in captured.out
