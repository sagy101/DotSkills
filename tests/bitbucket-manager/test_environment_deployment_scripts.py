#!/usr/bin/env python3
"""Tests for environment and deployment CLI scripts."""

import importlib.util
import io
import sys
from pathlib import Path
from types import ModuleType
from unittest import mock

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "bitbucket-manager" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


def _load(name: str) -> ModuleType:
    path = Path(_SCRIPTS_DIR) / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules[name] = mod
    return mod


_env_list_mod = _load("environment_list")
_env_get_mod = _load("environment_get")
_dep_list_mod = _load("deployment_list")
_dep_get_mod = _load("deployment_get")


class TestEnvironmentList:
    def test_table_output(self) -> None:
        stdout = io.StringIO()
        payload = [{"uuid": "{e1}", "name": "prod"}]
        with (
            mock.patch.object(_env_list_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(_env_list_mod, "resolve_workspace", return_value="acme"),
            mock.patch.object(_env_list_mod, "resolve_repo", return_value="repo"),
            mock.patch.object(_env_list_mod, "BitbucketClient") as mock_client_cls,
            mock.patch.object(sys, "argv", ["environment_list.py"]),
            mock.patch("sys.stdout", stdout),
        ):
            mock_client_cls.return_value.list_environments.return_value = payload
            _env_list_mod.main()

        assert "{e1}" in stdout.getvalue()

    def test_max_results_passed(self) -> None:
        with (
            mock.patch.object(_env_list_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(_env_list_mod, "resolve_workspace", return_value="acme"),
            mock.patch.object(_env_list_mod, "resolve_repo", return_value="repo"),
            mock.patch.object(_env_list_mod, "BitbucketClient") as mock_client_cls,
            mock.patch.object(sys, "argv", ["environment_list.py", "--max-results", "7"]),
        ):
            mock_client_cls.return_value.list_environments.return_value = []
            _env_list_mod.main()

        mock_client_cls.return_value.list_environments.assert_called_once_with(
            "acme", "repo", max_results=7
        )


class TestEnvironmentGet:
    def test_json_output(self) -> None:
        stdout = io.StringIO()
        payload = {"uuid": "{e1}", "name": "prod"}
        with (
            mock.patch.object(_env_get_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(_env_get_mod, "resolve_workspace", return_value="acme"),
            mock.patch.object(_env_get_mod, "resolve_repo", return_value="repo"),
            mock.patch.object(_env_get_mod, "BitbucketClient") as mock_client_cls,
            mock.patch.object(
                sys, "argv", ["environment_get.py", "--environment", "{e1}", "--format", "json"]
            ),
            mock.patch("sys.stdout", stdout),
        ):
            mock_client_cls.return_value.get_environment.return_value = payload
            _env_get_mod.main()

        assert '"uuid": "{e1}"' in stdout.getvalue()


class TestDeploymentList:
    def test_table_output(self) -> None:
        stdout = io.StringIO()
        payload = [{"uuid": "{d1}", "state": {"name": "SUCCESS"}}]
        with (
            mock.patch.object(_dep_list_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(_dep_list_mod, "resolve_workspace", return_value="acme"),
            mock.patch.object(_dep_list_mod, "resolve_repo", return_value="repo"),
            mock.patch.object(_dep_list_mod, "BitbucketClient") as mock_client_cls,
            mock.patch.object(sys, "argv", ["deployment_list.py"]),
            mock.patch("sys.stdout", stdout),
        ):
            mock_client_cls.return_value.list_deployments.return_value = payload
            _dep_list_mod.main()

        assert "{d1}" in stdout.getvalue()

    def test_max_results_passed(self) -> None:
        with (
            mock.patch.object(_dep_list_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(_dep_list_mod, "resolve_workspace", return_value="acme"),
            mock.patch.object(_dep_list_mod, "resolve_repo", return_value="repo"),
            mock.patch.object(_dep_list_mod, "BitbucketClient") as mock_client_cls,
            mock.patch.object(sys, "argv", ["deployment_list.py", "--max-results", "13"]),
        ):
            mock_client_cls.return_value.list_deployments.return_value = []
            _dep_list_mod.main()

        mock_client_cls.return_value.list_deployments.assert_called_once_with(
            "acme", "repo", max_results=13
        )


class TestDeploymentGet:
    def test_json_output(self) -> None:
        stdout = io.StringIO()
        payload = {"uuid": "{d1}", "state": {"name": "SUCCESS"}}
        with (
            mock.patch.object(_dep_get_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(_dep_get_mod, "resolve_workspace", return_value="acme"),
            mock.patch.object(_dep_get_mod, "resolve_repo", return_value="repo"),
            mock.patch.object(_dep_get_mod, "BitbucketClient") as mock_client_cls,
            mock.patch.object(
                sys, "argv", ["deployment_get.py", "--deployment", "{d1}", "--format", "json"]
            ),
            mock.patch("sys.stdout", stdout),
        ):
            mock_client_cls.return_value.get_deployment.return_value = payload
            _dep_get_mod.main()

        assert '"uuid": "{d1}"' in stdout.getvalue()
