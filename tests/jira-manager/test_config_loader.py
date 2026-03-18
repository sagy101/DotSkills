#!/usr/bin/env python3
"""Tests for config_loader.py — shell detection, deep merge, config discovery."""

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

_MODULE_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "jira-manager"
    / "scripts"
    / "jira_config_loader.py"
)
_spec = importlib.util.spec_from_file_location("jira_config_loader", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["jira_config_loader"] = _mod

_credential_hint = _mod._credential_hint
_deep_merge = _mod._deep_merge
_find_global_config = _mod._find_global_config
_find_project_config = _mod._find_project_config
add_config_arg = _mod.add_config_arg
detect_shell = _mod.detect_shell
load_config = _mod.load_config


# ---------------------------------------------------------------------------
# detect_shell
# ---------------------------------------------------------------------------


class TestDetectShell:
    def test_zsh_on_macos(self):
        with (
            mock.patch.dict(os.environ, {"SHELL": "/bin/zsh"}, clear=False),
            mock.patch("jira_config_loader.sys") as mock_sys,
        ):
            mock_sys.platform = "darwin"
            name, rc = detect_shell()
            assert name == "zsh"
            assert rc == "~/.zshrc"

    def test_bash_on_linux(self):
        with (
            mock.patch.dict(os.environ, {"SHELL": "/bin/bash"}, clear=False),
            mock.patch("jira_config_loader.sys") as mock_sys,
        ):
            mock_sys.platform = "linux"
            name, rc = detect_shell()
            assert name == "bash"
            assert rc == "~/.bashrc"

    def test_bash_on_macos(self):
        with (
            mock.patch.dict(os.environ, {"SHELL": "/bin/bash"}, clear=False),
            mock.patch("jira_config_loader.sys") as mock_sys,
        ):
            mock_sys.platform = "darwin"
            name, rc = detect_shell()
            assert name == "bash"
            assert rc == "~/.bash_profile"

    def test_fish(self):
        with (
            mock.patch.dict(os.environ, {"SHELL": "/usr/bin/fish"}, clear=False),
            mock.patch("jira_config_loader.sys") as mock_sys,
        ):
            mock_sys.platform = "linux"
            name, rc = detect_shell()
            assert name == "fish"
            assert rc == "~/.config/fish/config.fish"

    def test_unknown_shell_falls_back_to_profile(self):
        with (
            mock.patch.dict(os.environ, {"SHELL": "/usr/bin/ksh"}, clear=False),
            mock.patch("jira_config_loader.sys") as mock_sys,
        ):
            mock_sys.platform = "linux"
            name, rc = detect_shell()
            assert name == "ksh"
            assert rc == "~/.profile"

    def test_no_shell_env_falls_back_to_sh(self):
        env = os.environ.copy()
        env.pop("SHELL", None)
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch("jira_config_loader.sys") as mock_sys,
        ):
            mock_sys.platform = "linux"
            name, rc = detect_shell()
            assert name == "sh"
            assert rc == "~/.profile"

    def test_windows_cmd(self):
        env = os.environ.copy()
        env.pop("PSModulePath", None)
        env["COMSPEC"] = r"C:\Windows\system32\cmd.exe"
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch("jira_config_loader.sys") as mock_sys,
        ):
            mock_sys.platform = "win32"
            name, _rc = detect_shell()
            assert name == "cmd"

    def test_windows_powershell_via_comspec(self):
        with (
            mock.patch.dict(
                os.environ, {"COMSPEC": r"C:\Program Files\PowerShell\7\pwsh.exe"}, clear=False
            ),
            mock.patch("jira_config_loader.sys") as mock_sys,
        ):
            mock_sys.platform = "win32"
            name, rc = detect_shell()
            assert name == "pwsh"
            assert rc == "$PROFILE"

    def test_windows_powershell_via_psmodulepath(self):
        env = os.environ.copy()
        env["COMSPEC"] = r"C:\Windows\system32\cmd.exe"
        env["PSModulePath"] = r"C:\Users\test\Documents\PowerShell\Modules"
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch("jira_config_loader.sys") as mock_sys,
        ):
            mock_sys.platform = "win32"
            name, rc = detect_shell()
            assert name == "pwsh"
            assert rc == "$PROFILE"


# ---------------------------------------------------------------------------
# _credential_hint
# ---------------------------------------------------------------------------


