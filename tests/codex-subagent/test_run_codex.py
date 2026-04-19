#!/usr/bin/env python3
"""Unit tests for run_codex.py safety-critical parsing functions."""

import os
import sys
import unittest.mock
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "codex-subagent", "scripts"))

import run_codex as _mod
from run_codex import (
    DEFAULT_MAX_PARALLEL,
    _check_dangerous_flag,
    _check_sandbox_flag,
    _count_active_agents,
    _ensure_pid_dir,
    _extract_subcommand,
    _is_pid_alive,
    _is_sandbox_config_override,
    _is_scope_flag,
    _matches_blocked_flag,
    _normalize_exit_code,
    _read_pid_metadata,
    _register_agent,
    _report_exit_error,
    _scan_agents,
    _unregister_agent,
    _validate_args,
    _validate_prompt,
    build_codex_args,
    build_prompt_file,
    enforce_parallel_limit,
    parse_args_with_passthrough,
    print_status,
    scan_for_dangerous_flags,
    setup_worktree,
    version_gte,
)

# ========== version_gte ==========


class TestVersionGte:
    def test_equal(self):
        assert version_gte("0.106.0", "0.106.0") is True

    def test_greater_patch(self):
        assert version_gte("0.106.1", "0.106.0") is True

    def test_greater_minor(self):
        assert version_gte("0.107.0", "0.106.0") is True

    def test_greater_major(self):
        assert version_gte("1.0.0", "0.106.0") is True

    def test_less_patch(self):
        assert version_gte("0.105.9", "0.106.0") is False

    def test_less_minor(self):
        assert version_gte("0.99.0", "0.106.0") is False

    def test_malformed_returns_false(self):
        assert version_gte("abc", "0.106.0") is False

    def test_empty_returns_false(self):
        assert version_gte("", "0.106.0") is False

    def test_two_part_version(self):
        assert version_gte("0.106", "0.106.0") is False

    def test_four_part_version(self):
        assert version_gte("0.106.0.1", "0.106.0") is True


# ========== _is_sandbox_config_override ==========


class TestIsSandboxConfigOverride:
    def test_c_sandbox(self):
        assert _is_sandbox_config_override("-c", "sandbox_mode=danger") is True

    def test_config_sandbox(self):
        assert _is_sandbox_config_override("--config", "sandbox_mode=x") is True

    def test_config_eq_sandbox(self):
        assert _is_sandbox_config_override("--config=sandbox_mode=x", None) is True

    def test_short_c_attached_sandbox(self):
        assert _is_sandbox_config_override("-csandbox_mode=x", None) is True

    def test_c_non_sandbox(self):
        assert _is_sandbox_config_override("-c", "model=gpt-4") is False

    def test_config_eq_non_sandbox(self):
        assert _is_sandbox_config_override("--config=model=gpt-4", None) is False

    def test_c_no_next(self):
        assert _is_sandbox_config_override("-c", None) is False

    def test_unrelated_flag(self):
        assert _is_sandbox_config_override("--model", "sandbox") is False

    def test_case_insensitive(self):
        assert _is_sandbox_config_override("-c", "Sandbox_mode=x") is True
        assert _is_sandbox_config_override("--config=SANDBOX_MODE=x", None) is True


# ========== _is_scope_flag ==========


class TestIsScopeFlag:
    def test_cd(self):
        assert _is_scope_flag("--cd") is True

    def test_cd_eq(self):
        assert _is_scope_flag("--cd=/other/dir") is True

    def test_short_c(self):
        assert _is_scope_flag("-C") is True

    def test_add_dir(self):
        assert _is_scope_flag("--add-dir") is True

    def test_add_dir_eq(self):
        assert _is_scope_flag("--add-dir=/extra") is True

    def test_not_scope(self):
        assert _is_scope_flag("--model") is False
        assert _is_scope_flag("-m") is False


# ========== _matches_blocked_flag ==========


class TestMatchesBlockedFlag:
    def test_exact_long(self):
        assert _matches_blocked_flag("--ephemeral", "--ephemeral") is True

    def test_exact_short(self):
        assert _matches_blocked_flag("-o", "-o") is True

    def test_long_eq_form(self):
        assert (
            _matches_blocked_flag("--output-last-message=/tmp/x", "--output-last-message") is True
        )

    def test_short_attached(self):
        assert _matches_blocked_flag("-o/tmp/x", "-o") is True

    def test_no_match(self):
        assert _matches_blocked_flag("--model", "--ephemeral") is False

    def test_short_exact_no_false_positive(self):
        assert _matches_blocked_flag("-o", "--output-last-message") is False

    def test_long_flag_no_short_match(self):
        assert _matches_blocked_flag("--ephemeralx", "--ephemeral") is False
        assert _matches_blocked_flag("--ephemeral=yes", "--ephemeral") is True


# ========== _check_sandbox_flag ==========


class TestCheckSandboxFlag:
    def test_sandbox_danger_full(self):
        with pytest.raises(SystemExit):
            _check_sandbox_flag("--sandbox=danger-full-access", None)

    def test_sandbox_danger_two_args(self):
        with pytest.raises(SystemExit):
            _check_sandbox_flag("--sandbox", "danger-full-access")

    def test_sandbox_safe_still_blocked(self):
        with pytest.raises(SystemExit):
            _check_sandbox_flag("--sandbox=read-only", None)

    def test_sandbox_bare(self):
        with pytest.raises(SystemExit):
            _check_sandbox_flag("--sandbox", "read-only")

    def test_s_short(self):
        with pytest.raises(SystemExit):
            _check_sandbox_flag("-s", None)

    def test_s_attached_value(self):
        with pytest.raises(SystemExit):
            _check_sandbox_flag("-sdanger-full-access", None)

    def test_s_safe_still_blocked(self):
        with pytest.raises(SystemExit):
            _check_sandbox_flag("-sread-only", None)

    def test_sandbox_bare_no_next_arg(self):
        with pytest.raises(SystemExit):
            _check_sandbox_flag("--sandbox", None)

    def test_unrelated_passes(self):
        _check_sandbox_flag("--model", None)
        _check_sandbox_flag("-m", None)


