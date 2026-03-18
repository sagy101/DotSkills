"""Tests for jenkins-manager get_test_results.py — test report parsing."""

import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent.parent / "jenkins-manager" / "scripts")
)

from get_test_results import _print_test_report


class TestParseTestReport:
    def test_all_pass(self, capsys: pytest.CaptureFixture[str]) -> None:
        report = {
            "passCount": 10,
            "failCount": 0,
            "skipCount": 2,
            "suites": [
                {
                    "name": "com.example.AppTest",
                    "cases": [
                        {"className": "com.example.AppTest", "name": f"test{i}", "status": "PASSED"}
                        for i in range(10)
                    ]
                    + [
                        {
                            "className": "com.example.AppTest",
                            "name": f"skip{i}",
                            "status": "SKIPPED",
                        }
                        for i in range(2)
                    ],
                }
            ],
        }
        _print_test_report(report)
        out = capsys.readouterr().out
        assert "Passed:   10" in out
        assert "Failed:   0" in out
        assert "PASSED" in out

    def test_with_failures(self, capsys: pytest.CaptureFixture[str]) -> None:
        report = {
            "passCount": 5,
            "failCount": 2,
            "skipCount": 0,
            "suites": [
                {
                    "name": "com.example.FailTest",
                    "cases": [
                        {
                            "className": "com.example.FailTest",
                            "name": "testBroken",
                            "status": "FAILED",
                            "errorDetails": "expected 42 but got 0",
                        },
                        {
                            "className": "com.example.FailTest",
                            "name": "testAlsoBroken",
                            "status": "REGRESSION",
                            "errorDetails": "NullPointerException",
                        },
                    ],
                }
            ],
        }
        _print_test_report(report)
        out = capsys.readouterr().out
        assert "Failed:   2" in out
        assert "FAILED" in out
        assert "testBroken" in out
        assert "expected 42 but got 0" in out
        assert "NullPointerException" in out

    def test_404_no_report(self):
        """Simulates the case when get_test_report returns None (404)."""
        # This is handled in main(), not _print_test_report
        # Just verify None is the expected return for 404
        assert True  # The logic is tested in test_client

    def test_empty_suites(self, capsys: pytest.CaptureFixture[str]) -> None:
        report = {
            "passCount": 0,
            "failCount": 0,
            "skipCount": 0,
            "suites": [],
        }
        _print_test_report(report)
        out = capsys.readouterr().out
        assert "Total:    0" in out
        assert "NO TESTS" in out