class TestCredentialHint:
    def test_zsh_hint(self):
        with mock.patch("jira_config_loader.detect_shell", return_value=("zsh", "~/.zshrc")):
            hint = _credential_hint("JIRA_TOKEN")
            assert "export JIRA_TOKEN" in hint
            assert "~/.zshrc" in hint

    def test_fish_hint(self):
        with mock.patch(
            "jira_config_loader.detect_shell", return_value=("fish", "~/.config/fish/config.fish")
        ):
            hint = _credential_hint("JIRA_TOKEN")
            assert "set -Ux JIRA_TOKEN" in hint

    def test_pwsh_hint(self):
        with mock.patch("jira_config_loader.detect_shell", return_value=("pwsh", "$PROFILE")):
            hint = _credential_hint("JIRA_TOKEN")
            assert "SetEnvironmentVariable" in hint
            assert "JIRA_TOKEN" in hint

    def test_cmd_hint(self):
        with mock.patch(
            "jira_config_loader.detect_shell", return_value=("cmd", "%USERPROFILE%\\.env")
        ):
            hint = _credential_hint("JIRA_TOKEN")
            assert "setx JIRA_TOKEN" in hint


# ---------------------------------------------------------------------------
# _deep_merge
# ---------------------------------------------------------------------------


class TestDeepMerge:
    def test_flat_merge(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        base = {"credentials": {"username_env": "EMAIL", "token_env": "TOKEN"}}
        override = {"credentials": {"token_env": "MY_TOKEN"}}
        result = _deep_merge(base, override)
        assert result["credentials"]["username_env"] == "EMAIL"
        assert result["credentials"]["token_env"] == "MY_TOKEN"

    def test_override_replaces_non_dict(self):
        base = {"key": "old"}
        override = {"key": {"nested": True}}
        result = _deep_merge(base, override)
        assert result["key"] == {"nested": True}

    def test_empty_base(self):
        result = _deep_merge({}, {"a": 1})
        assert result == {"a": 1}

    def test_empty_override(self):
        result = _deep_merge({"a": 1}, {})
        assert result == {"a": 1}

    def test_does_not_mutate_inputs(self):
        base = {"a": {"x": 1}}
        override = {"a": {"y": 2}}
        _deep_merge(base, override)
        assert base == {"a": {"x": 1}}
        assert override == {"a": {"y": 2}}


# ---------------------------------------------------------------------------
# Config discovery (_find_project_config, _find_global_config)
# ---------------------------------------------------------------------------


class TestConfigDiscovery:
    def test_find_project_config_in_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / ".jira.json"
            config_file.write_text('{"jira_url": "https://test.atlassian.net"}')
            result = _find_project_config(start_dir=tmp)
            assert result is not None
            assert result == config_file

    def test_find_project_config_walks_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / ".jira.json"
            config_file.write_text("{}")
            subdir = Path(tmp) / "sub" / "deep"
            subdir.mkdir(parents=True)
            result = _find_project_config(start_dir=str(subdir))
            assert result is not None
            assert result == config_file

    def test_find_project_config_returns_none_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _find_project_config(start_dir=tmp)
            assert result is None

    def test_find_global_config_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = Path(tmp)
            config_file = fake_home / ".jira.json"
            config_file.write_text("{}")
            with mock.patch("jira_config_loader.Path.home", return_value=fake_home):
                result = _find_global_config()
                assert result is not None
                assert result == config_file

    def test_find_global_config_missing(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch("jira_config_loader.Path.home", return_value=Path(tmp)),
        ):
            result = _find_global_config()
            assert result is None


# ---------------------------------------------------------------------------
# load_config (with merge)
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_explicit_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / ".jira.json"
            config_file.write_text(
                json.dumps(
                    {
                        "jira_url": "https://test.atlassian.net",
                        "project_key": "TEST",
                    }
                )
            )
            config = load_config(str(config_file))
            assert config.jira_url == "https://test.atlassian.net"
            assert config.project_key == "TEST"

    def test_merge_global_and_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = Path(tmp) / "home"
            fake_home.mkdir()
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()

            global_cfg = fake_home / ".jira.json"
            global_cfg.write_text(
                json.dumps(
                    {
                        "jira_url": "https://global.atlassian.net",
                        "credentials": {
                            "username_env": "GLOBAL_EMAIL",
                            "token_env": "GLOBAL_TOKEN",
                        },
                    }
                )
            )

            project_cfg = project_dir / ".jira.json"
            project_cfg.write_text(
                json.dumps(
                    {
                        "project_key": "PROJ",
                        "credentials": {"token_env": "PROJECT_TOKEN"},
                    }
                )
            )

            with (
                mock.patch("jira_config_loader.Path.home", return_value=fake_home),
                mock.patch("jira_config_loader._find_project_config", return_value=project_cfg),
            ):
                config = load_config()
                assert config.jira_url == "https://global.atlassian.net"
                assert config.project_key == "PROJ"
                assert config.username_env == "GLOBAL_EMAIL"
                assert config.token_env == "PROJECT_TOKEN"

    def test_global_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = Path(tmp)
            global_cfg = fake_home / ".jira.json"
            global_cfg.write_text(
                json.dumps(
                    {
                        "jira_url": "https://global.atlassian.net",
                        "project_key": "GLOB",
                    }
                )
            )

            with (
                mock.patch("jira_config_loader.Path.home", return_value=fake_home),
                mock.patch("jira_config_loader._find_project_config", return_value=None),
            ):
                config = load_config()
                assert config.jira_url == "https://global.atlassian.net"
                assert config.project_key == "GLOB"

    def test_missing_config_exits(self):
        import pytest

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch("jira_config_loader.Path.home", return_value=Path(tmp)),
            mock.patch("jira_config_loader._find_project_config", return_value=None),
            pytest.raises(SystemExit, match="1"),
        ):
            load_config()


