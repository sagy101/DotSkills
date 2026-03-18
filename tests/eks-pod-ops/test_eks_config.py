"""Tests for eks-pod-ops config loading and environment resolution."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "eks-pod-ops" / "scripts"))

import pytest
from lib.config import get_env_config, get_kubeconfig_path

SAMPLE_CONFIG = {
    "environments": {
        "dev": {
            "profile": "dev",
            "cluster": "eks01-dev",
            "sso_session": "lab",
            "namespace": "default",
        },
        "stg": {
            "profile": "stg",
            "cluster": "eks01-stg",
            "sso_session": "lab",
            "namespace": "staging",
        },
        "us1": {
            "profile": "us1",
            "cluster": "eks01-us1",
            "sso_session": "prod",
            "namespace": "default",
            "alias": "production",
        },
    },
    "kubeconfig_dir": "~/.kube",
    "kubeconfig_pattern": "config_{env}",
}


class TestGetEnvConfig:
    def test_direct_name(self):
        cfg = get_env_config(SAMPLE_CONFIG, "dev")
        assert cfg["profile"] == "dev"
        assert cfg["cluster"] == "eks01-dev"

    def test_alias_resolution(self):
        cfg = get_env_config(SAMPLE_CONFIG, "production")
        assert cfg["profile"] == "us1"

    def test_unknown_env_exits(self):
        with pytest.raises(SystemExit):
            get_env_config(SAMPLE_CONFIG, "nonexistent")

    def test_namespace_returned(self):
        cfg = get_env_config(SAMPLE_CONFIG, "stg")
        assert cfg["namespace"] == "staging"

    def test_sso_session(self):
        cfg = get_env_config(SAMPLE_CONFIG, "us1")
        assert cfg["sso_session"] == "prod"


class TestGetKubeconfigPath:
    def test_default_pattern(self):
        path = get_kubeconfig_path(SAMPLE_CONFIG, "dev")
        assert path.endswith("/.kube/config_dev")

    def test_custom_pattern(self):
        config = {**SAMPLE_CONFIG, "kubeconfig_pattern": "kubeconfig-{env}.yaml"}
        path = get_kubeconfig_path(config, "stg")
        assert path.endswith("/.kube/kubeconfig-stg.yaml")

    def test_custom_dir(self):
        config = {**SAMPLE_CONFIG, "kubeconfig_dir": "/tmp/kube"}
        path = get_kubeconfig_path(config, "dev")
        assert path == "/tmp/kube/config_dev"

    def test_default_values(self):
        config = {"environments": {"dev": {}}}
        path = get_kubeconfig_path(config, "dev")
        assert "/.kube/config_dev" in path
