#!/usr/bin/env python3
"""Tests for discover_fields.py --transitions feature."""

import importlib.util
import sys
from pathlib import Path
from unittest import mock

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "jira-manager" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_MODULE_PATH = Path(_SCRIPTS_DIR) / "discover_fields.py"
_spec = importlib.util.spec_from_file_location("discover_fields", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["discover_fields"] = _mod

_run_transitions = _mod._run_transitions


def _mock_client(transitions: list[dict[str, object]]) -> mock.MagicMock:
    client = mock.MagicMock()
    client.get_transitions.return_value = transitions
    return client


class TestRunTransitions:
    def test_no_transitions(self, capsys: object) -> None:
        client = _mock_client([])
        _run_transitions(client, "PROJ-1")
        captured = capsys.readouterr()  # type: ignore[attr-defined]
        assert "No transitions available" in captured.out

    def test_single_transition(self, capsys: object) -> None:
        client = _mock_client(
            [
                {"id": "21", "name": "In Progress", "to": {"name": "In Progress"}},
            ]
        )
        _run_transitions(client, "PROJ-1")
        captured = capsys.readouterr()  # type: ignore[attr-defined]
        assert "Available transitions for PROJ-1 (1 found)" in captured.out
        assert "21" in captured.out
        assert "In Progress" in captured.out

    def test_multiple_transitions(self, capsys: object) -> None:
        client = _mock_client(
            [
                {"id": "21", "name": "In Progress", "to": {"name": "In Progress"}},
                {"id": "31", "name": "Done", "to": {"name": "Done"}},
                {"id": "41", "name": "Cancelled", "to": {"name": "Cancelled"}},
            ]
        )
        _run_transitions(client, "PROJ-99")
        captured = capsys.readouterr()  # type: ignore[attr-defined]
        assert "3 found" in captured.out
        assert "Done" in captured.out
        assert "Cancelled" in captured.out

    def test_transition_missing_to_field(self, capsys: object) -> None:
        client = _mock_client(
            [
                {"id": "21", "name": "Start"},
            ]
        )
        _run_transitions(client, "PROJ-1")
        captured = capsys.readouterr()  # type: ignore[attr-defined]
        assert "21" in captured.out
        assert "Start" in captured.out

    def test_api_error_exits(self) -> None:
        import pytest

        client = mock.MagicMock()
        client.get_transitions.side_effect = Exception("404 Not Found")
        with pytest.raises(SystemExit):
            _run_transitions(client, "PROJ-BAD")

    def test_client_called_with_key(self) -> None:
        client = _mock_client([])
        _run_transitions(client, "API-8620")
        client.get_transitions.assert_called_once_with("API-8620")