# ---------------------------------------------------------------------------
# add_config_arg
# ---------------------------------------------------------------------------


class TestAddConfigArg:
    def test_adds_optional_config_arg(self):
        import argparse

        parser = argparse.ArgumentParser()
        add_config_arg(parser)
        args = parser.parse_args([])
        assert args.config is None

    def test_accepts_config_value(self):
        import argparse

        parser = argparse.ArgumentParser()
        add_config_arg(parser)
        args = parser.parse_args(["--config", "/path/to/.jira.json"])
        assert args.config == "/path/to/.jira.json"


# ---------------------------------------------------------------------------
# _find_git_root / git root boundary
# ---------------------------------------------------------------------------

_find_git_root = _mod._find_git_root
CONFIG_FILENAME = _mod.CONFIG_FILENAME


class TestGitRootBoundary:
    def test_find_git_root_returns_dir_with_dotgit(self):
        with tempfile.TemporaryDirectory() as tmp:
            git_dir = Path(tmp) / "repo"
            git_dir.mkdir()
            (git_dir / ".git").mkdir()
            subdir = git_dir / "a" / "b"
            subdir.mkdir(parents=True)
            assert _find_git_root(subdir) == git_dir

    def test_find_git_root_returns_none_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            assert _find_git_root(Path(tmp)) is None

    def test_config_discovery_stops_at_git_root(self):
        """Config above the git root should NOT be found."""
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            # Config in parent (above git root)
            (parent / CONFIG_FILENAME).write_text('{"jira_url": "https://x"}')
            # Git root one level deeper
            repo = parent / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            subdir = repo / "src"
            subdir.mkdir()
            result = _find_project_config(start_dir=str(subdir))
            assert result is None

    def test_config_at_git_root_is_found(self):
        """Config at the git root itself should be found."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            cfg = repo / CONFIG_FILENAME
            cfg.write_text("{}")
            subdir = repo / "src"
            subdir.mkdir()
            result = _find_project_config(start_dir=str(subdir))
            assert result == cfg


# ---------------------------------------------------------------------------
# Type validation (M5)
# ---------------------------------------------------------------------------


class TestTypeValidation:
    def test_non_string_jira_url_exits(self):
        import pytest

        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / ".jira.json"
            cfg.write_text(
                json.dumps(
                    {
                        "jira_url": 12345,
                        "project_key": "TEST",
                    }
                )
            )
            with pytest.raises(SystemExit):
                load_config(str(cfg))

    def test_empty_project_key_exits(self):
        import pytest

        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / ".jira.json"
            cfg.write_text(
                json.dumps(
                    {
                        "jira_url": "https://test.atlassian.net",
                        "project_key": "   ",
                    }
                )
            )
            with pytest.raises(SystemExit):
                load_config(str(cfg))

    def test_credentials_not_dict_exits(self):
        import pytest

        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / ".jira.json"
            cfg.write_text(
                json.dumps(
                    {
                        "jira_url": "https://test.atlassian.net",
                        "project_key": "TEST",
                        "credentials": "bad",
                    }
                )
            )
            with pytest.raises(SystemExit):
                load_config(str(cfg))


# ---------------------------------------------------------------------------
# Path traversal (H3)
# ---------------------------------------------------------------------------

resolve_credentials = _mod.resolve_credentials
JiraConfig = _mod.JiraConfig


class TestPathTraversal:
    def test_env_file_escape_exits(self):
        import pytest

        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "project"
            project_root.mkdir()
            config = JiraConfig(
                jira_url="https://test.atlassian.net",
                project_key="TEST",
                env_file="../../etc/passwd",
                project_root=project_root,
            )
            with pytest.raises(SystemExit):
                resolve_credentials(config)

    def test_env_file_inside_root_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            env_file = project_root / ".env"
            env_file.write_text("JIRA_EMAIL=x@y.com\nJIRA_TOKEN=secret\n")
            config = JiraConfig(
                jira_url="https://test.atlassian.net",
                project_key="TEST",
                env_file=".env",
                project_root=project_root,
            )
            username, token = resolve_credentials(config)
            assert username == "x@y.com"
            assert token == "secret"


# ---------------------------------------------------------------------------
# Run with pytest or directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import subprocess

    sys.exit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