# ========== _check_dangerous_flag ==========


class TestCheckDangerousFlag:
    def test_dangerously_bypass(self):
        with pytest.raises(SystemExit):
            _check_dangerous_flag("--dangerously-bypass-is-safe-prompt", None)

    def test_config_sandbox_override(self):
        with pytest.raises(SystemExit):
            _check_dangerous_flag("-c", "sandbox_mode=danger")

    def test_config_eq_sandbox(self):
        with pytest.raises(SystemExit):
            _check_dangerous_flag("--config=sandbox_mode=x", None)

    def test_cd_blocked(self):
        with pytest.raises(SystemExit):
            _check_dangerous_flag("--cd", "/other/dir")

    def test_cd_eq_blocked(self):
        with pytest.raises(SystemExit):
            _check_dangerous_flag("--cd=/other", None)

    def test_short_c_blocked(self):
        with pytest.raises(SystemExit):
            _check_dangerous_flag("-C", None)

    def test_add_dir_blocked(self):
        with pytest.raises(SystemExit):
            _check_dangerous_flag("--add-dir", "/extra")

    def test_add_dir_eq_blocked(self):
        with pytest.raises(SystemExit):
            _check_dangerous_flag("--add-dir=/extra", None)

    def test_output_last_message_bare_blocked(self):
        with pytest.raises(SystemExit):
            _check_dangerous_flag("--output-last-message", "/tmp/x")

    def test_ephemeral_blocked(self):
        with pytest.raises(SystemExit):
            _check_dangerous_flag("--ephemeral", None)

    def test_o_blocked(self):
        with pytest.raises(SystemExit):
            _check_dangerous_flag("-o", "/tmp/x")

    def test_o_attached_blocked(self):
        with pytest.raises(SystemExit):
            _check_dangerous_flag("-o/tmp/x", None)

    def test_output_eq_blocked(self):
        with pytest.raises(SystemExit):
            _check_dangerous_flag("--output-last-message=/tmp/x", None)

    def test_json_blocked(self):
        with pytest.raises(SystemExit):
            _check_dangerous_flag("--json", None)

    def test_full_auto_blocked(self):
        with pytest.raises(SystemExit):
            _check_dangerous_flag("--full-auto", None)

    def test_safe_passthrough(self):
        _check_dangerous_flag("--model", "gpt-4")
        _check_dangerous_flag("-m", "gpt-4")
        _check_dangerous_flag("-c", "model=gpt-4")
        _check_dangerous_flag("--skip-git-repo-check", None)
        _check_dangerous_flag("--output-schema", "/tmp/schema.json")
        _check_dangerous_flag("-i", "screenshot.png")
        _check_dangerous_flag("--image", "screenshot.png")
        _check_dangerous_flag("--oss", None)
        _check_dangerous_flag("--local-provider", "ollama")
        _check_dangerous_flag("-p", "fast")
        _check_dangerous_flag("--profile", "fast")
        _check_dangerous_flag("--enable", "streaming")
        _check_dangerous_flag("--disable", "streaming")


# ========== scan_for_dangerous_flags (integration) ==========


class TestScanForDangerousFlags:
    def test_clean_passthrough(self):
        scan_for_dangerous_flags(["--model", "gpt-4", "-c", "temperature=0"])

    def test_catches_sandbox_in_list(self):
        with pytest.raises(SystemExit):
            scan_for_dangerous_flags(["--model", "gpt-4", "--sandbox", "danger-full-access"])

    def test_catches_cd_in_list(self):
        with pytest.raises(SystemExit):
            scan_for_dangerous_flags(["--cd=/evil"])

    def test_catches_config_sandbox_in_list(self):
        with pytest.raises(SystemExit):
            scan_for_dangerous_flags(["--config=sandbox_mode=danger"])

    def test_catches_o_attached(self):
        with pytest.raises(SystemExit):
            scan_for_dangerous_flags(["-o/tmp/x"])

    def test_empty_list(self):
        scan_for_dangerous_flags([])

    def test_catches_json_in_list(self):
        with pytest.raises(SystemExit):
            scan_for_dangerous_flags(["--model", "gpt-4", "--json"])

    def test_catches_full_auto_in_list(self):
        with pytest.raises(SystemExit):
            scan_for_dangerous_flags(["--full-auto"])

    def test_safe_passthrough_flags_in_list(self):
        scan_for_dangerous_flags(
            [
                "--model",
                "o3",
                "--skip-git-repo-check",
                "--output-schema",
                "/tmp/schema.json",
                "-i",
                "img.png",
                "--oss",
                "-p",
                "fast",
                "--enable",
                "streaming",
            ]
        )

    def test_catches_dangerously_bypass_in_list(self):
        with pytest.raises(SystemExit):
            scan_for_dangerous_flags(["--dangerously-bypass-is-safe-prompt"])

    def test_catches_s_short_in_list(self):
        with pytest.raises(SystemExit):
            scan_for_dangerous_flags(["-s", "read-only"])

    def test_catches_ephemeral_in_list(self):
        with pytest.raises(SystemExit):
            scan_for_dangerous_flags(["--model", "o3", "--ephemeral"])

    def test_catches_output_last_message_in_list(self):
        with pytest.raises(SystemExit):
            scan_for_dangerous_flags(["--output-last-message", "/tmp/x"])

    def test_catches_add_dir_eq_in_list(self):
        with pytest.raises(SystemExit):
            scan_for_dangerous_flags(["--add-dir=/extra"])


# ========== parse + scan integration (blocked flags × all delivery paths) ==========

