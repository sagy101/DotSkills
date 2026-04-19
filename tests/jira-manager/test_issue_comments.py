#!/usr/bin/env python3
"""Tests for Jira comment and project operations."""

import importlib.util
import io
import sys
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "jira-manager" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_CLIENT_PATH = Path(_SCRIPTS_DIR) / "jira_client.py"
_client_spec = importlib.util.spec_from_file_location("jira_client", _CLIENT_PATH)
assert _client_spec is not None
assert _client_spec.loader is not None
_client_mod = importlib.util.module_from_spec(_client_spec)
_client_spec.loader.exec_module(_client_mod)
sys.modules["jira_client"] = _client_mod

_COMMENTS_PATH = Path(_SCRIPTS_DIR) / "issue_comments.py"
_comments_spec = importlib.util.spec_from_file_location("issue_comments", _COMMENTS_PATH)
assert _comments_spec is not None
assert _comments_spec.loader is not None
_comments_mod = importlib.util.module_from_spec(_comments_spec)
_comments_spec.loader.exec_module(_comments_mod)
sys.modules["issue_comments"] = _comments_mod

format_comments_table = _comments_mod.format_comments_table


def _make_client() -> Any:
    config = mock.MagicMock()
    config.jira_url = "https://example.atlassian.net"
    config.project_key = "API"
    with mock.patch.object(_client_mod, "resolve_credentials", return_value=("user", "token")):
        return _client_mod.JiraClient(config)


class TestJiraCommentMethods:
    def test_add_comment(self) -> None:
        client = _make_client()
        with mock.patch.object(client, "_request", return_value={"id": "10"}) as mock_request:
            result = client.add_comment("API-1", "Added text")

        assert result["id"] == "10"
        mock_request.assert_called_once_with(
            "POST",
            "/rest/api/3/issue/API-1/comment",
            {
                "body": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "Added text"}],
                        }
                    ],
                }
            },
        )

    def test_get_comment(self) -> None:
        client = _make_client()
        with mock.patch.object(client, "_request", return_value={"id": "10"}) as mock_request:
            result = client.get_comment("API-1", "10")

        assert result["id"] == "10"
        mock_request.assert_called_once_with("GET", "/rest/api/3/issue/API-1/comment/10")

    def test_update_comment(self) -> None:
        client = _make_client()
        with mock.patch.object(client, "_request", return_value={"id": "10"}) as mock_request:
            result = client.update_comment("API-1", "10", "Updated text")

        assert result["id"] == "10"
        mock_request.assert_called_once_with(
            "PUT",
            "/rest/api/3/issue/API-1/comment/10",
            {
                "body": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "Updated text"}],
                        }
                    ],
                }
            },
        )

    def test_delete_comment(self) -> None:
        client = _make_client()
        with mock.patch.object(client, "_request", return_value={}) as mock_request:
            result = client.delete_comment("API-1", "10")

        assert result == {}
        mock_request.assert_called_once_with("DELETE", "/rest/api/3/issue/API-1/comment/10")

    def test_get_comments_paginates(self) -> None:
        client = _make_client()
        pages = [
            {"comments": [{"id": "1"}], "startAt": 0, "maxResults": 1, "total": 2},
            {"comments": [{"id": "2"}], "startAt": 1, "maxResults": 1, "total": 2},
        ]
        with mock.patch.object(client, "_request", side_effect=pages) as mock_request:
            result = client.get_comments("API-1")

        assert result == [{"id": "1"}, {"id": "2"}]
        assert mock_request.call_args_list == [
            mock.call(
                "GET",
                "/rest/api/3/issue/API-1/comment",
                params={"startAt": "0", "maxResults": "100"},
            ),
            mock.call(
                "GET",
                "/rest/api/3/issue/API-1/comment",
                params={"startAt": "1", "maxResults": "100"},
            ),
        ]

    def test_get_remote_issue_links(self) -> None:
        client = _make_client()
        payload = [{"id": 1, "title": "doc"}]
        with mock.patch.object(client, "_request", return_value=payload) as mock_request:
            result = client.get_remote_issue_links("API-1")

        assert result == payload
        mock_request.assert_called_once_with("GET", "/rest/api/2/issue/API-1/remotelink")

    def test_get_visible_projects(self) -> None:
        client = _make_client()
        payload = [{"key": "API", "name": "API Team"}]
        with mock.patch.object(client, "_request", return_value=payload) as mock_request:
            result = client.get_visible_projects()

        assert result == payload
        mock_request.assert_called_once_with(
            "GET",
            "/rest/api/3/project/search",
            params={"startAt": "0", "maxResults": "50"},
        )

    def test_get_visible_projects_paginates(self) -> None:
        client = _make_client()
        pages = [
            {"values": [{"key": "API"}], "startAt": 0, "maxResults": 1, "total": 2},
            {"values": [{"key": "OPS"}], "startAt": 1, "maxResults": 1, "total": 2},
        ]
        with mock.patch.object(client, "_request", side_effect=pages) as mock_request:
            result = client.get_visible_projects()

        assert result == [{"key": "API"}, {"key": "OPS"}]
        assert mock_request.call_args_list == [
            mock.call(
                "GET", "/rest/api/3/project/search", params={"startAt": "0", "maxResults": "50"}
            ),
            mock.call(
                "GET", "/rest/api/3/project/search", params={"startAt": "1", "maxResults": "50"}
            ),
        ]

    def test_get_boards_paginates(self) -> None:
        client = _make_client()
        pages = [
            {"values": [{"id": 1}], "startAt": 0, "maxResults": 1, "total": 2},
            {"values": [{"id": 2}], "startAt": 1, "maxResults": 1, "total": 2},
        ]
        with mock.patch.object(client, "_request", side_effect=pages) as mock_request:
            result = client.get_boards()

        assert result == [{"id": 1}, {"id": 2}]
        assert mock_request.call_args_list == [
            mock.call(
                "GET",
                "/rest/agile/1.0/board",
                params={"projectKeyOrId": "API", "startAt": "0", "maxResults": "50"},
            ),
            mock.call(
                "GET",
                "/rest/agile/1.0/board",
                params={"projectKeyOrId": "API", "startAt": "1", "maxResults": "50"},
            ),
        ]


