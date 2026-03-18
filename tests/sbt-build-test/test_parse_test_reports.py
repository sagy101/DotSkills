"""Tests for sbt-build-test parse_test_reports.sh — JUnit XML parsing + SBT log cross-reference."""

import os
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "sbt-build-test" / "scripts"
PARSE_SCRIPT = SCRIPT_DIR / "parse_test_reports.sh"


def _write_xml(
    report_dir: Path, suite_name: str, tests: int, failures: int, errors: int = 0
) -> None:
    """Write a minimal JUnit XML file."""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="{suite_name}" tests="{tests}" failures="{failures}" errors="{errors}" skipped="0" time="1.5">
"""
    for i in range(tests - failures - errors):
        xml += f'  <testcase classname="{suite_name}" name="test{i}" time="0.1"/>\n'
    for i in range(failures):
        xml += f"""  <testcase classname="{suite_name}" name="failTest{i}" time="0.1">
    <failure message="expected true but was false">assertion failed</failure>
  </testcase>
"""
    for i in range(errors):
        xml += f"""  <testcase classname="{suite_name}" name="errorTest{i}" time="0.1">
    <error message="ClassCastException: cannot cast Foo to Bar">java.lang.ClassCastException</error>
  </testcase>
"""
    xml += "</testsuite>\n"
    (report_dir / f"TEST-{suite_name}.xml").write_text(xml)


def _run_parse(target_dir: str, verbose: str = "") -> tuple[str, int]:
    """Run parse_test_reports.sh and return (stdout+stderr, exit_code)."""
    args = ["bash", str(PARSE_SCRIPT), target_dir]
    if verbose:
        args.append(verbose)
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    return result.stdout + result.stderr, result.returncode


class TestAllXmlPass:
    def test_all_pass(self, tmp_path: Path) -> None:
        report_dir = tmp_path / "target" / "test-reports"
        report_dir.mkdir(parents=True)
        _write_xml(report_dir, "com.example.FooTest", tests=5, failures=0)
        _write_xml(report_dir, "com.example.BarTest", tests=3, failures=0)

        output, rc = _run_parse(str(tmp_path / "target"))
        assert rc == 0
        assert "ALL PASSED" in output
        assert "Tests:    8" in output


class TestXmlWithFailures:
    def test_failures_shown(self, tmp_path: Path) -> None:
        report_dir = tmp_path / "target" / "test-reports"
        report_dir.mkdir(parents=True)
        _write_xml(report_dir, "com.example.PassTest", tests=5, failures=0)
        _write_xml(report_dir, "com.example.FailTest", tests=3, failures=2)

        output, rc = _run_parse(str(tmp_path / "target"))
        assert rc == 1
        assert "RESULT: FAILED" in output
        assert "com.example.FailTest" in output
        assert "expected true but was false" in output
        # Top Failures section
        assert "Top Failures" in output


class TestSbtLogCrossReference:
    def test_sbt_log_reports_failure_but_no_xml(self, tmp_path: Path) -> None:
        """SBT log says a suite failed but no XML was produced → CRASHED."""
        # Set up cache root with a log file
        cache_root = tmp_path / ".sbt-build-cache"
        log_dir = cache_root / "logs"
        log_dir.mkdir(parents=True)

        # Create a build.sbt so repo root detection works
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        (project_dir / "build.sbt").write_text('name := "myproject"\n')

        report_dir = project_dir / "target" / "test-reports"
        report_dir.mkdir(parents=True)
        # Only one suite has XML
        _write_xml(report_dir, "com.example.PassTest", tests=3, failures=0)

        # Create SBT log that reports a crashed suite
        sanitized = str(project_dir).replace("/", "_")
        log_file = log_dir / f"{sanitized}.sbt.20260319-120000.log"
        log_file.write_text(
            "[info] Done compiling.\n"
            "[error] Failed tests:\n"
            "[error]   com.example.CrashedTest\n"
            "[info] Done.\n"
        )

        env = dict(os.environ, SBT_BUILD_CACHE_ROOT=str(cache_root))
        result = subprocess.run(
            ["bash", str(PARSE_SCRIPT), str(project_dir / "target")],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        output = result.stdout + result.stderr
        assert result.returncode == 1
        assert "CRASH" in output
        assert "com.example.CrashedTest" in output
        assert "RESULT: FAILED" in output

    def test_sbt_log_matches_xml(self, tmp_path: Path) -> None:
        """SBT log says failed, XML confirms → normal FAILED (not CRASHED)."""
        cache_root = tmp_path / ".sbt-build-cache"
        log_dir = cache_root / "logs"
        log_dir.mkdir(parents=True)

        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        (project_dir / "build.sbt").write_text('name := "myproject"\n')

        report_dir = project_dir / "target" / "test-reports"
        report_dir.mkdir(parents=True)
        _write_xml(report_dir, "com.example.FailTest", tests=3, failures=1)

        sanitized = str(project_dir).replace("/", "_")
        log_file = log_dir / f"{sanitized}.sbt.20260319-120000.log"
        log_file.write_text("[error] Failed tests:\n[error]   com.example.FailTest\n")

        env = dict(os.environ, SBT_BUILD_CACHE_ROOT=str(cache_root))
        result = subprocess.run(
            ["bash", str(PARSE_SCRIPT), str(project_dir / "target")],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        output = result.stdout + result.stderr
        assert result.returncode == 1
        assert "CRASH" not in output
        assert "FAIL" in output


class TestNoXmlNoLog:
    def test_no_reports_found(self, tmp_path: Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        # No test-reports dir at all
        output, rc = _run_parse(str(target))
        assert rc == 2
        assert "No test-reports" in output