# Every blocked flag that must be caught, grouped by category.
# Each entry is a list of args that contains the blocked flag (some need a value).
BLOCKED_FLAG_SAMPLES = [
    # sandbox flags
    ["--sandbox", "danger-full-access"],
    ["--sandbox=read-only"],
    ["-s"],
    ["-sdanger-full-access"],
    # dangerous bypass
    ["--dangerously-bypass-is-safe-prompt"],
    # config sandbox override
    ["-c", "sandbox_mode=danger"],
    ["--config=sandbox_mode=danger"],
    # scope flags
    ["--cd", "/evil"],
    ["--cd=/evil"],
    ["-C"],
    ["--add-dir", "/extra"],
    ["--add-dir=/extra"],
    # wrapper-managed flags (blocked from direct passthrough)
    ["--ephemeral"],
    ["--full-auto"],
    ["-o", "/tmp/x"],
    ["-o/tmp/x"],
    ["--output-last-message=/tmp/x"],
    ["--output-last-message", "/tmp/x"],
    ["--json"],
]


def _parse_then_scan(argv: list[str]) -> None:
    """Helper: parse argv then run safety scan on resulting passthrough."""
    _, passthrough = parse_args_with_passthrough(argv)
    scan_for_dangerous_flags(passthrough)


class TestBlockedFlagsViaAllPaths:
    """Integration: blocked flags must be caught regardless of delivery path."""

    # --- Path 1: normal passthrough (unrecognized flag, before '-') ---
    @pytest.mark.parametrize(
        "blocked", BLOCKED_FLAG_SAMPLES, ids=[b[0] for b in BLOCKED_FLAG_SAMPLES]
    )
    def test_blocked_via_normal_passthrough(self, blocked: list[str]) -> None:
        argv = ["--mode", "read-only"] + blocked + ["-"]
        with pytest.raises(SystemExit):
            _parse_then_scan(argv)

    # --- Path 2: after '--' separator ---
    @pytest.mark.parametrize(
        "blocked", BLOCKED_FLAG_SAMPLES, ids=[b[0] for b in BLOCKED_FLAG_SAMPLES]
    )
    def test_blocked_via_double_dash(self, blocked: list[str]) -> None:
        argv = ["--mode", "read-only", "--"] + blocked + ["-"]
        with pytest.raises(SystemExit):
            _parse_then_scan(argv)

    # --- Path 3: trailing args after '-' stdin marker ---
    @pytest.mark.parametrize(
        "blocked", BLOCKED_FLAG_SAMPLES, ids=[b[0] for b in BLOCKED_FLAG_SAMPLES]
    )
    def test_blocked_via_trailing_after_stdin(self, blocked: list[str]) -> None:
        argv = ["--mode", "read-only", "-"] + blocked
        with pytest.raises(SystemExit):
            _parse_then_scan(argv)


class TestSafePassthroughViaAllPaths:
    """Integration: safe flags must NOT be blocked regardless of delivery path."""

    SAFE_FLAG_SAMPLES = [
        ["--model", "o3"],
        ["-m", "o3"],
        ["-c", "temperature=0"],
        ["--output-schema", "/tmp/schema.json"],
        ["-i", "screenshot.png"],
        ["--image", "screenshot.png"],
        ["--oss"],
        ["--local-provider", "ollama"],
        ["-p", "fast"],
        ["--profile", "fast"],
        ["--enable", "streaming"],
        ["--disable", "streaming"],
    ]

    @pytest.mark.parametrize("safe", SAFE_FLAG_SAMPLES, ids=[s[0] for s in SAFE_FLAG_SAMPLES])
    def test_safe_via_normal_passthrough(self, safe: list[str]) -> None:
        argv = ["--mode", "read-only"] + safe + ["-"]
        _parse_then_scan(argv)  # should not raise

    @pytest.mark.parametrize("safe", SAFE_FLAG_SAMPLES, ids=[s[0] for s in SAFE_FLAG_SAMPLES])
    def test_safe_via_double_dash(self, safe: list[str]) -> None:
        argv = ["--mode", "read-only", "--"] + safe + ["-"]
        _parse_then_scan(argv)  # should not raise

    @pytest.mark.parametrize("safe", SAFE_FLAG_SAMPLES, ids=[s[0] for s in SAFE_FLAG_SAMPLES])
    def test_safe_via_trailing_after_stdin(self, safe: list[str]) -> None:
        argv = ["--mode", "read-only", "-"] + safe
        _parse_then_scan(argv)  # should not raise


# ========== _extract_subcommand ==========


class TestExtractSubcommand:
    def test_review_first_token(self):
        sub, sub_args, rest = _extract_subcommand(["review", "--uncommitted"])
        assert sub == "review"
        assert sub_args == ["--uncommitted"]
        assert rest == []

    def test_no_subcommand(self):
        sub, sub_args, rest = _extract_subcommand(["--model", "gpt-4"])
        assert sub is None
        assert sub_args == []
        assert rest == ["--model", "gpt-4"]

    def test_review_as_flag_value_not_extracted(self):
        sub, _, rest = _extract_subcommand(["--profile", "review"])
        assert sub is None
        assert rest == ["--profile", "review"]

    def test_empty_passthrough(self):
        sub, _, rest = _extract_subcommand([])
        assert sub is None
        assert rest == []

    def test_unknown_positional_stops_search(self):
        sub, _, rest = _extract_subcommand(["something", "review"])
        assert sub is None
        assert rest == ["something", "review"]

    def test_review_after_flag_eq(self):
        sub, sub_args, rest = _extract_subcommand(["--model=gpt-4", "review", "--base", "main"])
        assert sub == "review"
        assert sub_args == ["--base", "main"]
        assert rest == ["--model=gpt-4"]

    def test_review_base_direct(self):
        sub, sub_args, rest = _extract_subcommand(["review", "--base", "main"])
        assert sub == "review"
        assert sub_args == ["--base", "main"]
        assert rest == []

    def test_review_after_value_flag_skips_correctly(self):
        sub, sub_args, rest = _extract_subcommand(["--model", "gpt-4", "review", "--uncommitted"])
        assert sub == "review"
        assert sub_args == ["--uncommitted"]
        assert rest == ["--model", "gpt-4"]


