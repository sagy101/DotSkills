"""Tests for eks-pod-ops pod resolution and container selection."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "eks-pod-ops" / "scripts"))

from lib.pods import KNOWN_SIDECARS, _parse_pod, pick_app_container


class TestPickAppContainer:
    def test_exact_match(self):
        assert pick_app_container(["my-service", "statsite"], "my-service") == "my-service"

    def test_skip_sidecar(self):
        assert pick_app_container(["istio-proxy", "my-app"], "my-app") == "my-app"

    def test_skip_multiple_sidecars(self):
        result = pick_app_container(["envoy", "statsite", "my-app"], "my-app")
        assert result == "my-app"

    def test_no_exact_match_picks_first_non_sidecar(self):
        result = pick_app_container(["main-container", "statsite"], "some-service")
        assert result == "main-container"

    def test_all_sidecars_picks_first(self):
        result = pick_app_container(["istio-proxy", "envoy"], "my-service")
        assert result == "istio-proxy"

    def test_empty_containers(self):
        assert pick_app_container([], "my-service") == ""

    def test_single_container(self):
        assert pick_app_container(["my-service"], "my-service") == "my-service"

    def test_all_known_sidecars_are_skipped(self):
        for sidecar in KNOWN_SIDECARS:
            result = pick_app_container([sidecar, "app"], "app")
            assert result == "app", f"Sidecar '{sidecar}' was not skipped"


class TestParsePod:
    def test_basic_pod(self):
        item = {
            "metadata": {"name": "my-service-abc123"},
            "spec": {"containers": [{"name": "my-service"}, {"name": "statsite"}]},
            "status": {
                "phase": "Running",
                "containerStatuses": [
                    {"name": "my-service", "ready": True, "restartCount": 0},
                    {"name": "statsite", "ready": True, "restartCount": 0},
                ],
            },
        }
        pod = _parse_pod(item)
        assert pod["name"] == "my-service-abc123"
        assert pod["status"] == "Running"
        assert pod["containers"] == ["my-service", "statsite"]
        assert pod["ready"] == "2/2"
        assert pod["restarts"] == 0

    def test_crashed_pod(self):
        item = {
            "metadata": {"name": "my-service-xyz"},
            "spec": {"containers": [{"name": "my-service"}]},
            "status": {
                "phase": "CrashLoopBackOff",
                "containerStatuses": [
                    {"name": "my-service", "ready": False, "restartCount": 15},
                ],
            },
        }
        pod = _parse_pod(item)
        assert pod["status"] == "CrashLoopBackOff"
        assert pod["ready"] == "0/1"
        assert pod["restarts"] == 15

    def test_missing_status(self):
        item = {
            "metadata": {"name": "my-service-pending"},
            "spec": {"containers": [{"name": "my-service"}]},
            "status": {},
        }
        pod = _parse_pod(item)
        assert pod["status"] == "Unknown"
        assert pod["ready"] == "0/1"
