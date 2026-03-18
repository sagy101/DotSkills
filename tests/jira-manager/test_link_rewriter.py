#!/usr/bin/env python3
"""Tests for link_rewriter.py — git URL parsing, link rewriting."""

import importlib.util
import sys
from pathlib import Path
from unittest import mock

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "jira-manager" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_MODULE_PATH = Path(_SCRIPTS_DIR) / "link_rewriter.py"
_spec = importlib.util.spec_from_file_location("link_rewriter", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["link_rewriter"] = _mod

_git_remote_to_browse_base = _mod._git_remote_to_browse_base
rewrite_links_to_git = _mod.rewrite_links_to_git
rewrite_links_to_local = _mod.rewrite_links_to_local


def _make_config(remote_url: str | None, branch: str = "main") -> mock.MagicMock:
    config = mock.MagicMock()
    config.resolve_git_remote_url.return_value = remote_url
    config.resolve_git_branch.return_value = branch
    return config


# ---------------------------------------------------------------------------
# _git_remote_to_browse_base — SSH URLs
# ---------------------------------------------------------------------------


class TestGitRemoteSsh:
    def test_bitbucket_ssh(self):
        result = _git_remote_to_browse_base("git@bitbucket.org:acme/repo.git", "main")
        assert result == "https://bitbucket.org/acme/repo/src/main/"

    def test_github_ssh(self):
        result = _git_remote_to_browse_base("git@github.com:user/repo.git", "main")
        assert result == "https://github.com/user/repo/blob/main/"

    def test_gitlab_ssh(self):
        result = _git_remote_to_browse_base("git@gitlab.com:org/repo.git", "main")
        assert result == "https://gitlab.com/org/repo/-/blob/main/"

    def test_ssh_without_git_suffix(self):
        result = _git_remote_to_browse_base("git@github.com:user/repo", "main")
        assert result == "https://github.com/user/repo/blob/main/"

    def test_custom_branch(self):
        result = _git_remote_to_browse_base("git@github.com:user/repo.git", "develop")
        assert "develop" in result

    def test_whitespace_stripped(self):
        result = _git_remote_to_browse_base("  git@github.com:user/repo.git  ", "main")
        assert result == "https://github.com/user/repo/blob/main/"


# ---------------------------------------------------------------------------
# _git_remote_to_browse_base — HTTPS URLs
# ---------------------------------------------------------------------------


class TestGitRemoteHttps:
    def test_bitbucket_https(self):
        result = _git_remote_to_browse_base("https://bitbucket.org/acme/repo.git", "main")
        assert result == "https://bitbucket.org/acme/repo/src/main/"

    def test_github_https(self):
        result = _git_remote_to_browse_base("https://github.com/user/repo.git", "main")
        assert result == "https://github.com/user/repo/blob/main/"

    def test_gitlab_https(self):
        result = _git_remote_to_browse_base("https://gitlab.com/org/repo.git", "main")
        assert result == "https://gitlab.com/org/repo/-/blob/main/"

    def test_https_without_git_suffix(self):
        result = _git_remote_to_browse_base("https://github.com/user/repo", "main")
        assert result == "https://github.com/user/repo/blob/main/"

    def test_unknown_host_uses_blob(self):
        result = _git_remote_to_browse_base("https://custom.host/org/repo.git", "main")
        assert result == "https://custom.host/org/repo/blob/main/"


# ---------------------------------------------------------------------------
# _git_remote_to_browse_base — edge cases
# ---------------------------------------------------------------------------


class TestGitRemoteEdgeCases:
    def test_empty_string(self):
        assert _git_remote_to_browse_base("", "main") is None

    def test_whitespace_only(self):
        assert _git_remote_to_browse_base("   ", "main") is None

    def test_malformed_url(self):
        result = _git_remote_to_browse_base("not-a-url", "main")
        # Should return None since there's no host
        assert result is None


# ---------------------------------------------------------------------------
# rewrite_links_to_git
# ---------------------------------------------------------------------------


class TestRewriteLinksToGit:
    def test_relative_path(self):
        config = _make_config("git@github.com:user/repo.git")
        result = rewrite_links_to_git("[doc](path/to/file.md)", config)
        assert "https://github.com/user/repo/blob/main/path/to/file.md" in result

    def test_dot_slash_stripped(self):
        config = _make_config("git@github.com:user/repo.git")
        result = rewrite_links_to_git("[doc](./file.md)", config)
        assert "https://github.com/user/repo/blob/main/file.md" in result
        assert "./" not in result

    def test_double_dot_slash_preserved(self):
        config = _make_config("git@github.com:user/repo.git")
        result = rewrite_links_to_git("[doc](../other/file.md)", config)
        assert "../other/file.md" in result or "https://" in result

    def test_absolute_url_not_rewritten(self):
        config = _make_config("git@github.com:user/repo.git")
        original = "[link](https://example.com)"
        result = rewrite_links_to_git(original, config)
        assert result == original

    def test_anchor_not_rewritten(self):
        config = _make_config("git@github.com:user/repo.git")
        original = "[section](#heading)"
        result = rewrite_links_to_git(original, config)
        assert result == original

    def test_mailto_not_rewritten(self):
        config = _make_config("git@github.com:user/repo.git")
        original = "[email](mailto:user@example.com)"
        result = rewrite_links_to_git(original, config)
        assert result == original

    def test_multiple_links(self):
        config = _make_config("git@github.com:user/repo.git")
        text = "[a](a.md) and [b](b.md)"
        result = rewrite_links_to_git(text, config)
        assert "https://github.com/user/repo/blob/main/a.md" in result
        assert "https://github.com/user/repo/blob/main/b.md" in result

    def test_no_remote_returns_unchanged(self):
        config = _make_config(None)
        text = "[doc](file.md)"
        assert rewrite_links_to_git(text, config) == text

    def test_empty_text(self):
        config = _make_config("git@github.com:user/repo.git")
        assert rewrite_links_to_git("", config) == ""

    def test_bitbucket_uses_src(self):
        config = _make_config("git@bitbucket.org:org/repo.git")
        result = rewrite_links_to_git("[doc](file.md)", config)
        assert "/src/main/" in result


# ---------------------------------------------------------------------------
# rewrite_links_to_local
# ---------------------------------------------------------------------------


class TestRewriteLinksToLocal:
    def test_git_url_to_relative(self):
        config = _make_config("git@github.com:user/repo.git")
        text = "[doc](https://github.com/user/repo/blob/main/path/file.md)"
        result = rewrite_links_to_local(text, config)
        assert result == "[doc](path/file.md)"

    def test_different_host_not_rewritten(self):
        config = _make_config("git@github.com:user/repo.git")
        text = "[doc](https://other.com/user/repo/blob/main/file.md)"
        result = rewrite_links_to_local(text, config)
        assert "https://other.com" in result

    def test_different_repo_not_rewritten(self):
        config = _make_config("git@github.com:user/repo.git")
        text = "[doc](https://github.com/other/project/blob/main/file.md)"
        result = rewrite_links_to_local(text, config)
        assert "https://github.com/other/project" in result

    def test_no_remote_returns_unchanged(self):
        config = _make_config(None)
        text = "[doc](https://github.com/user/repo/blob/main/file.md)"
        assert rewrite_links_to_local(text, config) == text

    def test_empty_text(self):
        config = _make_config("git@github.com:user/repo.git")
        assert rewrite_links_to_local("", config) == ""


# ---------------------------------------------------------------------------
# Roundtrip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_github_roundtrip(self):
        config = _make_config("git@github.com:user/repo.git")
        original = "[doc](path/file.md) and [ext](https://example.com)"
        rewritten = rewrite_links_to_git(original, config)
        restored = rewrite_links_to_local(rewritten, config)
        assert "[doc](path/file.md)" in restored
        assert "[ext](https://example.com)" in restored

    def test_bitbucket_roundtrip(self):
        config = _make_config("git@bitbucket.org:org/repo.git")
        original = "[readme](README.md)"
        rewritten = rewrite_links_to_git(original, config)
        restored = rewrite_links_to_local(rewritten, config)
        assert restored == "[readme](README.md)"


if __name__ == "__main__":
    import subprocess

    sys.exit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