# ========== _normalize_exit_code ==========


class TestNormalizeExitCode:
    def test_none(self):
        assert _normalize_exit_code(None) == 1

    def test_zero(self):
        assert _normalize_exit_code(0) == 0

    def test_positive(self):
        assert _normalize_exit_code(1) == 1
        assert _normalize_exit_code(2) == 2

    def test_sigterm(self):
        assert _normalize_exit_code(-15) == 143

    def test_sigkill(self):
        assert _normalize_exit_code(-9) == 137

    def test_sigint(self):
        assert _normalize_exit_code(-2) == 130


# ========== build_codex_args ==========


class TestBuildCodexArgs:
    def test_read_only_basic(self):
        args = build_codex_args(
            mode="read-only",
            resume=False,
            persist=False,
            web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt",
            worktree_dir=None,
            passthrough=[],
        )
        assert args[:1] == ["exec"]
        assert "--sandbox" in args
        idx = args.index("--sandbox")
        assert args[idx + 1] == "read-only"
        assert "--ephemeral" in args
        assert "-o" in args
        assert "--full-auto" not in args

    def test_write_mode(self):
        args = build_codex_args(
            mode="write",
            resume=False,
            persist=False,
            web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt",
            worktree_dir=None,
            passthrough=[],
        )
        assert "--full-auto" in args
        assert "--sandbox" in args
        idx = args.index("--sandbox")
        assert args[idx + 1] == "workspace-write"

    def test_persist_no_ephemeral(self):
        args = build_codex_args(
            mode="read-only",
            resume=False,
            persist=True,
            web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt",
            worktree_dir=None,
            passthrough=[],
        )
        assert "--ephemeral" not in args

    def test_web_search(self):
        args = build_codex_args(
            mode="read-only",
            resume=False,
            persist=False,
            web_search=True,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt",
            worktree_dir=None,
            passthrough=[],
        )
        assert "-c" in args
        idx = args.index("-c")
        assert args[idx + 1] == "web_search_request=true"

    def test_worktree_cd(self):
        args = build_codex_args(
            mode="write",
            resume=False,
            persist=False,
            web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt",
            worktree_dir="/tmp/wt-123",
            passthrough=[],
        )
        assert "--cd" in args
        idx = args.index("--cd")
        assert args[idx + 1] == "/tmp/wt-123"

    def test_resume(self):
        args = build_codex_args(
            mode="read-only",
            resume=True,
            persist=False,
            web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt",
            worktree_dir=None,
            passthrough=[],
        )
        assert args[:3] == ["exec", "resume", "--last"]
        assert "--sandbox" not in args
        assert "-o" in args
        idx = args.index("-o")
        assert args[idx + 1] == "/tmp/r.txt"

    def test_review_subcommand(self):
        args = build_codex_args(
            mode="read-only",
            resume=False,
            persist=False,
            web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt",
            worktree_dir=None,
            passthrough=["review", "--uncommitted"],
        )
        assert args[0] == "exec"
        assert args[1] == "review"
        assert "--uncommitted" in args

    def test_color_always_present(self):
        args = build_codex_args(
            mode="read-only",
            resume=False,
            persist=False,
            web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt",
            worktree_dir=None,
            passthrough=[],
        )
        assert "--color" in args
        idx = args.index("--color")
        assert args[idx + 1] == "never"

    def test_passthrough_appended(self):
        args = build_codex_args(
            mode="read-only",
            resume=False,
            persist=False,
            web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt",
            worktree_dir=None,
            passthrough=["--model", "o3"],
        )
        assert "--model" in args
        assert "o3" in args

    def test_skip_git_repo_check_appended(self):
        args = build_codex_args(
            mode="read-only",
            resume=False,
            persist=False,
            web_search=False,
            skip_git_repo_check=True,
            result_file="/tmp/r.txt",
            worktree_dir=None,
            passthrough=[],
        )
        assert "--skip-git-repo-check" in args

    def test_skip_git_repo_check_not_appended_when_false(self):
        args = build_codex_args(
            mode="read-only",
            resume=False,
            persist=False,
            web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt",
            worktree_dir=None,
            passthrough=[],
        )
        assert "--skip-git-repo-check" not in args

    def test_skip_git_repo_check_with_resume(self):
        args = build_codex_args(
            mode="read-only",
            resume=True,
            persist=False,
            web_search=False,
            skip_git_repo_check=True,
            result_file="/tmp/r.txt",
            worktree_dir=None,
            passthrough=[],
        )
        assert "--skip-git-repo-check" in args

    def test_resume_still_appends_passthrough(self):
        args = build_codex_args(
            mode="read-only",
            resume=True,
            persist=False,
            web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt",
            worktree_dir=None,
            passthrough=["--model", "o3"],
        )
        assert "--model" in args
        assert "o3" in args

    def test_write_mode_has_ephemeral(self):
        args = build_codex_args(
            mode="write",
            resume=False,
            persist=False,
            web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt",
            worktree_dir=None,
            passthrough=[],
        )
        assert "--ephemeral" in args

    def test_review_base_subcommand(self):
        args = build_codex_args(
            mode="read-only",
            resume=False,
            persist=False,
            web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt",
            worktree_dir=None,
            passthrough=["review", "--base", "main"],
        )
        assert args[0] == "exec"
        assert args[1] == "review"
        assert "--base" in args
        assert "main" in args


# ========== parse_args_with_passthrough ==========


