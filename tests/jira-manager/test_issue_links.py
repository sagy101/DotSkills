#!/usr/bin/env python3
"""Tests for update_ticket.py _handle_issue_link — link type resolution and direction."""

import importlib.util
import sys
from pathlib import Path
from unittest import mock

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "jira-manager" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_MODULE_PATH = Path(_SCRIPTS_DIR) / "update_ticket.py"
_spec = importlib.util.spec_from_file_location("update_ticket", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["update_ticket"] = _mod

_handle_issue_link = _mod._handle_issue_link


LINK_TYPES = [
    {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
    {"name": "Duplicate", "inward": "is duplicated by", "outward": "duplicates"},
    {"name": "Cloners", "inward": "is cloned by", "outward": "clones"},
]


def _make_client(link_types=None):
    client = mock.MagicMock()
    client.get_link_types.return_value = link_types or LINK_TYPES
    return client


# ---------------------------------------------------------------------------
# Format validation
# ---------------------------------------------------------------------------

class TestLinkFormatValidation:
    def test_missing_colon(self, capsys):
        client = _make_client()
        _handle_issue_link(client, "T-1", "BlocksT-2")
        client.add_issue_link.assert_not_called()
        assert "Invalid link format" in capsys.readouterr().err

    def test_empty_target_key(self, capsys):
        client = _make_client()
        _handle_issue_link(client, "T-1", "Blocks:")
        client.add_issue_link.assert_not_called()
        assert "No target key" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Link type matching
# ---------------------------------------------------------------------------

class TestLinkTypeMatching:
    def test_match_by_name(self):
        client = _make_client()
        _handle_issue_link(client, "T-1", "Blocks:T-2")
        client.add_issue_link.assert_called_once_with("Blocks", "T-1", "T-2")

    def test_match_by_name_case_insensitive(self):
        client = _make_client()
        _handle_issue_link(client, "T-1", "blocks:T-2")
        client.add_issue_link.assert_called_once_with("Blocks", "T-1", "T-2")

    def test_match_by_outward(self):
        client = _make_client()
        _handle_issue_link(client, "T-1", "duplicates:T-2")
        client.add_issue_link.assert_called_once_with("Duplicate", "T-1", "T-2")

    def test_match_by_inward_swaps_direction(self):
        """Inward match means the target blocks the source — swap order."""
        client = _make_client()
        _handle_issue_link(client, "T-1", "is blocked by:T-2")
        # T-2 blocks T-1 (swapped)
        client.add_issue_link.assert_called_once_with("Blocks", "T-2", "T-1")

    def test_inward_case_insensitive(self):
        client = _make_client()
        _handle_issue_link(client, "T-1", "Is Blocked By:T-2")
        client.add_issue_link.assert_called_once_with("Blocks", "T-2", "T-1")


# ---------------------------------------------------------------------------
# Unknown link type
# ---------------------------------------------------------------------------

class TestUnknownLinkType:
    def test_unknown_type_shows_available(self, capsys):
        client = _make_client()
        _handle_issue_link(client, "T-1", "FakeType:T-2")
        client.add_issue_link.assert_not_called()
        err = capsys.readouterr().err
        assert "Unknown link type" in err
        assert "Blocks" in err

    def test_empty_link_types(self, capsys):
        client = _make_client(link_types=[])
        _handle_issue_link(client, "T-1", "Nonexistent:T-2")
        client.add_issue_link.assert_not_called()
        assert "Unknown link type" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# API failure — graceful handling
# ---------------------------------------------------------------------------

class TestLinkApiFailure:
    def test_api_error_warns_not_exits(self, capsys):
        client = _make_client()
        client.add_issue_link.side_effect = Exception("API error")
        # Should NOT raise — it warns
        _handle_issue_link(client, "T-1", "Blocks:T-2")
        assert "Failed to create link" in capsys.readouterr().err

    def test_whitespace_in_target_key(self):
        client = _make_client()
        _handle_issue_link(client, "T-1", "Blocks: T-2 ")
        client.add_issue_link.assert_called_once_with("Blocks", "T-1", "T-2")


if __name__ == "__main__":
    import subprocess
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
