"""Tests for IDE-specific auto-approval handlers in sync.py.

Validates Gemini CLI, Windsurf, Cursor, and Codex auto-approval:
- TOML policy generation and idempotent installation (Gemini)
- Settings.json merge with dedup (Windsurf)
- Info messages for unsupported IDEs (Cursor, Codex)
"""

import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "skill-sync" / "scripts"))

from sync import (
    _GEMINI_POLICY_FILE,
    _generate_gemini_policy,
    _load_read_patterns,
    _pattern_to_gemini_regex,
    _patterns_to_windsurf_prefixes,
    _print_codex_info,
    _print_cursor_info,
    _update_windsurf_settings,
    update_gemini_approval,
    update_read_approvals,
    update_windsurf_approval,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def read_patterns() -> list[dict]:
    return json.loads(
        (REPO_ROOT / ".claude" / "hooks" / "read-commands.json").read_text(encoding="utf-8")
    )


@pytest.fixture
def source_with_patterns(tmp_path):
    """Create a source directory with read-commands.json."""
    source = tmp_path / "source"
    hooks = source / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    # Copy real patterns
    real = REPO_ROOT / ".claude" / "hooks" / "read-commands.json"
    (hooks / "read-commands.json").write_text(real.read_text(encoding="utf-8"))
    # Also copy the hook script (needed for Claude handler)
    real_script = REPO_ROOT / ".claude" / "hooks" / "approve-read-commands.sh"
    (hooks / "approve-read-commands.sh").write_text(real_script.read_text(encoding="utf-8"))
    return source


@pytest.fixture
def gemini_detected(tmp_path):
    """Create a detected IDE dict with Gemini paths."""
    user_skills = tmp_path / "user" / ".gemini" / "skills"
    user_skills.mkdir(parents=True)
    proj_skills = tmp_path / "proj" / ".gemini" / "skills"
    proj_skills.mkdir(parents=True)
    return {
        "gemini": {
            "name": "Gemini CLI",
            "user_path": user_skills,
            "project_path": proj_skills,
        }
    }


@pytest.fixture
def windsurf_detected(tmp_path):
    """Create a detected IDE dict with Windsurf paths."""
    user_skills = tmp_path / "user" / ".codeium" / "windsurf" / "skills"
    user_skills.mkdir(parents=True)
    return {
        "windsurf": {
            "name": "Windsurf",
            "user_path": user_skills,
            "project_path": None,
        }
    }


# ═══════════════════════════════════════════════════════════════════════════
# LOAD READ PATTERNS
# ═══════════════════════════════════════════════════════════════════════════


class TestLoadReadPatterns:
    def test_loads_from_source(self, source_with_patterns):
        patterns = _load_read_patterns(source_with_patterns)
        assert len(patterns) > 0
        assert all("skill" in p and "pattern" in p for p in patterns)

    def test_returns_empty_when_missing(self, tmp_path, capsys):
        patterns = _load_read_patterns(tmp_path)
        assert patterns == []
        assert "WARNING" in capsys.readouterr().out


# ═══════════════════════════════════════════════════════════════════════════
# GEMINI — REGEX CONVERSION
# ═══════════════════════════════════════════════════════════════════════════


class TestGeminiRegexConversion:
    """Test _pattern_to_gemini_regex for all pattern types."""

    # --- Simple patterns ---
    def test_simple_pattern_matches_with_args(self):
        regex = _pattern_to_gemini_regex("*/scripts/fetch_tickets.py *")
        assert re.search(regex, "python3 /path/scripts/fetch_tickets.py --key X")

    def test_simple_pattern_matches_no_args(self):
        regex = _pattern_to_gemini_regex("*/scripts/fetch_tickets.py *")
        assert re.search(regex, "python3 /path/scripts/fetch_tickets.py")

    def test_simple_pattern_rejects_different_script(self):
        regex = _pattern_to_gemini_regex("*/scripts/fetch_tickets.py *")
        assert not re.search(regex, "python3 /path/scripts/create_ticket.py --key X")

    def test_simple_pattern_dots_escaped(self):
        regex = _pattern_to_gemini_regex("*/scripts/build-prompt.py *")
        assert re.search(regex, "python3 /path/scripts/build-prompt.py --list")
        # Dot should not match arbitrary char
        assert not re.search(regex, "python3 /path/scripts/build-promptXpy --list")

    # --- No-args patterns ---
    def test_no_args_matches_exact(self):
        regex = _pattern_to_gemini_regex("*/scripts/jira_setup_env.py")
        assert re.search(regex, "python3 /path/scripts/jira_setup_env.py")

    def test_no_args_rejects_with_args(self):
        regex = _pattern_to_gemini_regex("*/scripts/jira_setup_env.py")
        assert not re.search(regex, "python3 /path/scripts/jira_setup_env.py --flag")

    # --- Subcommand patterns ---
    def test_subcommand_matches(self):
        regex = _pattern_to_gemini_regex("*/scripts/eks_ops.py pods *")
        assert re.search(regex, "python3 /p/scripts/eks_ops.py pods --env stg")

    def test_subcommand_rejects_wrong_subcmd(self):
        regex = _pattern_to_gemini_regex("*/scripts/eks_ops.py pods *")
        assert not re.search(regex, "python3 /p/scripts/eks_ops.py exec --env stg")

    def test_subcommand_rejects_restart(self):
        regex = _pattern_to_gemini_regex("*/scripts/eks_ops.py pods *")
        assert not re.search(regex, "python3 /p/scripts/eks_ops.py restart --env stg")

    def test_subcommand_matches_no_extra_args(self):
        regex = _pattern_to_gemini_regex("*/scripts/eks_ops.py pods *")
        assert re.search(regex, "python3 /p/scripts/eks_ops.py pods")

    # --- Flag-based patterns ---
    def test_flag_matches_flag_first(self):
        regex = _pattern_to_gemini_regex("*/scripts/page_versions.py --list *")
        assert re.search(regex, "python3 /p/scripts/page_versions.py --list")

    def test_flag_matches_flag_after_other_args(self):
        regex = _pattern_to_gemini_regex("*/scripts/page_versions.py --list *")
        assert re.search(regex, "python3 /p/scripts/page_versions.py --page 123 --list")

    def test_flag_rejects_write_flag(self):
        regex = _pattern_to_gemini_regex("*/scripts/page_versions.py --list *")
        assert not re.search(regex, "python3 /p/scripts/page_versions.py --page 123 --revert 56")

    def test_flag_with_value_matches(self):
        regex = _pattern_to_gemini_regex("*/scripts/run_codex.py --mode read-only *")
        assert re.search(regex, "python3 /p/scripts/run_codex.py --mode read-only -")

    def test_flag_with_value_rejects_write(self):
        regex = _pattern_to_gemini_regex("*/scripts/run_codex.py --mode read-only *")
        assert not re.search(regex, "python3 /p/scripts/run_codex.py --mode write -")

    def test_flag_with_value_matches_flag_reordered(self):
        regex = _pattern_to_gemini_regex("*/scripts/run_codex.py --mode read-only *")
        assert re.search(regex, "python3 /p/scripts/run_codex.py --timeout 300 --mode read-only -")

    # --- All real patterns produce valid regex ---
    def test_all_patterns_produce_valid_regex(self, read_patterns):
        for entry in read_patterns:
            regex = _pattern_to_gemini_regex(entry["pattern"])
            # Should compile without error
            re.compile(regex)


# ═══════════════════════════════════════════════════════════════════════════
# GEMINI — TOML POLICY GENERATION
# ═══════════════════════════════════════════════════════════════════════════


class TestGeminiPolicyGeneration:
    def test_generates_valid_toml_structure(self, read_patterns):
        content = _generate_gemini_policy(read_patterns)
        assert "[[rule]]" in content
        assert 'decision = "allow"' in content
        assert 'tool = "shell"' in content
        assert "commandRegex" in content

    def test_has_one_rule_per_pattern(self, read_patterns):
        content = _generate_gemini_policy(read_patterns)
        rule_count = content.count("[[rule]]")
        assert rule_count == len(read_patterns)

    def test_header_present(self, read_patterns):
        content = _generate_gemini_policy(read_patterns)
        assert "Auto-generated by DotSkills" in content
        assert "Do not edit manually" in content

    def test_each_rule_has_description(self, read_patterns):
        content = _generate_gemini_policy(read_patterns)
        for entry in read_patterns:
            assert entry["skill"] in content

    def test_deterministic_output(self, read_patterns):
        """Same input produces same output (for idempotency check)."""
        c1 = _generate_gemini_policy(read_patterns)
        c2 = _generate_gemini_policy(read_patterns)
        assert c1 == c2


# ═══════════════════════════════════════════════════════════════════════════
# GEMINI — INSTALL / IDEMPOTENCY
# ═══════════════════════════════════════════════════════════════════════════


class TestGeminiInstall:
    def test_creates_policy_file(self, source_with_patterns, gemini_detected, tmp_path):
        update_gemini_approval(source_with_patterns, gemini_detected, dry_run=False)
        policy = tmp_path / "user" / ".gemini" / "policies" / _GEMINI_POLICY_FILE
        assert policy.is_file()
        content = policy.read_text()
        assert "[[rule]]" in content

    def test_creates_policy_for_both_levels(self, source_with_patterns, gemini_detected, tmp_path):
        update_gemini_approval(source_with_patterns, gemini_detected, dry_run=False)
        for sub in ("user", "proj"):
            policy = tmp_path / sub / ".gemini" / "policies" / _GEMINI_POLICY_FILE
            assert policy.is_file()

    def test_idempotent_second_run_no_change(self, source_with_patterns, gemini_detected, tmp_path, capsys):
        update_gemini_approval(source_with_patterns, gemini_detected, dry_run=False)
        capsys.readouterr()  # clear
        update_gemini_approval(source_with_patterns, gemini_detected, dry_run=False)
        output = capsys.readouterr().out
        assert "already up to date" in output

    def test_dry_run_does_not_create(self, source_with_patterns, gemini_detected, tmp_path):
        update_gemini_approval(source_with_patterns, gemini_detected, dry_run=True)
        policy = tmp_path / "user" / ".gemini" / "policies" / _GEMINI_POLICY_FILE
        assert not policy.exists()

    def test_skips_when_gemini_not_detected(self, source_with_patterns, capsys):
        detected = {"claude": {"name": "Claude", "user_path": Path("/tmp"), "project_path": None}}
        update_gemini_approval(source_with_patterns, detected, dry_run=False)
        assert "Gemini" not in capsys.readouterr().out

    def test_updates_when_patterns_change(self, source_with_patterns, gemini_detected, tmp_path):
        update_gemini_approval(source_with_patterns, gemini_detected, dry_run=False)
        policy = tmp_path / "user" / ".gemini" / "policies" / _GEMINI_POLICY_FILE
        # Modify patterns file to simulate a change
        patterns_file = source_with_patterns / ".claude" / "hooks" / "read-commands.json"
        patterns_file.write_text('[{"skill": "test", "pattern": "*/scripts/test.py *"}]')
        update_gemini_approval(source_with_patterns, gemini_detected, dry_run=False)
        content = policy.read_text()
        assert "test.py" in content
        assert content.count("[[rule]]") == 1


# ═══════════════════════════════════════════════════════════════════════════
# WINDSURF — PREFIX GENERATION
# ═══════════════════════════════════════════════════════════════════════════


class TestWindsurfPrefixGeneration:
    def test_simple_pattern_generates_prefix(self, tmp_path):
        patterns = [{"skill": "jira-manager", "pattern": "*/scripts/fetch_tickets.py *"}]
        prefixes, skipped = _patterns_to_windsurf_prefixes(patterns, tmp_path)
        assert len(prefixes) == 1
        assert "python3" in prefixes[0]
        assert "fetch_tickets.py" in prefixes[0]
        assert skipped == []

    def test_bash_script_uses_bash_interpreter(self, tmp_path):
        patterns = [{"skill": "sbt-build-test", "pattern": "*/scripts/sbt_status.sh *"}]
        prefixes, _ = _patterns_to_windsurf_prefixes(patterns, tmp_path)
        assert prefixes[0].startswith("bash ")

    def test_subcommand_included_in_prefix(self, tmp_path):
        patterns = [{"skill": "eks-pod-ops", "pattern": "*/scripts/eks_ops.py pods *"}]
        prefixes, _ = _patterns_to_windsurf_prefixes(patterns, tmp_path)
        assert "eks_ops.py pods" in prefixes[0]

    def test_flag_pattern_skipped(self, tmp_path):
        patterns = [{"skill": "confluence-publisher", "pattern": "*/scripts/page_versions.py --list *"}]
        prefixes, skipped = _patterns_to_windsurf_prefixes(patterns, tmp_path)
        assert prefixes == []
        assert len(skipped) == 1

    def test_no_args_pattern_generates_prefix(self, tmp_path):
        patterns = [{"skill": "jira-manager", "pattern": "*/scripts/jira_setup_env.py"}]
        prefixes, _ = _patterns_to_windsurf_prefixes(patterns, tmp_path)
        assert len(prefixes) == 1
        assert "jira_setup_env.py" in prefixes[0]

    def test_uses_correct_skill_subdir(self, tmp_path):
        patterns = [{"skill": "bitbucket-manager", "pattern": "*/scripts/pr_get.py *"}]
        prefixes, _ = _patterns_to_windsurf_prefixes(patterns, tmp_path)
        assert "bitbucket-manager" in prefixes[0]

    def test_all_real_patterns_handled(self, read_patterns, tmp_path):
        prefixes, skipped = _patterns_to_windsurf_prefixes(read_patterns, tmp_path)
        total = len(prefixes) + len(skipped)
        assert total == len(read_patterns)

    def test_flag_patterns_are_only_skipped_ones(self, read_patterns, tmp_path):
        """Only patterns with flags should be skipped."""
        _, skipped = _patterns_to_windsurf_prefixes(read_patterns, tmp_path)
        for pat in skipped:
            parts = pat.split()
            # The second part (after script) should start with --
            assert any(p.startswith("--") for p in parts[1:]), f"Non-flag pattern skipped: {pat}"


# ═══════════════════════════════════════════════════════════════════════════
# WINDSURF — SETTINGS MERGE
# ═══════════════════════════════════════════════════════════════════════════


class TestWindsurfSettingsMerge:
    def test_creates_new_settings(self, tmp_path):
        settings = tmp_path / "settings.json"
        result = _update_windsurf_settings(settings, {"cmd1", "cmd2"}, dry_run=False)
        assert result is True
        data = json.loads(settings.read_text())
        assert sorted(data["cascadeCommandsAllowList"]) == ["cmd1", "cmd2"]

    def test_preserves_existing_entries(self, tmp_path):
        settings = tmp_path / "settings.json"
        settings.write_text(json.dumps({"cascadeCommandsAllowList": ["existing_cmd"]}))
        _update_windsurf_settings(settings, {"new_cmd"}, dry_run=False)
        data = json.loads(settings.read_text())
        assert "existing_cmd" in data["cascadeCommandsAllowList"]
        assert "new_cmd" in data["cascadeCommandsAllowList"]

    def test_preserves_other_settings(self, tmp_path):
        settings = tmp_path / "settings.json"
        settings.write_text(json.dumps({"editor.fontSize": 14, "theme": "dark"}))
        _update_windsurf_settings(settings, {"cmd1"}, dry_run=False)
        data = json.loads(settings.read_text())
        assert data["editor.fontSize"] == 14
        assert data["theme"] == "dark"

    def test_dedup_no_duplicates(self, tmp_path):
        settings = tmp_path / "settings.json"
        settings.write_text(json.dumps({"cascadeCommandsAllowList": ["cmd1"]}))
        result = _update_windsurf_settings(settings, {"cmd1"}, dry_run=False)
        assert result is False
        data = json.loads(settings.read_text())
        assert data["cascadeCommandsAllowList"].count("cmd1") == 1

    def test_dry_run_does_not_write(self, tmp_path):
        settings = tmp_path / "settings.json"
        result = _update_windsurf_settings(settings, {"cmd1"}, dry_run=True)
        assert result is False
        assert not settings.exists()

    def test_handles_corrupt_json(self, tmp_path):
        settings = tmp_path / "settings.json"
        settings.write_text("not valid json{{{")
        result = _update_windsurf_settings(settings, {"cmd1"}, dry_run=False)
        assert result is True
        data = json.loads(settings.read_text())
        assert "cmd1" in data["cascadeCommandsAllowList"]

    def test_idempotent_second_run(self, tmp_path, capsys):
        settings = tmp_path / "settings.json"
        _update_windsurf_settings(settings, {"cmd1", "cmd2"}, dry_run=False)
        capsys.readouterr()
        result = _update_windsurf_settings(settings, {"cmd1", "cmd2"}, dry_run=False)
        assert result is False
        assert "already present" in capsys.readouterr().out


# ═══════════════════════════════════════════════════════════════════════════
# WINDSURF — INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════


class TestWindsurfInstallIntegration:
    def test_skips_when_windsurf_not_detected(self, source_with_patterns, capsys):
        detected = {"claude": {"name": "Claude", "user_path": Path("/tmp"), "project_path": None}}
        update_windsurf_approval(source_with_patterns, detected, dry_run=False)
        assert "Windsurf" not in capsys.readouterr().out

    def test_installs_prefixes(self, source_with_patterns, windsurf_detected, tmp_path):
        settings = tmp_path / "windsurf_settings.json"
        with patch("sync._windsurf_user_settings_path", return_value=settings):
            update_windsurf_approval(source_with_patterns, windsurf_detected, dry_run=False)
        assert settings.is_file()
        data = json.loads(settings.read_text())
        assert len(data["cascadeCommandsAllowList"]) > 0

    def test_notes_skipped_flag_patterns(self, source_with_patterns, windsurf_detected, tmp_path, capsys):
        settings = tmp_path / "windsurf_settings.json"
        with patch("sync._windsurf_user_settings_path", return_value=settings):
            update_windsurf_approval(source_with_patterns, windsurf_detected, dry_run=False)
        output = capsys.readouterr().out
        assert "flag-based patterns skipped" in output

    def test_idempotent_second_run(self, source_with_patterns, windsurf_detected, tmp_path, capsys):
        settings = tmp_path / "windsurf_settings.json"
        with patch("sync._windsurf_user_settings_path", return_value=settings):
            update_windsurf_approval(source_with_patterns, windsurf_detected, dry_run=False)
            capsys.readouterr()
            update_windsurf_approval(source_with_patterns, windsurf_detected, dry_run=False)
        output = capsys.readouterr().out
        assert "already present" in output


# ═══════════════════════════════════════════════════════════════════════════
# CURSOR / CODEX — INFO MESSAGES
# ═══════════════════════════════════════════════════════════════════════════


class TestCursorInfo:
    def test_prints_info(self, capsys):
        _print_cursor_info()
        output = capsys.readouterr().out
        assert "Cursor" in output
        assert "SQLite" in output or "state.vscdb" in output

    def test_mentions_workaround(self, capsys):
        _print_cursor_info()
        output = capsys.readouterr().out
        assert "windsurf-read-whitelist.md" in output


class TestCodexInfo:
    def test_prints_info(self, capsys):
        _print_codex_info()
        output = capsys.readouterr().out
        assert "Codex" in output
        assert "approval_policy" in output

    def test_mentions_config_path(self, capsys):
        _print_codex_info()
        output = capsys.readouterr().out
        assert "config.toml" in output


# ═══════════════════════════════════════════════════════════════════════════
# DISPATCHER — update_read_approvals
# ═══════════════════════════════════════════════════════════════════════════


class TestUpdateReadApprovals:
    def test_calls_claude_when_targeted(self, source_with_patterns, tmp_path, capsys):
        skills = tmp_path / ".claude" / "skills"
        skills.mkdir(parents=True)
        detected = {"claude": {"name": "Claude Code", "user_path": skills, "project_path": None}}
        update_read_approvals(source_with_patterns, detected, ["claude"], dry_run=False)
        output = capsys.readouterr().out
        assert "Claude Code" in output

    def test_calls_gemini_when_targeted(self, source_with_patterns, gemini_detected, capsys):
        update_read_approvals(source_with_patterns, gemini_detected, ["gemini"], dry_run=False)
        output = capsys.readouterr().out
        assert "Gemini" in output

    def test_skips_undetected_ides(self, source_with_patterns, capsys):
        detected = {}
        update_read_approvals(source_with_patterns, detected, ["claude", "gemini"], dry_run=False)
        output = capsys.readouterr().out
        assert output == ""

    def test_cursor_info_only_when_detected(self, source_with_patterns, capsys):
        detected = {"cursor": {"name": "Cursor", "user_path": Path("/tmp"), "project_path": None}}
        update_read_approvals(source_with_patterns, detected, ["cursor"], dry_run=False)
        output = capsys.readouterr().out
        assert "auto-approval not supported" in output

    def test_codex_info_only_when_detected(self, source_with_patterns, capsys):
        detected = {"codex": {"name": "Codex", "user_path": Path("/tmp"), "project_path": None}}
        update_read_approvals(source_with_patterns, detected, ["codex"], dry_run=False)
        output = capsys.readouterr().out
        assert "auto-approval not supported" in output
