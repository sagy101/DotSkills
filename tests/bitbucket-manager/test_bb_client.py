#!/usr/bin/env python3
"""Tests for new Bitbucket client helpers used by the Bitbucket lane."""

import importlib.util
import os
import sys
import urllib.error
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "bitbucket-manager" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_CLIENT_PATH = Path(_SCRIPTS_DIR) / "bb_client.py"
_client_spec = importlib.util.spec_from_file_location("bb_client", _CLIENT_PATH)
assert _client_spec is not None
assert _client_spec.loader is not None
_client_mod = importlib.util.module_from_spec(_client_spec)
_client_spec.loader.exec_module(_client_mod)
sys.modules["bb_client"] = _client_mod


def _make_client() -> Any:
    config = SimpleNamespace(
        workspace="acme",
        auth_mode="basic",
        email_env="BITBUCKET_EMAIL",
        token_env="BITBUCKET_TOKEN",
        env_file=None,
        repo_tokens={},
        project_root=Path.cwd(),
        auto_detect_repo=lambda: "repo",
    )
    return _client_mod.BitbucketClient(config)


def _make_bearer_client(auto_repo: str | None = "repo") -> Any:
    config = SimpleNamespace(
        workspace="acme",
        auth_mode="basic",
        email_env="BITBUCKET_EMAIL",
        token_env="BITBUCKET_TOKEN",
        env_file=None,
        repo_tokens={f"acme/{auto_repo}": "BB_ACCESS_TOKEN"} if auto_repo else {},
        project_root=Path.cwd(),
        auto_detect_repo=lambda: auto_repo,
    )
    return _client_mod.BitbucketClient(config)


class TestPrDiff:
    def test_get_pr_diff(self) -> None:
        client = _make_client()
        with mock.patch.object(client, "_request", return_value="diff") as mock_request:
            result = client.get_pr_diff("acme", "repo", 42)

        assert result == "diff"
        mock_request.assert_called_once_with(
            "GET",
            "/repositories/acme/repo/pullrequests/42/diff",
            raw=True,
        )


class TestPipelines:
    def test_list_pipelines(self) -> None:
        client = _make_client()
        payload = {"values": [{"uuid": "{p1}"}]}
        with mock.patch.object(
            client, "_paginate", return_value=payload["values"]
        ) as mock_paginate:
            result = client.list_pipelines("acme", "repo")

        assert result == payload["values"]
        mock_paginate.assert_called_once_with("/repositories/acme/repo/pipelines", max_results=50)

    def test_get_pipeline(self) -> None:
        client = _make_client()
        with mock.patch.object(client, "_request", return_value={"uuid": "{p1}"}) as mock_request:
            result = client.get_pipeline("acme", "repo", "{p1}")

        assert result["uuid"] == "{p1}"
        mock_request.assert_called_once_with(
            "GET",
            "/repositories/acme/repo/pipelines/{p1}",
        )

    def test_run_pipeline(self) -> None:
        client = _make_client()
        with mock.patch.object(client, "_request", return_value={"uuid": "{p2}"}) as mock_request:
            result = client.run_pipeline(
                "acme",
                "repo",
                target={"type": "pipeline_ref_target"},
            )

        assert result["uuid"] == "{p2}"
        mock_request.assert_called_once_with(
            "POST",
            "/repositories/acme/repo/pipelines",
            data={"target": {"type": "pipeline_ref_target"}},
        )

    def test_list_pipeline_steps(self) -> None:
        client = _make_client()
        with mock.patch.object(
            client, "_paginate", return_value=[{"uuid": "{s1}"}]
        ) as mock_paginate:
            result = client.list_pipeline_steps("acme", "repo", "{p1}")

        assert result == [{"uuid": "{s1}"}]
        mock_paginate.assert_called_once_with(
            "/repositories/acme/repo/pipelines/{p1}/steps", max_results=50
        )

    def test_get_pipeline_step_log(self) -> None:
        client = _make_client()
        with mock.patch.object(client, "_request", return_value="log text") as mock_request:
            result = client.get_pipeline_step_log("acme", "repo", "{p1}", "{s1}", "{l1}")

        assert result == "log text"
        mock_request.assert_called_once_with(
            "GET",
            "/repositories/acme/repo/pipelines/{p1}/steps/{s1}/logs/{l1}",
            raw=True,
        )

    def test_list_environments(self) -> None:
        client = _make_client()
        with mock.patch.object(
            client, "_paginate", return_value=[{"uuid": "{e1}"}]
        ) as mock_paginate:
            result = client.list_environments("acme", "repo")

        assert result == [{"uuid": "{e1}"}]
        mock_paginate.assert_called_once_with(
            "/repositories/acme/repo/environments", max_results=50
        )

    def test_get_environment(self) -> None:
        client = _make_client()
        with mock.patch.object(client, "_request", return_value={"uuid": "{e1}"}) as mock_request:
            result = client.get_environment("acme", "repo", "{e1}")

        assert result["uuid"] == "{e1}"
        mock_request.assert_called_once_with(
            "GET",
            "/repositories/acme/repo/environments/{e1}",
        )

    def test_list_deployments(self) -> None:
        client = _make_client()
        with mock.patch.object(
            client, "_paginate", return_value=[{"uuid": "{d1}"}]
        ) as mock_paginate:
            result = client.list_deployments("acme", "repo")

        assert result == [{"uuid": "{d1}"}]
        mock_paginate.assert_called_once_with("/repositories/acme/repo/deployments", max_results=50)

    def test_get_deployment(self) -> None:
        client = _make_client()
        with mock.patch.object(client, "_request", return_value={"uuid": "{d1}"}) as mock_request:
            result = client.get_deployment("acme", "repo", "{d1}")

        assert result["uuid"] == "{d1}"
        mock_request.assert_called_once_with(
            "GET",
            "/repositories/acme/repo/deployments/{d1}",
        )


