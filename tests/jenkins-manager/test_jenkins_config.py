"""Tests for jenkins-manager config loading, repo detection, and branch encoding."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent.parent / "jenkins-manager" / "scripts")
)

from jenkins_config import (
    JenkinsConfig,
    _deep_merge,
    _parse_repo_name,
    resolve_branch,
    resolve_job_path,
    url_encode_branch,
)

# ─── Repo Name Parsing ──────────────────────────────────────────────────────


class TestParseRepoName:
    def test_ssh_bitbucket(self):
        assert _parse_repo_name("git@bitbucket.org:workspace/my-repo.git") == "my-repo"

    def test_ssh_github(self):
        assert _parse_repo_name("git@github.com:org/my-repo.git") == "my-repo"

    def test_ssh_gitlab(self):
        assert _parse_repo_name("git@gitlab.com:group/subgroup/my-repo.git") == "my-repo"

    def test_https_bitbucket(self):
        assert _parse_repo_name("https://bitbucket.org/workspace/my-repo.git") == "my-repo"

    def test_https_github(self):
        assert _parse_repo_name("https://github.com/org/my-repo.git") == "my-repo"

    def test_https_no_git_suffix(self):
        assert _parse_repo_name("https://github.com/org/my-repo") == "my-repo"

    def test_ssh_scheme_url(self):
        assert _parse_repo_name("ssh://git@host.com/org/my-repo.git") == "my-repo"

    def test_trailing_slash(self):
        assert _parse_repo_name("https://github.com/org/my-repo/") == "my-repo"

    def test_corporate_host(self):
        assert _parse_repo_name("git@git.corp.example.com:team/service-api.git") == "service-api"

    def test_deeply_nested_path(self):
        assert _parse_repo_name("git@gitlab.com:a/b/c/deep-repo.git") == "deep-repo"


# ─── Branch URL Encoding ────────────────────────────────────────────────────


class TestUrlEncodeBranch:
    def test_simple_branch(self):
        assert url_encode_branch("master") == "master"

    def test_feature_slash(self):
        assert url_encode_branch("feature/TICKET-123") == "feature%2FTICKET-123"

    def test_multiple_slashes(self):
        assert url_encode_branch("feature/team/thing") == "feature%2Fteam%2Fthing"

    def test_special_chars(self):
        encoded = url_encode_branch("release/v1.0+hotfix")
        assert "/" not in encoded
        assert "+" not in encoded

    def test_already_simple(self):
        assert url_encode_branch("develop") == "develop"


# ─── Deep Merge ─────────────────────────────────────────────────────────────


class TestDeepMerge:
    def test_flat_override(self):
        result = _deep_merge({"a": 1}, {"a": 2})
        assert result == {"a": 2}

    def test_nested_merge(self):
        base = {"credentials": {"username_env": "A", "token_env": "B"}}
        override = {"credentials": {"token_env": "C"}}
        result = _deep_merge(base, override)
        assert result == {"credentials": {"username_env": "A", "token_env": "C"}}

    def test_new_keys_added(self):
        result = _deep_merge({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_override_replaces_non_dict(self):
        result = _deep_merge({"a": {"x": 1}}, {"a": "flat"})
        assert result == {"a": "flat"}

    def test_empty_base(self):
        result = _deep_merge({}, {"a": 1})
        assert result == {"a": 1}

    def test_empty_override(self):
        result = _deep_merge({"a": 1}, {})
        assert result == {"a": 1}


# ─── Job Path Resolution ────────────────────────────────────────────────────


class TestResolveJobPath:
    def _config(self, job_cache: dict[str, str] | None = None) -> JenkinsConfig:
        return JenkinsConfig(
            base_url="https://jenkins.example.com",
            job_cache=job_cache or {},
            project_root=Path("/tmp"),
        )

    def test_cli_flags_override(self):
        config = self._config({"my-repo": "Cached/my-repo"})
        folder, job = resolve_job_path(config, "CLI-Folder", "cli-job")
        assert folder == "CLI-Folder"
        assert job == "cli-job"

    def test_job_cache_hit(self):
        config = self._config({"my-repo": "API/my-repo"})
        with patch("jenkins_config.detect_repo_name", return_value="my-repo"):
            folder, job = resolve_job_path(config, None, None)
        assert folder == "API"
        assert job == "my-repo"

    def test_job_cache_miss_returns_repo_name(self):
        config = self._config({})
        with patch("jenkins_config.detect_repo_name", return_value="unknown-repo"):
            folder, job = resolve_job_path(config, None, None)
        assert folder is None
        assert job == "unknown-repo"

    def test_cli_folder_with_cache_job(self):
        config = self._config({"my-repo": "Cached/my-repo"})
        with patch("jenkins_config.detect_repo_name", return_value="my-repo"):
            folder, job = resolve_job_path(config, "Override", None)
        assert folder == "Override"
        assert job == "my-repo"

    def test_no_repo_detected(self):
        config = self._config({})
        with patch("jenkins_config.detect_repo_name", return_value=None):
            folder, job = resolve_job_path(config, None, None)
        assert folder is None
        assert job is None


# ─── Branch Resolution ───────────────────────────────────────────────────────


class TestResolveBranch:
    def _config(self, default_branch: str | None = None) -> JenkinsConfig:
        return JenkinsConfig(
            base_url="https://jenkins.example.com",
            default_branch=default_branch,
            project_root=Path("/tmp"),
        )

    def test_cli_flag_wins(self):
        config = self._config("main")
        assert resolve_branch(config, "feature/x") == "feature/x"

    def test_git_branch_detected(self):
        config = self._config("main")
        with patch("jenkins_config.detect_current_branch", return_value="develop"):
            assert resolve_branch(config, None) == "develop"

    def test_config_default_fallback(self):
        config = self._config("main")
        with patch("jenkins_config.detect_current_branch", return_value=None):
            assert resolve_branch(config, None) == "main"

    def test_no_branch_anywhere(self):
        config = self._config(None)
        with patch("jenkins_config.detect_current_branch", return_value=None):
            assert resolve_branch(config, None) is None