class TestParseArgsWithPassthrough:
    def test_basic_read_only(self):
        parsed, pt = parse_args_with_passthrough(["--mode", "read-only", "-"])
        assert parsed.mode == "read-only"
        assert pt == []

    def test_passthrough_collected(self):
        parsed, pt = parse_args_with_passthrough(["--mode", "write", "--model", "gpt-4", "-"])
        assert parsed.mode == "write"
        assert pt == ["--model", "gpt-4"]

    def test_stdin_marker_stops_parsing(self):
        _, pt = parse_args_with_passthrough(["--mode", "read-only", "-", "--extra"])
        assert pt == ["--extra"]

    def test_defaults(self):
        parsed, _ = parse_args_with_passthrough(["-"])
        assert parsed.mode == "read-only"
        assert parsed.collision == "high"
        assert parsed.timeout == 600
        assert parsed.resume is False
        assert parsed.persist is False
        assert parsed.web_search is False
        assert parsed.review_prompt is None
        assert parsed.max_parallel == DEFAULT_MAX_PARALLEL

    def test_all_wrapper_flags(self):
        parsed, passthrough = parse_args_with_passthrough(
            [
                "--mode",
                "write",
                "--collision",
                "medium",
                "--timeout",
                "1200",
                "--web-search",
                "--resume",
                "--persist",
                "--skip-git-repo-check",
                "--max-parallel",
                "8",
                "--review-prompt",
                "/tmp/p.md",
                "-",
            ]
        )
        assert parsed.mode == "write"
        assert parsed.collision == "medium"
        assert parsed.timeout == 1200
        assert parsed.web_search is True
        assert parsed.resume is True
        assert parsed.persist is True
        assert parsed.skip_git_repo_check is True
        assert parsed.review_prompt == "/tmp/p.md"
        assert parsed.max_parallel == 8
        assert passthrough == []

    def test_max_parallel_default(self):
        parsed, _ = parse_args_with_passthrough(["--mode", "read-only", "-"])
        assert parsed.max_parallel == 6

    def test_max_parallel_override(self):
        parsed, _ = parse_args_with_passthrough(["--max-parallel", "10", "-"])
        assert parsed.max_parallel == 10

    def test_max_parallel_not_leaked_to_passthrough(self):
        parsed, pt = parse_args_with_passthrough(["--max-parallel", "4", "--model", "o3", "-"])
        assert parsed.max_parallel == 4
        assert "--max-parallel" not in pt
        assert "4" not in pt
        assert pt == ["--model", "o3"]

    def test_mixed_wrapper_and_passthrough(self):
        parsed, pt = parse_args_with_passthrough(
            [
                "--mode",
                "read-only",
                "review",
                "--uncommitted",
                "-",
            ]
        )
        assert parsed.mode == "read-only"
        assert pt == ["review", "--uncommitted"]

    def test_double_dash_routes_to_passthrough(self):
        parsed, pt = parse_args_with_passthrough(
            [
                "--mode",
                "read-only",
                "--",
                "--skip-git-repo-check",
                "-",
            ]
        )
        assert parsed.mode == "read-only"
        assert pt == ["--skip-git-repo-check"]

    def test_double_dash_does_not_leak_into_passthrough(self):
        """The literal '--' must NOT appear in passthrough args."""
        _, pt = parse_args_with_passthrough(
            [
                "--mode",
                "read-only",
                "--",
                "-m",
                "o3",
                "-",
            ]
        )
        assert "--" not in pt
        assert pt == ["-m", "o3"]

    def test_double_dash_multiple_passthrough_flags(self):
        _, pt = parse_args_with_passthrough(
            [
                "--mode",
                "write",
                "--",
                "-m",
                "o3",
                "-c",
                "temperature=0",
                "-",
            ]
        )
        assert pt == ["-m", "o3", "-c", "temperature=0"]

    def test_double_dash_no_stdin_marker(self):
        """If no '-' after '--', everything goes to passthrough."""
        _, pt = parse_args_with_passthrough(
            [
                "--mode",
                "read-only",
                "--",
                "--model",
                "o3",
            ]
        )
        assert pt == ["--model", "o3"]

    def test_skip_git_repo_check_as_wrapper_flag(self):
        parsed, pt = parse_args_with_passthrough(
            [
                "--mode",
                "read-only",
                "--skip-git-repo-check",
                "-",
            ]
        )
        assert parsed.skip_git_repo_check is True
        assert pt == []

    def test_skip_git_repo_check_default_false(self):
        parsed, _ = parse_args_with_passthrough(["-"])
        assert parsed.skip_git_repo_check is False

    def test_empty_argv(self):
        parsed, pt = parse_args_with_passthrough([])
        assert parsed.mode == "read-only"
        assert pt == []

    def test_wrapper_flag_value_missing_at_end(self):
        """Wrapper flag expecting a value at end of argv gets empty string → argparse error."""
        with pytest.raises(SystemExit):
            parse_args_with_passthrough(["--timeout"])

    def test_double_dash_then_stdin_marker_empty_passthrough(self):
        _, pt = parse_args_with_passthrough(["--mode", "read-only", "--", "-"])
        assert pt == []

    def test_wrapper_flags_after_double_dash_become_passthrough(self):
        parsed, pt = parse_args_with_passthrough(
            [
                "--mode",
                "read-only",
                "--",
                "--web-search",
                "--resume",
                "-",
            ]
        )
        assert parsed.mode == "read-only"
        assert parsed.web_search is False
        assert parsed.resume is False
        assert pt == ["--web-search", "--resume"]

    def test_interleaved_passthrough_between_wrapper_flags(self):
        parsed, pt = parse_args_with_passthrough(
            [
                "--model",
                "o3",
                "--mode",
                "write",
                "-c",
                "temperature=0",
                "-",
            ]
        )
        assert parsed.mode == "write"
        assert pt == ["--model", "o3", "-c", "temperature=0"]


# ========== Parallel Agent Tracking ==========


@pytest.fixture(autouse=False)
def isolated_pid_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[str, None, None]:
    """Redirect PID_TRACKING_DIR to an isolated temp dir for each test."""
    pid_dir = str(tmp_path / "codex-agent-pids")
    monkeypatch.setattr(_mod, "PID_TRACKING_DIR", pid_dir)
    monkeypatch.setattr(_mod, "_pid_file_path", None)
    yield pid_dir