class TestConnectivity:
    def test_test_connection_success(self) -> None:
        client = _make_client()
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with (
            mock.patch.dict(
                os.environ,
                {"BITBUCKET_EMAIL": "user@example.com", "BITBUCKET_TOKEN": "token"},
                clear=False,
            ),
            mock.patch.object(
                _client_mod.urllib.request, "urlopen", return_value=response
            ) as mock_urlopen,
        ):
            ok, detail = client.test_connection("acme")

        assert ok is True
        assert detail == "Using basic auth"
        mock_urlopen.assert_called_once()

    def test_test_connection_401_has_actionable_hint(self) -> None:
        client = _make_client()
        error = urllib.error.HTTPError(
            "https://api.bitbucket.org/2.0/repositories/acme",
            401,
            "Unauthorized",
            hdrs=Message(),
            fp=None,
        )
        with (
            mock.patch.dict(
                os.environ,
                {"BITBUCKET_EMAIL": "user@example.com", "BITBUCKET_TOKEN": "token"},
                clear=False,
            ),
            mock.patch.object(_client_mod.urllib.request, "urlopen", side_effect=error),
        ):
            ok, detail = client.test_connection("acme")

        assert ok is False
        assert detail is not None
        assert "REST auth rejected the token" in detail
        assert "Plain no-scope Atlassian tokens will fail" in detail
        assert "SSH git access alone does not validate REST auth" in detail

    def test_bearer_client_uses_bearer_header(self) -> None:
        client = _make_bearer_client()
        headers = client._build_headers("bearer", None, "access-token")
        assert headers["Authorization"] == "Bearer access-token"

    def test_bearer_test_connection_uses_repo_endpoint(self) -> None:
        client = _make_bearer_client(auto_repo="demo-repo")
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False

        with (
            mock.patch.dict(
                os.environ,
                {
                    "BB_ACCESS_TOKEN": "access-token",
                    "BITBUCKET_EMAIL": "",
                    "BITBUCKET_TOKEN": "",
                },
                clear=False,
            ),
            mock.patch.object(
                _client_mod.urllib.request, "urlopen", return_value=response
            ) as mock_urlopen,
        ):
            ok, detail = client.test_connection("acme", "demo-repo")

        assert ok is True
        assert detail == "Using repo_token auth"
        request = mock_urlopen.call_args.args[0]
        assert request.full_url == "https://api.bitbucket.org/2.0/repositories/acme/demo-repo"

    def test_bearer_test_connection_404_explains_repo_scope(self) -> None:
        client = _make_bearer_client(auto_repo="demo-repo")
        error = urllib.error.HTTPError(
            "https://api.bitbucket.org/2.0/repositories/acme/demo-repo",
            404,
            "Not Found",
            hdrs=Message(),
            fp=None,
        )
        with (
            mock.patch.dict(
                os.environ,
                {
                    "BB_ACCESS_TOKEN": "access-token",
                    "BITBUCKET_EMAIL": "",
                    "BITBUCKET_TOKEN": "",
                },
                clear=False,
            ),
            mock.patch.object(_client_mod.urllib.request, "urlopen", side_effect=error),
        ):
            ok, detail = client.test_connection("acme", "demo-repo")

        assert ok is False
        assert detail is not None
        assert "Verify the token scope matches this repository" in detail
