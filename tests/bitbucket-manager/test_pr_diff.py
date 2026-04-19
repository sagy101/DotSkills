#!/usr/bin/env python3
"""Tests for pr_diff.py."""

import importlib.util
import io
import sys
from pathlib import Path
from unittest import mock

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "bitbucket-manager" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_MODULE_PATH = Path(_SCRIPTS_DIR) / "pr_diff.py"
_spec = importlib.util.spec_from_file_location("pr_diff", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["pr_diff"] = _mod


class TestPrDiffMain:
    def test_plain_diff_prints_raw_text(self) -> None:
        stdout = io.StringIO()
        with (
            mock.patch.object(_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(_mod, "resolve_workspace", return_value="acme"),
            mock.patch.object(_mod, "resolve_repo", return_value="repo"),
            mock.patch.object(_mod, "BitbucketClient") as mock_client_cls,
            mock.patch.object(sys, "argv", ["pr_diff.py", "--pr", "42"]),
            mock.patch("sys.stdout", stdout),
        ):
            mock_client_cls.return_value.get_pr_diff.return_value = "diff --git a/x b/x\n"
            _mod.main()

        assert "diff --git" in stdout.getvalue()

    def test_summary_lists_files(self) -> None:
        stdout = io.StringIO()
        diff_text = (
            "diff --git a/x b/x\n"
            "+++ b/x\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
            "diff --git a/y b/y\n"
            "+++ b/y\n"
            "@@ -1 +1 @@\n"
            "-one\n"
            "+two\n"
        )
        with (
            mock.patch.object(_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(_mod, "resolve_workspace", return_value="acme"),
            mock.patch.object(_mod, "resolve_repo", return_value="repo"),
            mock.patch.object(_mod, "BitbucketClient") as mock_client_cls,
            mock.patch.object(sys, "argv", ["pr_diff.py", "--pr", "42", "--format", "summary"]),
            mock.patch("sys.stdout", stdout),
        ):
            mock_client_cls.return_value.get_pr_diff.return_value = diff_text
            _mod.main()

        out = stdout.getvalue()
        assert "2 file(s)" in out
        assert "x" in out and "y" in out

    def test_empty_diff_reports_no_changes(self) -> None:
        stdout = io.StringIO()
        with (
            mock.patch.object(_mod, "load_config", return_value=mock.MagicMock()),
            mock.patch.object(_mod, "resolve_workspace", return_value="acme"),
            mock.patch.object(_mod, "resolve_repo", return_value="repo"),
            mock.patch.object(_mod, "BitbucketClient") as mock_client_cls,
            mock.patch.object(sys, "argv", ["pr_diff.py", "--pr", "42", "--format", "summary"]),
            mock.patch("sys.stdout", stdout),
        ):
            mock_client_cls.return_value.get_pr_diff.return_value = ""
            _mod.main()

        assert "0 file(s)" in stdout.getvalue()
