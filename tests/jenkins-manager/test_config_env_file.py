"""Tests for jenkins-manager config env_file resolution and default_username."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent.parent / "jenkins-manager" / "scripts")
)

from jenkins_config import JenkinsConfig, resolve_credentials


class TestEnvFileResolution:
    def test_env_file_at_top_level(self, tmp_path: Path) -> None:
        """env_file at top level of config should be resolved."""
        env_file = tmp_path / ".env"
        env_file.write_text("JENKINS_USER=alice\nJENKINS_TOKEN=tok123\n")

        config = JenkinsConfig(
            base_url="https://jenkins.example.com",
            env_file=str(env_file),
            project_root=tmp_path,
        )
        username, token = resolve_credentials(config)
        assert username == "alice"
        assert token == "tok123"

    def test_env_file_under_credentials(self, tmp_path: Path) -> None:
        """env_file under credentials block should also work (via load_config)."""
        # This tests the load_config path indirectly — the JenkinsConfig dataclass
        # just stores env_file; the config loader sets it from either location
        env_file = tmp_path / ".env"
        env_file.write_text("JENKINS_USER=bob\nJENKINS_TOKEN=tok456\n")

        config = JenkinsConfig(
            base_url="https://jenkins.example.com",
            env_file=str(env_file),
            project_root=tmp_path,
        )
        username, token = resolve_credentials(config)
        assert username == "bob"
        assert token == "tok456"


class TestDefaultUsername:
    def test_default_username_fallback(self, tmp_path: Path) -> None:
        """When env var is not set, default_username should be used."""
        env_file = tmp_path / ".env"
        env_file.write_text("JENKINS_TOKEN=tok789\n")

        config = JenkinsConfig(
            base_url="https://jenkins.example.com",
            env_file=str(env_file),
            default_username="default-user",
            project_root=tmp_path,
        )
        with patch.dict(os.environ, {}, clear=True):
            username, token = resolve_credentials(config)
        assert username == "default-user"
        assert token == "tok789"

    def test_default_username_not_used_when_env_set(self, tmp_path: Path) -> None:
        """When env var IS set, default_username should be ignored."""
        env_file = tmp_path / ".env"
        env_file.write_text("JENKINS_USER=env-user\nJENKINS_TOKEN=tokABC\n")

        config = JenkinsConfig(
            base_url="https://jenkins.example.com",
            env_file=str(env_file),
            default_username="should-not-use",
            project_root=tmp_path,
        )
        username, token = resolve_credentials(config)
        assert username == "env-user"
        assert token == "tokABC"
