"""Tests for sync.py Claude Code PreToolUse hook injection.

Validates that:
- update_claude_hooks correctly adds PreToolUse hook to settings.json
- Existing hooks are preserved (additive, not overwrite)
- Duplicate hooks are not added (dedup)
- Hook files are copied to target directory
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "skill-sync" / "scripts"))

from sync import (
    _HOOK_COMMAND,
    _PRETOOL_ENTRY,
    _has_hook_entry,
    _update_settings_json,
    _copy_hook_files,
    update_claude_hooks,
)


@pytest.fixture
def tmp_claude_dir(tmp_path):
    """Create a temporary .claude directory structure."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    hooks_dir = claude_dir / "hooks"
    hooks_dir.mkdir()
    skills_dir = claude_dir / "skills"
    skills_dir.mkdir()
    return claude_dir


@pytest.fixture
def source_with_hooks(tmp_path):
    """Create a source directory with hook files."""
    source = tmp_path / "source"
    source.mkdir()
    hooks = source / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "approve-read-commands.sh").write_text("#!/bin/bash\nexit 0\n")
    (hooks / "read-commands.json").write_text('[{"skill":"test","pattern":"*/test.py *"}]\n')
    return source


# ═══════════════════════════════════════════════════════════════════════════
# _has_hook_entry
# ═══════════════════════════════════════════════════════════════════════════


class TestHasHookEntry:
    def test_empty_list(self):
        assert not _has_hook_entry([], _HOOK_COMMAND)

    def test_not_present(self):
        entries = [{"matcher": "Bash", "hooks": [{"type": "command", "command": "other.sh"}]}]
        assert not _has_hook_entry(entries, _HOOK_COMMAND)

    def test_present(self):
        entries = [_PRETOOL_ENTRY]
        assert _has_hook_entry(entries, _HOOK_COMMAND)

    def test_present_among_others(self):
        entries = [
            {"matcher": "Edit", "hooks": [{"type": "command", "command": "lint.sh"}]},
            _PRETOOL_ENTRY,
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "other.sh"}]},
        ]
        assert _has_hook_entry(entries, _HOOK_COMMAND)


# ═══════════════════════════════════════════════════════════════════════════
# _update_settings_json
# ═══════════════════════════════════════════════════════════════════════════


class TestUpdateSettingsJson:
    def test_creates_new_settings(self, tmp_claude_dir):
        settings = tmp_claude_dir / "settings.json"
        assert not settings.exists()
        result = _update_settings_json(settings, dry_run=False)
        assert result is True
        assert settings.exists()
        data = json.loads(settings.read_text())
        assert "PreToolUse" in data["hooks"]
        assert len(data["hooks"]["PreToolUse"]) == 1
        assert data["hooks"]["PreToolUse"][0]["matcher"] == "Bash"

    def test_preserves_existing_hooks(self, tmp_claude_dir):
        settings = tmp_claude_dir / "settings.json"
        existing = {
            "hooks": {
                "PostToolUse": [
                    {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "lint.sh"}]}
                ]
            }
        }
        settings.write_text(json.dumps(existing))
        _update_settings_json(settings, dry_run=False)
        data = json.loads(settings.read_text())
        # Both PostToolUse and PreToolUse should exist
        assert "PostToolUse" in data["hooks"]
        assert "PreToolUse" in data["hooks"]
        assert len(data["hooks"]["PostToolUse"]) == 1
        assert data["hooks"]["PostToolUse"][0]["hooks"][0]["command"] == "lint.sh"

    def test_dedup_does_not_add_twice(self, tmp_claude_dir):
        settings = tmp_claude_dir / "settings.json"
        _update_settings_json(settings, dry_run=False)
        result = _update_settings_json(settings, dry_run=False)
        assert result is False
        data = json.loads(settings.read_text())
        assert len(data["hooks"]["PreToolUse"]) == 1

    def test_dry_run_does_not_write(self, tmp_claude_dir):
        settings = tmp_claude_dir / "settings.json"
        result = _update_settings_json(settings, dry_run=True)
        assert result is False
        assert not settings.exists()

    def test_appends_to_existing_pretool(self, tmp_claude_dir):
        settings = tmp_claude_dir / "settings.json"
        existing = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "other.sh"}]}
                ]
            }
        }
        settings.write_text(json.dumps(existing))
        _update_settings_json(settings, dry_run=False)
        data = json.loads(settings.read_text())
        assert len(data["hooks"]["PreToolUse"]) == 2

    def test_preserves_non_hooks_keys(self, tmp_claude_dir):
        settings = tmp_claude_dir / "settings.json"
        existing = {"permissions": {"allow": ["npm"]}, "hooks": {}}
        settings.write_text(json.dumps(existing))
        _update_settings_json(settings, dry_run=False)
        data = json.loads(settings.read_text())
        assert data["permissions"]["allow"] == ["npm"]


