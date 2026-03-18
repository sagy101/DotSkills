"""Tests for ANSI escape code stripping in jenkins-manager."""

import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent.parent / "jenkins-manager" / "scripts")
)

from jenkins_redaction import redact_text, strip_ansi


class TestStripAnsi:
    def test_strip_ansi_removes_color_codes(self):
        assert strip_ansi("\x1b[31merror\x1b[0m") == "error"

    def test_strip_ansi_removes_bold(self):
        assert strip_ansi("\x1b[1mbold\x1b[0m") == "bold"

    def test_strip_ansi_preserves_plain_text(self):
        plain = "just a normal log line"
        assert strip_ansi(plain) == plain

    def test_strip_ansi_handles_nested_codes(self):
        assert strip_ansi("\x1b[0m[\x1b[31merror\x1b[0m]") == "[error]"

    def test_strip_ansi_multiple_colors(self):
        text = "\x1b[32m[info]\x1b[0m \x1b[31m[error]\x1b[0m something"
        assert strip_ansi(text) == "[info] [error] something"

    def test_strip_ansi_with_semicolons(self):
        # SGR with multiple params like \x1b[1;31m (bold red)
        assert strip_ansi("\x1b[1;31mwarning\x1b[0m") == "warning"


class TestRedactTextStripsAnsi:
    def test_redact_text_strips_ansi_before_matching(self):
        # ANSI codes around a secret should be stripped, then secret redacted
        text = "\x1b[31mpassword=secret123\x1b[0m"
        result = redact_text(text)
        assert "secret123" not in result
        assert "password=[REDACTED]" in result

    def test_grep_matches_after_ansi_strip(self):
        """Simulate --grep 'error' on ANSI-encoded text after stripping."""
        raw = "\x1b[0m[\x1b[31merror\x1b[0m] Something went wrong"
        stripped = strip_ansi(raw)
        # After stripping, grep for "error" should match
        assert "error" in stripped.lower()

    def test_redact_strips_ansi_from_bearer(self):
        text = "\x1b[33mBearer\x1b[0m abc123secrettoken"
        result = redact_text(text)
        assert "abc123secrettoken" not in result
        assert "Bearer [REDACTED]" in result

    def test_normal_log_with_ansi_preserved_after_strip(self):
        text = "\x1b[32m[Pipeline]\x1b[0m stage (Build)"
        result = redact_text(text)
        assert result == "[Pipeline] stage (Build)"
