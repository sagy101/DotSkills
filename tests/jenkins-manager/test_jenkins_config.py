"""Tests for jenkins-manager config loading, repo detection, and branch encoding."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent.parent / "jenkins-manager" / "scripts")
)

from jenkins_config import (
    InstanceConfig,
    JenkinsConfig,
    _deep_merge,
    _parse_repo_name,
    load_config,
    resolve_branch,
    resolve_instance,
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


# ─── Instance Resolution ────────────────────────────────────────────────────


def _make_instance(
    name: str = "ci",
    base_url: str = "https://jenkins.example.com",
    description: str = "",
    job_cache: dict[str, str] | None = None,
    default_branch: str | None = None,
    project_root: Path | None = None,
) -> InstanceConfig:
    return InstanceConfig(
        name=name,
        base_url=base_url,
        description=description,
        job_cache=job_cache or {},
        default_branch=default_branch,
        project_root=project_root or Path("/tmp"),
    )


def _make_config(instances: dict[str, InstanceConfig], default: str | None = None) -> JenkinsConfig:
    return JenkinsConfig(instances=instances, default_instance=default)


class TestResolveInstance:
    def test_cli_flag_selects_instance(self):
        ci = _make_instance("ci")
        cd = _make_instance("cd")
        config = _make_config({"ci": ci, "cd": cd}, default="ci")
        assert resolve_instance(config, "cd") is cd

    def test_default_instance_used(self):
        ci = _make_instance("ci")
        cd = _make_instance("cd")
        config = _make_config({"ci": ci, "cd": cd}, default="ci")
        assert resolve_instance(config, None) is ci

    def test_single_instance_auto_selected(self):
        ci = _make_instance("ci")
        config = _make_config({"ci": ci})
        assert resolve_instance(config, None) is ci

    def test_env_var_selects_instance(self):
        ci = _make_instance("ci")
        cd = _make_instance("cd")
        config = _make_config({"ci": ci, "cd": cd})
        with patch.dict("os.environ", {"JENKINS_INSTANCE": "cd"}):
            assert resolve_instance(config, None) is cd

    def test_missing_instance_exits(self):
        ci = _make_instance("ci")
        config = _make_config({"ci": ci})
        try:
            resolve_instance(config, "nonexistent")
            raise AssertionError("Should have exited")
        except SystemExit as e:
            assert e.code == 2

    def test_no_default_multiple_exits(self):
        ci = _make_instance("ci")
        cd = _make_instance("cd")
        config = _make_config({"ci": ci, "cd": cd})
        try:
            resolve_instance(config, None)
            raise AssertionError("Should have exited")
        except SystemExit as e:
            assert e.code == 2


# ─── Config Loading ─────────────────────────────────────────────────────────


class TestLoadConfig:
    def test_load_instances_config(self, tmp_path: Path) -> None:
        config_data = {
            "instances": {
                "ci": {
                    "base_url": "https://ci.example.com",
                    "description": "CI server",
                    "credentials": {
                        "username_env": "CI_USER",
                        "token_env": "CI_TOKEN",
                    },
                },
                "cd": {
                    "base_url": "https://cd.example.com",
                    "credentials": {
                        "token_env": "CD_TOKEN",
                    },
                },
            },
            "default_instance": "ci",
            "env_file": "/tmp/.env",
        }
        config_file = tmp_path / ".jenkins.json"
        config_file.write_text(json.dumps(config_data))

        config = load_config(str(config_file))
        assert len(config.instances) == 2
        assert config.default_instance == "ci"
        assert config.instances["ci"].base_url == "https://ci.example.com"
        assert config.instances["ci"].description == "CI server"
        assert config.instances["ci"].username_env == "CI_USER"
        assert config.instances["ci"].token_env == "CI_TOKEN"
        assert config.instances["cd"].base_url == "https://cd.example.com"
        assert config.instances["cd"].token_env == "CD_TOKEN"
        assert config.instances["cd"].env_file == "/tmp/.env"  # inherited from top-level

    def test_missing_instances_exits(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".jenkins.json"
        config_file.write_text(json.dumps({"base_url": "https://old.example.com"}))
        try:
            load_config(str(config_file))
            raise AssertionError("Should have exited")
        except SystemExit as e:
            assert e.code == 2

    def test_missing_base_url_in_instance_exits(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".jenkins.json"
        config_file.write_text(json.dumps({"instances": {"ci": {"description": "no url"}}}))
        try:
            load_config(str(config_file))
            raise AssertionError("Should have exited")
        except SystemExit as e:
            assert e.code == 2


# ─── Job Path Resolution ────────────────────────────────────────────────────


class TestResolveJobPath:
    def _instance(self, job_cache: dict[str, str] | None = None) -> InstanceConfig:
        return _make_instance("ci", job_cache=job_cache or {})

    def test_cli_flags_override(self):
        instance = self._instance({"my-repo": "Cached/my-repo"})
        folder, job = resolve_job_path(instance, "CLI-Folder", "cli-job")
        assert folder == "CLI-Folder"
        assert job == "cli-job"

    def test_job_cache_hit(self):
        instance = self._instance({"my-repo": "API/my-repo"})
        with patch("jenkins_config.detect_repo_name", return_value="my-repo"):
            folder, job = resolve_job_path(instance, None, None)
        assert folder == "API"
        assert job == "my-repo"

    def test_job_cache_miss_returns_repo_name(self):
        instance = self._instance({})
        with patch("jenkins_config.detect_repo_name", return_value="unknown-repo"):
            folder, job = resolve_job_path(instance, None, None)
        assert folder is None
        assert job == "unknown-repo"

    def test_cli_folder_with_cache_job(self):
        instance = self._instance({"my-repo": "Cached/my-repo"})
        with patch("jenkins_config.detect_repo_name", return_value="my-repo"):
            folder, job = resolve_job_path(instance, "Override", None)
        assert folder == "Override"
        assert job == "my-repo"

    def test_no_repo_detected(self):
        instance = self._instance({})
        with patch("jenkins_config.detect_repo_name", return_value=None):
            folder, job = resolve_job_path(instance, None, None)
        assert folder is None
        assert job is None


# ─── Branch Resolution ───────────────────────────────────────────────────────


class TestResolveBranch:
    def _instance(self, default_branch: str | None = None) -> InstanceConfig:
        return _make_instance("ci", default_branch=default_branch)

    def test_cli_flag_wins(self):
        instance = self._instance("main")
        assert resolve_branch(instance, "feature/x") == "feature/x"

    def test_git_branch_detected(self):
        instance = self._instance("main")
        with patch("jenkins_config.detect_current_branch", return_value="develop"):
            assert resolve_branch(instance, None) == "develop"

    def test_config_default_fallback(self):
        instance = self._instance("main")
        with patch("jenkins_config.detect_current_branch", return_value=None):
            assert resolve_branch(instance, None) == "main"

    def test_no_branch_anywhere(self):
        instance = self._instance(None)
        with patch("jenkins_config.detect_current_branch", return_value=None):
            assert resolve_branch(instance, None) is None
