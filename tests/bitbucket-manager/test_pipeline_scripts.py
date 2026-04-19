#!/usr/bin/env python3
"""Tests for Bitbucket pipeline CLI scripts."""

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


_list_mod = _load("pipeline_list")
_get_mod = _load("pipeline_get")
_run_mod = _load("pipeline_run")
_steps_mod = _load("pipeline_steps")
_step_get_mod = _load("pipeline_step_get")
_log_mod = _load("pipeline_log")


class TestPipelineList:
    def test_table_output(self) -> None:
        stdout = io.StringIO()
        payload = [{"uuid": "{p1}", "state": {"name": "COMPLETED"}, "created_on": "2026-01-01"}]
        with (
            mock.patch.object(_list_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(_list_mod, "resolve_workspace", return_value="acme"),
            mock.patch.object(_list_mod, "resolve_repo", return_value="repo"),
            mock.patch.object(_list_mod, "BitbucketClient") as mock_client_cls,
            mock.patch.object(sys, "argv", ["pipeline_list.py"]),
            mock.patch("sys.stdout", stdout),
        ):
            mock_client_cls.return_value.list_pipelines.return_value = payload
            _list_mod.main()

        assert "{p1}" in stdout.getvalue()

    def test_max_results_passed(self) -> None:
        with (
            mock.patch.object(_list_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(_list_mod, "resolve_workspace", return_value="acme"),
            mock.patch.object(_list_mod, "resolve_repo", return_value="repo"),
            mock.patch.object(_list_mod, "BitbucketClient") as mock_client_cls,
            mock.patch.object(sys, "argv", ["pipeline_list.py", "--max-results", "12"]),
        ):
            mock_client_cls.return_value.list_pipelines.return_value = []
            _list_mod.main()

        mock_client_cls.return_value.list_pipelines.assert_called_once_with(
            "acme", "repo", max_results=12
        )


class TestPipelineGet:
    def test_json_output(self) -> None:
        stdout = io.StringIO()
        payload = {"uuid": "{p1}", "state": {"name": "COMPLETED"}}
        with (
            mock.patch.object(_get_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(_get_mod, "resolve_workspace", return_value="acme"),
            mock.patch.object(_get_mod, "resolve_repo", return_value="repo"),
            mock.patch.object(_get_mod, "BitbucketClient") as mock_client_cls,
            mock.patch.object(
                sys, "argv", ["pipeline_get.py", "--pipeline", "{p1}", "--format", "json"]
            ),
            mock.patch("sys.stdout", stdout),
        ):
            mock_client_cls.return_value.get_pipeline.return_value = payload
            _get_mod.main()

        assert '"uuid": "{p1}"' in stdout.getvalue()


class TestPipelineRun:
    def test_runs_with_branch_target(self) -> None:
        stdout = io.StringIO()
        client = mock.MagicMock()
        with (
            mock.patch.object(_run_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(_run_mod, "resolve_workspace", return_value="acme"),
            mock.patch.object(_run_mod, "resolve_repo", return_value="repo"),
            mock.patch.object(_run_mod, "BitbucketClient", return_value=client),
            mock.patch.object(
                sys,
                "argv",
                ["pipeline_run.py", "--branch", "main", "--selector", "Deploy"],
            ),
            mock.patch("sys.stdout", stdout),
        ):
            client.run_pipeline.return_value = {"uuid": "{p2}"}
            _run_mod.main()

        assert "triggered" in stdout.getvalue()
        client.run_pipeline.assert_called_once_with(
            "acme",
            "repo",
            target={
                "type": "pipeline_ref_target",
                "ref_type": "branch",
                "ref_name": "main",
                "selector": {"type": "custom", "pattern": "Deploy"},
            },
            variables=None,
        )

    def test_dry_run_skips_client_call(self) -> None:
        stdout = io.StringIO()
        client = mock.MagicMock()
        with (
            mock.patch.object(_run_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(_run_mod, "resolve_workspace", return_value="acme"),
            mock.patch.object(_run_mod, "resolve_repo", return_value="repo"),
            mock.patch.object(_run_mod, "BitbucketClient", return_value=client),
            mock.patch.object(
                sys,
                "argv",
                [
                    "pipeline_run.py",
                    "--branch",
                    "main",
                    "--selector",
                    "Deploy",
                    "--dry-run",
                ],
            ),
            mock.patch("sys.stdout", stdout),
        ):
            _run_mod.main()

        assert "DRY RUN" in stdout.getvalue()
        assert not client.run_pipeline.called


class TestPipelineSteps:
    def test_table_output(self) -> None:
        stdout = io.StringIO()
        payload = [{"uuid": "{s1}", "state": {"name": "COMPLETED"}}]
        client = mock.MagicMock()
        with (
            mock.patch.object(_steps_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(_steps_mod, "resolve_workspace", return_value="acme"),
            mock.patch.object(_steps_mod, "resolve_repo", return_value="repo"),
            mock.patch.object(_steps_mod, "BitbucketClient", return_value=client),
            mock.patch.object(
                sys,
                "argv",
                ["pipeline_steps.py", "--pipeline", "{p1}", "--max-results", "75"],
            ),
            mock.patch("sys.stdout", stdout),
        ):
            client.list_pipeline_steps.return_value = payload
            _steps_mod.main()

        assert "{s1}" in stdout.getvalue()
        client.list_pipeline_steps.assert_called_once_with(
            "acme",
            "repo",
            "{p1}",
            max_results=75,
        )

    def test_max_results_passed(self) -> None:
        with (
            mock.patch.object(_steps_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(_steps_mod, "resolve_workspace", return_value="acme"),
            mock.patch.object(_steps_mod, "resolve_repo", return_value="repo"),
            mock.patch.object(_steps_mod, "BitbucketClient") as mock_client_cls,
            mock.patch.object(
                sys, "argv", ["pipeline_steps.py", "--pipeline", "{p1}", "--max-results", "9"]
            ),
        ):
            mock_client_cls.return_value.list_pipeline_steps.return_value = []
            _steps_mod.main()

        mock_client_cls.return_value.list_pipeline_steps.assert_called_once_with(
            "acme", "repo", "{p1}", max_results=9
        )


class TestPipelineStepGet:
    def test_json_output(self) -> None:
        stdout = io.StringIO()
        payload = {"uuid": "{s1}", "state": {"name": "COMPLETED"}}
        with (
            mock.patch.object(_step_get_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(_step_get_mod, "resolve_workspace", return_value="acme"),
            mock.patch.object(_step_get_mod, "resolve_repo", return_value="repo"),
            mock.patch.object(_step_get_mod, "BitbucketClient") as mock_client_cls,
            mock.patch.object(
                sys,
                "argv",
                [
                    "pipeline_step_get.py",
                    "--pipeline",
                    "{p1}",
                    "--step",
                    "{s1}",
                    "--format",
                    "json",
                ],
            ),
            mock.patch("sys.stdout", stdout),
        ):
            mock_client_cls.return_value.get_pipeline_step.return_value = payload
            _step_get_mod.main()

        assert '"uuid": "{s1}"' in stdout.getvalue()


class TestPipelineLog:
    def test_plain_log(self) -> None:
        stdout = io.StringIO()
        with (
            mock.patch.object(_log_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(_log_mod, "resolve_workspace", return_value="acme"),
            mock.patch.object(_log_mod, "resolve_repo", return_value="repo"),
            mock.patch.object(_log_mod, "BitbucketClient") as mock_client_cls,
            mock.patch.object(
                sys,
                "argv",
                ["pipeline_log.py", "--pipeline", "{p1}", "--step", "{s1}", "--log", "{l1}"],
            ),
            mock.patch("sys.stdout", stdout),
        ):
            mock_client_cls.return_value.get_pipeline_step_log.return_value = "hello"
            _log_mod.main()

        assert stdout.getvalue().strip() == "hello"