# ═══════════════════════════════════════════════════════════════════════════
# _copy_hook_files
# ═══════════════════════════════════════════════════════════════════════════


class TestCopyHookFiles:
    def test_copies_both_files(self, source_with_hooks, tmp_claude_dir):
        hooks_dir = tmp_claude_dir / "hooks"
        _copy_hook_files(source_with_hooks, hooks_dir, dry_run=False)
        assert (hooks_dir / "approve-read-commands.sh").exists()
        assert (hooks_dir / "read-commands.json").exists()

    def test_script_is_executable(self, source_with_hooks, tmp_claude_dir):
        hooks_dir = tmp_claude_dir / "hooks"
        _copy_hook_files(source_with_hooks, hooks_dir, dry_run=False)
        script = hooks_dir / "approve-read-commands.sh"
        assert script.stat().st_mode & 0o111

    def test_dry_run_does_not_copy(self, source_with_hooks, tmp_path):
        hooks_dir = tmp_path / "new_hooks"
        _copy_hook_files(source_with_hooks, hooks_dir, dry_run=True)
        assert not (hooks_dir / "approve-read-commands.sh").exists()

    def test_creates_hooks_dir_if_missing(self, source_with_hooks, tmp_path):
        hooks_dir = tmp_path / "nonexistent" / "hooks"
        _copy_hook_files(source_with_hooks, hooks_dir, dry_run=False)
        assert hooks_dir.exists()
        assert (hooks_dir / "approve-read-commands.sh").exists()

    def test_warns_on_missing_source(self, tmp_path, capsys):
        source = tmp_path / "empty_source"
        source.mkdir()
        (source / ".claude" / "hooks").mkdir(parents=True)
        hooks_dir = tmp_path / "target_hooks"
        hooks_dir.mkdir()
        _copy_hook_files(source, hooks_dir, dry_run=False)
        output = capsys.readouterr().out
        assert "WARNING" in output


# ═══════════════════════════════════════════════════════════════════════════
# update_claude_hooks (integration)
# ═══════════════════════════════════════════════════════════════════════════


class TestUpdateClaudeHooksIntegration:
    def test_skips_when_claude_not_detected(self, source_with_hooks, capsys):
        detected = {"windsurf": {"name": "Windsurf", "user_path": Path("/tmp"), "project_path": None}}
        update_claude_hooks(source_with_hooks, detected, dry_run=False)
        output = capsys.readouterr().out
        assert "Claude Code" not in output

    def test_updates_user_level(self, source_with_hooks, tmp_path):
        skills_dir = tmp_path / ".claude" / "skills"
        skills_dir.mkdir(parents=True)
        detected = {"claude": {"name": "Claude Code", "user_path": skills_dir, "project_path": None}}
        update_claude_hooks(source_with_hooks, detected, dry_run=False)
        settings = tmp_path / ".claude" / "settings.json"
        assert settings.exists()
        data = json.loads(settings.read_text())
        assert "PreToolUse" in data["hooks"]

    def test_updates_both_levels(self, source_with_hooks, tmp_path):
        user_skills = tmp_path / "user" / ".claude" / "skills"
        user_skills.mkdir(parents=True)
        proj_skills = tmp_path / "proj" / ".claude" / "skills"
        proj_skills.mkdir(parents=True)
        detected = {
            "claude": {
                "name": "Claude Code",
                "user_path": user_skills,
                "project_path": proj_skills,
            }
        }
        update_claude_hooks(source_with_hooks, detected, dry_run=False)
        for base in [tmp_path / "user", tmp_path / "proj"]:
            settings = base / ".claude" / "settings.json"
            assert settings.exists()
            data = json.loads(settings.read_text())
            assert "PreToolUse" in data["hooks"]

    def test_idempotent(self, source_with_hooks, tmp_path):
        skills_dir = tmp_path / ".claude" / "skills"
        skills_dir.mkdir(parents=True)
        detected = {"claude": {"name": "Claude Code", "user_path": skills_dir, "project_path": None}}
        update_claude_hooks(source_with_hooks, detected, dry_run=False)
        update_claude_hooks(source_with_hooks, detected, dry_run=False)
        settings = tmp_path / ".claude" / "settings.json"
        data = json.loads(settings.read_text())
        assert len(data["hooks"]["PreToolUse"]) == 1