class TestFormatCommentsTable:
    def test_empty(self) -> None:
        assert format_comments_table([]) == "No comments found."

    def test_renders_rows(self) -> None:
        comments = [
            {
                "id": "10",
                "author": {"displayName": "Test User"},
                "updated": "2026-04-19T10:00:00.000+0300",
                "body": "Looks good",
            }
        ]

        table = format_comments_table(comments)

        assert "Test User" in table
        assert "Looks good" in table

    def test_renders_adf_body(self) -> None:
        comments = [
            {
                "id": "10",
                "author": {"displayName": "Test User"},
                "updated": "2026-04-19T10:00:00.000+0300",
                "body": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "ADF body"}],
                        }
                    ],
                },
            }
        ]

        table = format_comments_table(comments)

        assert "ADF body" in table


class TestIssueCommentsMain:
    def test_list_rejects_json_format(self) -> None:
        with (
            mock.patch.object(_comments_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(
                sys, "argv", ["issue_comments.py", "list", "--key", "API-1", "--format", "json"]
            ),
            pytest.raises(SystemExit),
        ):
            _comments_mod.main()

    def test_add_requires_body(self) -> None:
        with (
            mock.patch.object(_comments_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(sys, "argv", ["issue_comments.py", "add", "--key", "API-1"]),
            pytest.raises(SystemExit),
        ):
            _comments_mod.main()

    def test_edit_requires_comment_id(self) -> None:
        with (
            mock.patch.object(_comments_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(
                sys, "argv", ["issue_comments.py", "edit", "--key", "API-1", "--body", "Updated"]
            ),
            pytest.raises(SystemExit),
        ):
            _comments_mod.main()

    def test_add_calls_client(self) -> None:
        stdout = io.StringIO()
        with (
            mock.patch.object(_comments_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(_comments_mod, "JiraClient") as mock_client_cls,
            mock.patch.object(
                sys, "argv", ["issue_comments.py", "add", "--key", "API-1", "--body", "Hi"]
            ),
            mock.patch("sys.stdout", stdout),
        ):
            mock_client_cls.return_value.add_comment.return_value = {"id": "10"}
            _comments_mod.main()

        mock_client_cls.return_value.add_comment.assert_called_once_with("API-1", "Hi")
        assert "Added comment" in stdout.getvalue()

    def test_edit_calls_client(self) -> None:
        stdout = io.StringIO()
        with (
            mock.patch.object(_comments_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(_comments_mod, "JiraClient") as mock_client_cls,
            mock.patch.object(
                sys,
                "argv",
                [
                    "issue_comments.py",
                    "edit",
                    "--key",
                    "API-1",
                    "--comment-id",
                    "10",
                    "--body",
                    "Updated",
                ],
            ),
            mock.patch("sys.stdout", stdout),
        ):
            mock_client_cls.return_value.update_comment.return_value = {"id": "10"}
            _comments_mod.main()

        mock_client_cls.return_value.update_comment.assert_called_once_with(
            "API-1", "10", "Updated"
        )
        assert "Updated comment" in stdout.getvalue()

    def test_delete_calls_client(self) -> None:
        stdout = io.StringIO()
        with (
            mock.patch.object(_comments_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(_comments_mod, "JiraClient") as mock_client_cls,
            mock.patch.object(
                sys,
                "argv",
                ["issue_comments.py", "delete", "--key", "API-1", "--comment-id", "10"],
            ),
            mock.patch("sys.stdout", stdout),
        ):
            mock_client_cls.return_value.delete_comment.return_value = {}
            _comments_mod.main()

        mock_client_cls.return_value.delete_comment.assert_called_once_with("API-1", "10")
        assert "Deleted comment" in stdout.getvalue()
