#!/usr/bin/env python3
"""Tests for reopening Bitbucket PR comment threads from pr_comment.py."""

import importlib.util
import io
import sys
from pathlib import Path
from unittest import mock

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "bitbucket-manager" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_MODULE_PATH = Path(_SCRIPTS_DIR) / "pr_comment.py"
_spec = importlib.util.spec_from_file_location("pr_comment", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["pr_comment"] = _mod


class TestPrCommentUnresolve:
    def test_bulk_unresolve_calls_client(self) -> None:
        stdout = io.StringIO()
        client = mock.MagicMock()
        client.unresolve_pr_comment.return_value = {}

        with (
            mock.patch.object(_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(_mod, "resolve_workspace", return_value="acme"),
            mock.patch.object(_mod, "resolve_repo", return_value="repo"),
            mock.patch.object(_mod, "BitbucketClient", return_value=client),
            mock.patch.object(sys, "argv", ["pr_comment.py", "--pr", "42", "--unresolve", "7"]),
            mock.patch("sys.stdout", stdout),
        ):
            _mod.main()

        assert "Reopened #7" in stdout.getvalue()
        client.unresolve_pr_comment.assert_called_once_with(
            workspace="acme",
            repo_slug="repo",
            pr_id=42,
            comment_id=7,
        )
