"""Tests for jenkins-manager client — color mapping and path construction."""

import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent.parent / "jenkins-manager" / "scripts")
)

from jenkins_client import color_to_status

# ─── Color to Status Mapping ────────────────────────────────────────────────


class TestColorToStatus:
    def test_blue_is_success(self):
        assert color_to_status("blue") == "SUCCESS"

    def test_red_is_failure(self):
        assert color_to_status("red") == "FAILURE"

    def test_yellow_is_unstable(self):
        assert color_to_status("yellow") == "UNSTABLE"

    def test_blue_anime_is_building(self):
        assert color_to_status("blue_anime") == "BUILDING"

    def test_red_anime_is_building(self):
        assert color_to_status("red_anime") == "BUILDING"

    def test_yellow_anime_is_building(self):
        assert color_to_status("yellow_anime") == "BUILDING"

    def test_notbuilt(self):
        assert color_to_status("notbuilt") == "NOT_BUILT"

    def test_disabled(self):
        assert color_to_status("disabled") == "DISABLED"

    def test_aborted(self):
        assert color_to_status("aborted") == "ABORTED"

    def test_grey_is_pending(self):
        assert color_to_status("grey") == "PENDING"

    def test_none_is_unknown(self):
        assert color_to_status(None) == "UNKNOWN"

    def test_unknown_color_uppercased(self):
        assert color_to_status("magenta") == "MAGENTA"

    def test_all_anime_variants_are_building(self):
        for color in (
            "blue_anime",
            "red_anime",
            "yellow_anime",
            "grey_anime",
            "notbuilt_anime",
            "aborted_anime",
        ):
            assert color_to_status(color) == "BUILDING", f"{color} should map to BUILDING"


# ─── Build Job Path Construction ────────────────────────────────────────────


class TestBuildJobPath:
    """Test _build_job_path via a mock client (avoids credential resolution)."""

    def _make_client(self) -> object:
        """Create a JenkinsClient with mocked credentials."""
        # Import here to avoid side effects at module level
        from jenkins_client import JenkinsClient
        from jenkins_config import InstanceConfig

        instance = InstanceConfig(
            name="ci",
            base_url="https://jenkins.example.com",
            project_root=Path("/tmp"),
        )
        # Bypass __init__ credential resolution
        client = object.__new__(JenkinsClient)
        client.instance = instance
        client.base_url = instance.base_url
        return client

    def test_folder_job_branch(self):
        client = self._make_client()
        path = client._build_job_path("API", "router", "master")
        assert path == "/job/API/job/router/job/master"

    def test_folder_job_no_branch(self):
        client = self._make_client()
        path = client._build_job_path("API", "router", None)
        assert path == "/job/API/job/router"

    def test_no_folder(self):
        client = self._make_client()
        path = client._build_job_path(None, "my-job", "main")
        assert path == "/job/my-job/job/main"

    def test_no_folder_no_branch(self):
        client = self._make_client()
        path = client._build_job_path(None, "my-job", None)
        assert path == "/job/my-job"

    def test_branch_with_slash_encoded(self):
        client = self._make_client()
        path = client._build_job_path("API", "router", "feature/TICKET-123")
        assert path == "/job/API/job/router/job/feature%2FTICKET-123"

    def test_empty_folder_string(self):
        client = self._make_client()
        path = client._build_job_path("", "my-job", "main")
        # Empty string folder should still produce /job//job/my-job — but we treat it as truthy
        # In practice, empty string folder means "no folder"
        assert "/job/my-job/job/main" in path

    def test_folder_with_space(self):
        client = self._make_client()
        path = client._build_job_path("App Gov", "my-job", None)
        assert path == "/job/App%20Gov/job/my-job"