class TestParallelAgentTracking:
    def test_ensure_pid_dir_creates(self, isolated_pid_dir: str) -> None:
        assert not os.path.exists(isolated_pid_dir)
        _ensure_pid_dir()
        assert os.path.isdir(isolated_pid_dir)

    def test_ensure_pid_dir_idempotent(self, isolated_pid_dir: str) -> None:
        _ensure_pid_dir()
        _ensure_pid_dir()
        assert os.path.isdir(isolated_pid_dir)

    def test_is_pid_alive_self(self):
        assert _is_pid_alive(os.getpid()) is True

    def test_is_pid_alive_dead(self):
        assert _is_pid_alive(999999999) is False

    def test_count_active_agents_empty(self, isolated_pid_dir: str) -> None:
        assert _count_active_agents() == 0

    def test_register_creates_pid_file(self, isolated_pid_dir: str) -> None:
        pid_file = _register_agent()
        assert os.path.isfile(pid_file)
        assert str(os.getpid()) in pid_file

    def test_count_active_includes_self(self, isolated_pid_dir: str) -> None:
        _register_agent()
        assert _count_active_agents() == 1

    def test_unregister_removes_pid_file(
        self, isolated_pid_dir: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pid_file = _register_agent()
        monkeypatch.setattr(_mod, "_pid_file_path", pid_file)
        _unregister_agent()
        assert not os.path.exists(pid_file)

    def test_stale_pid_cleaned_on_count(self, isolated_pid_dir: str) -> None:
        _ensure_pid_dir()
        stale_pid = "999999999"
        stale_file = os.path.join(isolated_pid_dir, stale_pid)
        with open(stale_file, "w") as f:
            f.write(stale_pid)
        assert _count_active_agents() == 0
        assert not os.path.exists(stale_file)

    def test_non_numeric_files_ignored(self, isolated_pid_dir: str) -> None:
        _ensure_pid_dir()
        junk = os.path.join(isolated_pid_dir, "not-a-pid")
        with open(junk, "w") as f:
            f.write("junk")
        assert _count_active_agents() == 0
        assert os.path.exists(junk)

    def test_enforce_parallel_limit_allows_under(self, isolated_pid_dir: str) -> None:
        enforce_parallel_limit(6)

    def test_enforce_parallel_limit_blocks_at_limit(self, isolated_pid_dir: str) -> None:
        _ensure_pid_dir()
        for i in range(6):
            fake_pid = str(os.getpid() + 1000 + i)
            fake_file = os.path.join(isolated_pid_dir, fake_pid)
            with open(fake_file, "w") as f:
                f.write(fake_pid)
        with (
            pytest.raises(SystemExit) as exc_info,
            unittest.mock.patch.object(_mod, "_is_pid_alive", return_value=True),
        ):
            enforce_parallel_limit(6)
        assert exc_info.value.code == 2

    def test_enforce_registers_and_sets_atexit(self, isolated_pid_dir: str) -> None:
        enforce_parallel_limit(6)
        assert _mod._pid_file_path is not None
        assert os.path.isfile(_mod._pid_file_path)

    def test_default_max_parallel_is_six(self):
        assert DEFAULT_MAX_PARALLEL == 6

    def test_register_stores_json_metadata(self, isolated_pid_dir: str) -> None:
        import json as _json

        pid_file = _register_agent(mode="read-only")
        with open(pid_file) as f:
            data = _json.load(f)
        assert data["pid"] == os.getpid()
        assert data["mode"] == "read-only"
        assert "started" in data
        assert "started_iso" in data
        assert isinstance(data["started"], float)

    def test_register_default_mode_is_unknown(self, isolated_pid_dir: str) -> None:
        import json as _json

        pid_file = _register_agent()
        with open(pid_file) as f:
            data = _json.load(f)
        assert data["mode"] == "unknown"

    def test_read_pid_metadata_valid_json(self, isolated_pid_dir: str) -> None:
        import json as _json

        _ensure_pid_dir()
        filepath = os.path.join(isolated_pid_dir, "12345")
        with open(filepath, "w") as f:
            _json.dump({"pid": 12345, "mode": "write", "started": 100.0}, f)
        meta = _read_pid_metadata(filepath)
        assert meta["pid"] == 12345
        assert meta["mode"] == "write"

    def test_read_pid_metadata_legacy_plain_text(self, isolated_pid_dir: str) -> None:
        _ensure_pid_dir()
        filepath = os.path.join(isolated_pid_dir, "12345")
        with open(filepath, "w") as f:
            f.write("12345")
        meta = _read_pid_metadata(filepath)
        assert meta == {}

    def test_read_pid_metadata_corrupt_file(self, isolated_pid_dir: str) -> None:
        _ensure_pid_dir()
        filepath = os.path.join(isolated_pid_dir, "12345")
        with open(filepath, "w") as f:
            f.write("not json at all {{{")
        meta = _read_pid_metadata(filepath)
        assert meta == {}

    def test_scan_agents_returns_active_and_stale_count(self, isolated_pid_dir: str) -> None:
        _register_agent(mode="read-only")
        _ensure_pid_dir()
        stale_file = os.path.join(isolated_pid_dir, "999999999")
        with open(stale_file, "w") as f:
            f.write("999999999")
        active, stale_cleaned = _scan_agents()
        assert len(active) == 1
        assert active[0]["pid"] == os.getpid()
        assert stale_cleaned == 1
        assert not os.path.exists(stale_file)

    def test_scan_agents_empty_dir(self, isolated_pid_dir: str) -> None:
        active, stale = _scan_agents()
        assert active == []
        assert stale == 0

    def test_enforce_passes_mode_to_register(self, isolated_pid_dir: str) -> None:
        import json as _json

        enforce_parallel_limit(6, mode="write")
        assert _mod._pid_file_path is not None
        with open(_mod._pid_file_path) as f:
            data = _json.load(f)
        assert data["mode"] == "write"

    def test_enforce_blocked_message_mentions_status(
        self, isolated_pid_dir: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _ensure_pid_dir()
        for i in range(6):
            fake_pid = str(os.getpid() + 1000 + i)
            fake_file = os.path.join(isolated_pid_dir, fake_pid)
            with open(fake_file, "w") as f:
                f.write(fake_pid)
        with (
            pytest.raises(SystemExit),
            unittest.mock.patch.object(_mod, "_is_pid_alive", return_value=True),
        ):
            enforce_parallel_limit(6)
        captured = capsys.readouterr()
        assert "--status" in captured.err


class TestPrintStatus:
    def test_no_agents_tracked(
        self, isolated_pid_dir: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc_info:
            print_status()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "No codex sub-agents tracked" in captured.out

    def test_shows_active_agents(
        self, isolated_pid_dir: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _register_agent(mode="read-only")
        with pytest.raises(SystemExit) as exc_info:
            print_status()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Active agents: 1" in captured.out
        assert f"PID {os.getpid()}" in captured.out
        assert "mode=read-only" in captured.out
        assert "running=" in captured.out

    def test_shows_stale_cleaned(
        self, isolated_pid_dir: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _ensure_pid_dir()
        stale_file = os.path.join(isolated_pid_dir, "999999999")
        with open(stale_file, "w") as f:
            f.write("999999999")
        with pytest.raises(SystemExit) as exc_info:
            print_status()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Stale PIDs cleaned: 1" in captured.out
        assert "Active agents: 0" in captured.out

    def test_shows_limit(self, isolated_pid_dir: str, capsys: pytest.CaptureFixture[str]) -> None:
        _register_agent()
        with pytest.raises(SystemExit):
            print_status()
        captured = capsys.readouterr()
        assert f"Limit: {DEFAULT_MAX_PARALLEL}" in captured.out


class TestStatusFlag:
    def test_status_flag_parsed(self):
        parsed, _ = parse_args_with_passthrough(["--status"])
        assert parsed.status is True

    def test_status_default_false(self):
        parsed, _ = parse_args_with_passthrough(["-"])
        assert parsed.status is False

    def test_status_not_leaked_to_passthrough(self):
        parsed, pt = parse_args_with_passthrough(["--status", "--model", "o3", "-"])
        assert parsed.status is True
        assert "--status" not in pt
        assert pt == ["--model", "o3"]


# ========== _validate_args ==========


def _make_args(**kwargs: Any) -> Any:
    """Build a minimal valid argparse.Namespace for _validate_args."""
    import argparse

    defaults = {
        "timeout": 600,
        "mode": "read-only",
        "resume": False,
        "collision": "high",
        "max_parallel": 6,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestValidateArgs:
    def test_valid_defaults_pass(self):
        _validate_args(_make_args())

    def test_invalid_timeout_exits(self):
        with pytest.raises(SystemExit) as exc_info:
            _validate_args(_make_args(timeout=999))
        assert exc_info.value.code == 2

    def test_all_valid_timeouts_pass(self):
        for t in (300, 600, 1200, 2400):
            _validate_args(_make_args(timeout=t))

    def test_write_mode_invalid_collision_exits(self):
        with pytest.raises(SystemExit) as exc_info:
            _validate_args(_make_args(mode="write", collision="low"))
        assert exc_info.value.code == 2

    def test_write_mode_valid_collision_high_passes(self):
        _validate_args(_make_args(mode="write", collision="high"))

    def test_write_mode_valid_collision_medium_passes(self):
        _validate_args(_make_args(mode="write", collision="medium"))

    def test_write_mode_resume_skips_collision_check(self):
        # --resume bypasses collision validation
        _validate_args(_make_args(mode="write", collision="low", resume=True))

    def test_max_parallel_zero_exits(self):
        with pytest.raises(SystemExit) as exc_info:
            _validate_args(_make_args(max_parallel=0))
        assert exc_info.value.code == 2

    def test_max_parallel_negative_exits(self):
        with pytest.raises(SystemExit) as exc_info:
            _validate_args(_make_args(max_parallel=-1))
        assert exc_info.value.code == 2

    def test_max_parallel_one_passes(self):
        _validate_args(_make_args(max_parallel=1))

    def test_max_parallel_above_default_warns_but_continues(
        self, capsys: pytest.CaptureFixture[str]
    ):
        _validate_args(_make_args(max_parallel=10))
        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "10" in captured.err

    def test_read_only_any_collision_passes(self):
        for col in ("high", "medium"):
            _validate_args(_make_args(mode="read-only", collision=col))


# ========== _validate_prompt ==========


class TestValidatePrompt:
    def test_empty_prompt_exits(self, tmp_path: Path):
        empty = tmp_path / "empty.txt"
        empty.write_text("")
        with pytest.raises(SystemExit) as exc_info:
            _validate_prompt(str(empty))
        assert exc_info.value.code == 2

    def test_nonempty_prompt_passes(self, tmp_path: Path):
        f = tmp_path / "prompt.txt"
        f.write_text("do something")
        _validate_prompt(str(f))

    def test_large_prompt_warns_but_continues(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        f = tmp_path / "big.txt"
        f.write_text("x" * 60000)
        _validate_prompt(str(f))  # must not raise
        captured = capsys.readouterr()
        assert "WARNING" in captured.err

    def test_prompt_at_max_passes_without_warning(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        import run_codex as _m

        f = tmp_path / "prompt.txt"
        f.write_text("x" * _m.MAX_PROMPT_CHARS)
        _validate_prompt(str(f))
        captured = capsys.readouterr()
        assert "WARNING" not in captured.err


# ========== build_prompt_file ==========


class TestBuildPromptFile:
    def test_stdin_only_written(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        import io

        monkeypatch.setattr(sys, "stdin", io.StringIO("hello from stdin"))
        result = build_prompt_file(str(tmp_path), None)
        assert Path(result).read_text() == "hello from stdin"

    def test_review_prompt_prepended(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        import io

        review = tmp_path / "review.md"
        review.write_text("# Review\nDo a review.")
        monkeypatch.setattr(sys, "stdin", io.StringIO("extra context"))
        result = build_prompt_file(str(tmp_path), str(review))
        content = Path(result).read_text()
        assert content.startswith("# Review\nDo a review.")
        assert "--- Additional context from host agent ---" in content
        assert "extra context" in content

    def test_review_prompt_separator_before_stdin(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        import io

        review = tmp_path / "review.md"
        review.write_text("REVIEW_CONTENT")
        monkeypatch.setattr(sys, "stdin", io.StringIO("STDIN_CONTENT"))
        result = build_prompt_file(str(tmp_path), str(review))
        content = Path(result).read_text()
        sep_pos = content.index("--- Additional context from host agent ---")
        stdin_pos = content.index("STDIN_CONTENT")
        assert sep_pos < stdin_pos

    def test_missing_review_prompt_exits(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        import io

        monkeypatch.setattr(sys, "stdin", io.StringIO("context"))
        with pytest.raises(SystemExit) as exc_info:
            build_prompt_file(str(tmp_path), "/nonexistent/path/review.md")
        assert exc_info.value.code == 2

    def test_tty_stdin_skipped(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        import io

        tty_stdin = io.StringIO("")
        tty_stdin.isatty = lambda: True  # type: ignore[method-assign]
        monkeypatch.setattr(sys, "stdin", tty_stdin)
        result = build_prompt_file(str(tmp_path), None)
        assert Path(result).read_text() == ""

    def test_prompt_file_in_tmpdir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        import io

        monkeypatch.setattr(sys, "stdin", io.StringIO("hi"))
        result = build_prompt_file(str(tmp_path), None)
        assert Path(result).parent == tmp_path
        assert Path(result).name == "prompt.txt"


# ========== setup_worktree ==========


class TestSetupWorktree:
    def test_read_only_returns_none(self):
        wt_dir, wt_branch, wt_id = setup_worktree("high", "read-only")
        assert wt_dir is None
        assert wt_branch is None
        assert wt_id is None

    def test_write_high_returns_none(self):
        wt_dir, wt_branch, wt_id = setup_worktree("high", "write")
        assert wt_dir is None

    def test_medium_read_only_returns_none(self):
        wt_dir, wt_branch, wt_id = setup_worktree("medium", "read-only")
        assert wt_dir is None

    def test_medium_write_calls_git(self, monkeypatch: pytest.MonkeyPatch):
        import subprocess as sp

        fake_result = unittest.mock.MagicMock()
        fake_result.returncode = 0
        monkeypatch.setattr(sp, "run", lambda *a, **kw: fake_result)
        wt_dir, wt_branch, wt_id = setup_worktree("medium", "write")
        assert wt_dir is not None
        assert wt_branch is not None
        assert wt_id is not None
        assert "codex-wt-" in wt_dir

    def test_medium_write_git_failure_exits(self, monkeypatch: pytest.MonkeyPatch):
        import subprocess as sp

        fake_result = unittest.mock.MagicMock()
        fake_result.returncode = 1
        fake_result.stdout = ""
        fake_result.stderr = "fatal: not a git repo"
        monkeypatch.setattr(sp, "run", lambda *a, **kw: fake_result)
        with pytest.raises(SystemExit) as exc_info:
            setup_worktree("medium", "write")
        assert exc_info.value.code == 2

    def test_medium_write_branch_matches_dir(self, monkeypatch: pytest.MonkeyPatch):
        import subprocess as sp

        fake_result = unittest.mock.MagicMock()
        fake_result.returncode = 0
        monkeypatch.setattr(sp, "run", lambda *a, **kw: fake_result)
        wt_dir, wt_branch, wt_id = setup_worktree("medium", "write")
        # branch and id both come from the same uuid fragment
        assert wt_dir is not None
        assert wt_branch is not None
        assert wt_branch == wt_id
        assert wt_branch in wt_dir


# ========== _report_exit_error ==========


class TestReportExitError:
    def test_exit_101_rust_panic(self, capsys: pytest.CaptureFixture[str]):
        _report_exit_error(101)
        captured = capsys.readouterr()
        assert "101" in captured.err
        assert "panic" in captured.err.lower() or "Rust" in captured.err

    def test_exit_137_oom(self, capsys: pytest.CaptureFixture[str]):
        _report_exit_error(137)
        captured = capsys.readouterr()
        assert "137" in captured.err
        assert "OOM" in captured.err or "killed" in captured.err.lower()

    def test_exit_143_sigterm(self, capsys: pytest.CaptureFixture[str]):
        _report_exit_error(143)
        captured = capsys.readouterr()
        assert "143" in captured.err
        assert "SIGTERM" in captured.err or "terminated" in captured.err.lower()

    def test_exit_other_generic_message(self, capsys: pytest.CaptureFixture[str]):
        _report_exit_error(42)
        captured = capsys.readouterr()
        assert "42" in captured.err
        assert "ERROR_HANDLING" in captured.err

    def test_exit_zero_no_output(self, capsys: pytest.CaptureFixture[str]):
        # exit code 0 is not passed to _report_exit_error in practice, but it
        # falls through to the generic branch — just ensure it doesn't crash
        _report_exit_error(0)


# ========== _extract_subcommand edge cases ==========


class TestExtractSubcommandEdgeCases:
    def test_boolean_flag_before_review_skips_review(self):
        """Boolean passthrough flags (no '=', no value) cause skip_next=True,
        so the next token is consumed as the flag's value and 'review' is missed."""
        sub, sub_args, rest = _extract_subcommand(["--oss", "review"])
        # --oss sets skip_next, so 'review' is consumed as its value → not extracted
        assert sub is None

    def test_eq_form_boolean_flag_does_not_skip(self):
        """Flags in --flag=value form do NOT set skip_next, so review is found."""
        sub, sub_args, rest = _extract_subcommand(["--model=gpt-4", "review"])
        assert sub == "review"

    def test_uncommitted_flag_does_not_skip_next(self):
        """--uncommitted is explicitly exempted from skip_next, so review after it is found."""
        sub, sub_args, rest = _extract_subcommand(["--uncommitted", "review"])
        assert sub == "review"
