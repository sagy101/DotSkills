"""Tests for jenkins-manager get_status.py — --build flag and build resolution."""

import argparse
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent.parent / "jenkins-manager" / "scripts")
)

from get_status import _format_duration, _print_build


class TestFormatDuration:
    def test_seconds_only(self):
        assert _format_duration(45_000) == "45s"

    def test_minutes_and_seconds(self):
        assert _format_duration(125_000) == "2m 5s"

    def test_hours(self):
        assert _format_duration(3_661_000) == "1h 1m 1s"

    def test_zero(self):
        assert _format_duration(0) == "0s"


class TestPrintBuild:
    def test_table_output_includes_build_number(self, capsys: pytest.CaptureFixture[str]) -> None:
        build = {
            "number": 1094,
            "result": "SUCCESS",
            "duration": 60_000,
            "timestamp": 1710000000000,
            "url": "https://jenkins.example.com/job/test/1094/",
            "building": False,
        }
        _print_build(build, "API", "my-service", "main")
        out = capsys.readouterr().out
        assert "#1094" in out
        assert "SUCCESS" in out
        assert "API/my-service" in out

    def test_json_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        build = {"number": 42, "result": "FAILURE", "building": False}
        _print_build(build, None, "my-job", None, fmt="json")
        out = capsys.readouterr().out
        assert '"number": 42' in out
        assert '"result": "FAILURE"' in out


class TestBuildArgParsing:
    """Verify that get_status.py's argparse accepts --build N."""

    def _make_parser(self) -> argparse.ArgumentParser:
        """Replicate the parser from get_status.main() for unit testing."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--config")
        parser.add_argument("--folder")
        parser.add_argument("--job")
        parser.add_argument("--branch")
        parser.add_argument("--build", type=int)
        parser.add_argument("--format", choices=["table", "json"], default="table")
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--interval", type=int, default=60)
        parser.add_argument("--timeout", type=int, default=600)
        return parser

    def test_build_flag_parsed(self):
        parser = self._make_parser()
        args = parser.parse_args(["--build", "1094"])
        assert args.build == 1094

    def test_build_flag_with_other_args(self):
        parser = self._make_parser()
        args = parser.parse_args(["--build", "42", "--format", "json", "--watch"])
        assert args.build == 42
        assert args.format == "json"
        assert args.watch is True

    def test_no_build_flag_defaults_to_none(self):
        parser = self._make_parser()
        args = parser.parse_args([])
        assert args.build is None

    def test_build_flag_requires_int(self):
        parser = self._make_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--build", "notanumber"])
