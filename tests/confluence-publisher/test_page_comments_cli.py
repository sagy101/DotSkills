#!/usr/bin/env python3
"""CLI tests for page_comments.py — v2 comment manager dispatch."""

import importlib.util
import sys
from pathlib import Path
from unittest import mock

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "confluence-publisher"
    / "scripts"
    / "page_comments.py"
)
_spec = importlib.util.spec_from_file_location("confluence_page_comments", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["confluence_page_comments"] = _mod


class TestPageCommentsCli:
    def test_reply_dispatches_to_helper(self) -> None:
        with (
            mock.patch.object(_mod, "load_config"),
            mock.patch.object(_mod, "reply_to_comment", return_value="201") as reply,
        ):
            argv = [
                "page_comments.py",
                "reply",
                "--page-id",
                "100",
                "--parent-comment-id",
                "200",
                "--body",
                "<p>Reply</p>",
            ]
            with mock.patch.object(sys, "argv", argv):
                _mod.main()
        reply.assert_called_once()
        assert reply.call_args.kwargs["comment_type"] == "comment"

    def test_reply_rejects_inline_switch(self) -> None:
        argv = [
            "page_comments.py",
            "reply",
            "--page-id",
            "100",
            "--parent-comment-id",
            "200",
            "--body",
            "<p>Reply</p>",
            "--inline",
        ]
        with mock.patch.object(sys, "argv", argv), pytest.raises(SystemExit):
            _mod.main()

    def test_resolve_dispatches_to_helper(self) -> None:
        with (
            mock.patch.object(_mod, "load_config"),
            mock.patch.object(_mod, "resolve_comment", return_value={"id": "200"}) as resolve,
        ):
            argv = [
                "page_comments.py",
                "resolve",
                "--comment-id",
                "200",
            ]
            with mock.patch.object(sys, "argv", argv):
                _mod.main()
        resolve.assert_called_once()

    def test_likes_prints_counts(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            mock.patch.object(_mod, "load_config"),
            mock.patch.object(_mod, "get_page_like_count", return_value=3),
            mock.patch.object(_mod, "get_page_like_users", return_value=["a1", "a2"]),
        ):
            argv = [
                "page_comments.py",
                "likes",
                "--page-id",
                "100",
            ]
            with mock.patch.object(sys, "argv", argv):
                _mod.main()
        out = capsys.readouterr().out
        assert "3" in out
        assert "a1" in out

    def test_tree_output_invokes_recursive_walk(self, capsys: pytest.CaptureFixture[str]) -> None:
        comments = [
            mock.MagicMock(
                comment_id="1",
                body_html="<p>Root</p>",
                author="A",
                created="now",
                parent_comment_id="",
            ),
            mock.MagicMock(
                comment_id="2",
                body_html="<p>Child</p>",
                author="B",
                created="now",
                parent_comment_id="1",
            ),
        ]
        with (
            mock.patch.object(_mod, "load_config"),
            mock.patch.object(_mod, "walk_comment_thread", return_value=comments) as walk,
        ):
            argv = [
                "page_comments.py",
                "list",
                "--page-id",
                "100",
                "--tree",
            ]
            with mock.patch.object(sys, "argv", argv):
                _mod.main()
        walk.assert_called_once()
        out = capsys.readouterr().out
        assert "Root" in out
        assert "Child" in out
