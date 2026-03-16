#!/usr/bin/env python3
"""Tests for workflow_ops.py — transition resolution, status changes, attachments."""

import importlib.util
import sys
from pathlib import Path
from unittest import mock

import pytest

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "jira-manager" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_MODULE_PATH = Path(_SCRIPTS_DIR) / "workflow_ops.py"
_spec = importlib.util.spec_from_file_location("workflow_ops", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["workflow_ops"] = _mod

resolve_transition = _mod.resolve_transition
handle_status_transition = _mod.handle_status_transition
upload_attachments = _mod.upload_attachments


def _make_transitions(items):
    """Build transition list: [(id, name, to_status_name), ...]"""
    return [
        {"id": str(tid), "name": tname, "to": {"name": to_name}}
        for tid, tname, to_name in items
    ]


def _make_config(status_values=None):
    config = mock.MagicMock()
    if status_values:
        config.field_catalog = {
            "status": {"values": status_values}
        }
    else:
        config.field_catalog = {}
    return config


# ---------------------------------------------------------------------------
# resolve_transition — multi-level fallback
# ---------------------------------------------------------------------------

class TestResolveTransition:
    def test_match_by_target_status_name(self):
        client = mock.MagicMock()
        client.get_transitions.return_value = _make_transitions([
            (1, "Start Progress", "In Progress"),
            (2, "Close", "Done"),
        ])
        result = resolve_transition(client, "T-1", "In Progress", _make_config())
        assert result == ("1", "Start Progress", "In Progress")

    def test_match_by_target_status_case_insensitive(self):
        client = mock.MagicMock()
        client.get_transitions.return_value = _make_transitions([
            (1, "Start", "In Progress"),
        ])
        result = resolve_transition(client, "T-1", "in progress", _make_config())
        assert result[2] == "In Progress"

    def test_match_by_transition_name(self):
        """When target status doesn't match, fall back to transition name."""
        client = mock.MagicMock()
        client.get_transitions.return_value = _make_transitions([
            (5, "Done", "Completed"),
        ])
        result = resolve_transition(client, "T-1", "Done", _make_config())
        assert result == ("5", "Done", "Completed")

    def test_match_via_catalog_resolution(self):
        """When neither status nor transition name match, try catalog."""
        client = mock.MagicMock()
        client.get_transitions.return_value = _make_transitions([
            (3, "Finish", "Done"),
        ])
        config = _make_config(status_values={
            "completed": {"id": "10", "name": "Done"}
        })
        result = resolve_transition(client, "T-1", "Completed", config)
        assert result[2] == "Done"

    def test_no_match_returns_none(self):
        client = mock.MagicMock()
        client.get_transitions.return_value = _make_transitions([
            (1, "Start", "In Progress"),
        ])
        result = resolve_transition(client, "T-1", "Nonexistent", _make_config())
        assert result is None

    def test_empty_transitions(self):
        client = mock.MagicMock()
        client.get_transitions.return_value = []
        result = resolve_transition(client, "T-1", "Done", _make_config())
        assert result is None

    def test_first_match_wins(self):
        client = mock.MagicMock()
        client.get_transitions.return_value = _make_transitions([
            (1, "Resolve", "Done"),
            (2, "Close", "Done"),
        ])
        result = resolve_transition(client, "T-1", "Done", _make_config())
        assert result[0] == "1"  # first match


# ---------------------------------------------------------------------------
# handle_status_transition
# ---------------------------------------------------------------------------

class TestHandleStatusTransition:
    def test_success(self):
        client = mock.MagicMock()
        client.get_transitions.return_value = _make_transitions([
            (1, "Start", "In Progress"),
        ])
        result = handle_status_transition(client, "T-1", "In Progress", _make_config())
        assert result is True
        client.transition_issue.assert_called_once_with("T-1", "1")

    def test_no_transition_warn_only_returns_false(self):
        client = mock.MagicMock()
        client.get_transitions.return_value = []
        result = handle_status_transition(client, "T-1", "Done", _make_config(), warn_only=True)
        assert result is False

    def test_no_transition_strict_exits(self):
        client = mock.MagicMock()
        client.get_transitions.return_value = []
        with pytest.raises(SystemExit):
            handle_status_transition(client, "T-1", "Done", _make_config(), warn_only=False)

    def test_api_failure_warn_only_returns_false(self):
        client = mock.MagicMock()
        client.get_transitions.return_value = _make_transitions([
            (1, "Start", "In Progress"),
        ])
        client.transition_issue.side_effect = Exception("API error")
        result = handle_status_transition(client, "T-1", "In Progress", _make_config(), warn_only=True)
        assert result is False

    def test_api_failure_strict_exits(self):
        client = mock.MagicMock()
        client.get_transitions.return_value = _make_transitions([
            (1, "Start", "In Progress"),
        ])
        client.transition_issue.side_effect = Exception("API error")
        with pytest.raises(SystemExit):
            handle_status_transition(client, "T-1", "In Progress", _make_config(), warn_only=False)

    def test_available_statuses_in_error_message(self, capsys):
        client = mock.MagicMock()
        client.get_transitions.return_value = _make_transitions([
            (1, "Start", "In Progress"),
            (2, "Close", "Done"),
        ])
        handle_status_transition(client, "T-1", "Nonexistent", _make_config(), warn_only=True)
        captured = capsys.readouterr()
        assert "In Progress" in captured.err
        assert "Done" in captured.err


# ---------------------------------------------------------------------------
# upload_attachments
# ---------------------------------------------------------------------------

class TestUploadAttachments:
    def test_empty_list(self):
        client = mock.MagicMock()
        result = upload_attachments(client, "T-1", [])
        assert result is True
        client.add_attachment.assert_not_called()

    def test_success(self):
        client = mock.MagicMock()
        client.add_attachment.return_value = [{"filename": "report.pdf"}]
        result = upload_attachments(client, "T-1", ["report.pdf"])
        assert result is True

    def test_partial_failure(self):
        client = mock.MagicMock()
        client.add_attachment.side_effect = [
            [{"filename": "a.pdf"}],
            Exception("upload failed"),
        ]
        result = upload_attachments(client, "T-1", ["a.pdf", "b.pdf"])
        assert result is False

    def test_all_fail(self):
        client = mock.MagicMock()
        client.add_attachment.side_effect = Exception("fail")
        result = upload_attachments(client, "T-1", ["a.pdf"])
        assert result is False


if __name__ == "__main__":
    import subprocess
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
