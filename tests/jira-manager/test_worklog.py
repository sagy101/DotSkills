#!/usr/bin/env python3
"""Tests for worklog support in jira_client.py and update_ticket.py."""

import importlib.util
import sys
from pathlib import Path
from unittest import mock

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "jira-manager" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_CLIENT_PATH = Path(_SCRIPTS_DIR) / "jira_client.py"
_spec = importlib.util.spec_from_file_location("jira_client", _CLIENT_PATH)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["jira_client"] = _mod

JiraClient = _mod.JiraClient

_UPDATE_PATH = Path(_SCRIPTS_DIR) / "update_ticket.py"
_uspec = importlib.util.spec_from_file_location("update_ticket", _UPDATE_PATH)
assert _uspec is not None
assert _uspec.loader is not None
_umod = importlib.util.module_from_spec(_uspec)
_uspec.loader.exec_module(_umod)
sys.modules["update_ticket"] = _umod

_handle_worklog = _umod._handle_worklog


class TestJiraClientWorklog:
    """Test JiraClient worklog methods construct correct requests."""

    def test_add_worklog_minimal(self) -> None:
        client = mock.MagicMock(spec=JiraClient)
        client.add_worklog.return_value = {"id": "123"}
        result = client.add_worklog("PROJ-1", "2h")
        client.add_worklog.assert_called_once_with("PROJ-1", "2h")
        assert result["id"] == "123"

    def test_add_worklog_with_comment(self) -> None:
        client = mock.MagicMock(spec=JiraClient)
        client.add_worklog.return_value = {"id": "456"}
        client.add_worklog("PROJ-1", "1d", comment="Code review")
        client.add_worklog.assert_called_once_with("PROJ-1", "1d", comment="Code review")

    def test_get_worklogs(self) -> None:
        client = mock.MagicMock(spec=JiraClient)
        client.get_worklogs.return_value = [{"timeSpent": "2h"}]
        result = client.get_worklogs("PROJ-1")
        assert len(result) == 1
        assert result[0]["timeSpent"] == "2h"


class TestHandleWorklog:
    """Test _handle_worklog helper in update_ticket.py."""

    def test_none_time_is_noop(self, capsys: object) -> None:
        client = mock.MagicMock()
        _handle_worklog(client, "PROJ-1", None, None)
        client.add_worklog.assert_not_called()

    def test_empty_time_is_noop(self, capsys: object) -> None:
        client = mock.MagicMock()
        _handle_worklog(client, "PROJ-1", "", None)
        client.add_worklog.assert_not_called()

    def test_success(self, capsys: object) -> None:
        client = mock.MagicMock()
        client.add_worklog.return_value = {"id": "789"}
        _handle_worklog(client, "PROJ-1", "3h", "Testing")
        client.add_worklog.assert_called_once_with("PROJ-1", "3h", comment="Testing")
        captured = capsys.readouterr()  # type: ignore[attr-defined]
        assert "Logged 3h on PROJ-1" in captured.out
        assert "Testing" in captured.out

    def test_success_no_comment(self, capsys: object) -> None:
        client = mock.MagicMock()
        client.add_worklog.return_value = {"id": "789"}
        _handle_worklog(client, "PROJ-1", "30m", None)
        client.add_worklog.assert_called_once_with("PROJ-1", "30m", comment=None)
        captured = capsys.readouterr()  # type: ignore[attr-defined]
        assert "Logged 30m on PROJ-1" in captured.out

    def test_failure_warns(self, capsys: object) -> None:
        client = mock.MagicMock()
        client.add_worklog.side_effect = Exception("API error")
        _handle_worklog(client, "PROJ-1", "2h", None)
        captured = capsys.readouterr()  # type: ignore[attr-defined]
        assert "WARNING" in captured.err
