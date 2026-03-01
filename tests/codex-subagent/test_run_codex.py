#!/usr/bin/env python3
"""Unit tests for run_codex.py safety-critical parsing functions."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "codex-subagent", "scripts"))

from run_codex import (
    version_gte,
    scan_for_dangerous_flags,
    _check_sandbox_flag,
    _check_dangerous_flag,
    _is_sandbox_config_override,
    _is_scope_flag,
    _matches_blocked_flag,
    _extract_subcommand,
    _normalize_exit_code,
    build_codex_args,
    parse_args_with_passthrough,
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
        assert _matches_blocked_flag("--output-last-message=/tmp/x", "--output-last-message") is True

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
        scan_for_dangerous_flags([
            "--model", "o3", "--skip-git-repo-check",
            "--output-schema", "/tmp/schema.json",
            "-i", "img.png", "--oss", "-p", "fast",
            "--enable", "streaming",
        ])

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


def _parse_then_scan(argv):
    """Helper: parse argv then run safety scan on resulting passthrough."""
    _, passthrough = parse_args_with_passthrough(argv)
    scan_for_dangerous_flags(passthrough)


class TestBlockedFlagsViaAllPaths:
    """Integration: blocked flags must be caught regardless of delivery path."""

    # --- Path 1: normal passthrough (unrecognized flag, before '-') ---
    @pytest.mark.parametrize("blocked", BLOCKED_FLAG_SAMPLES, ids=[b[0] for b in BLOCKED_FLAG_SAMPLES])
    def test_blocked_via_normal_passthrough(self, blocked):
        argv = ["--mode", "read-only"] + blocked + ["-"]
        with pytest.raises(SystemExit):
            _parse_then_scan(argv)

    # --- Path 2: after '--' separator ---
    @pytest.mark.parametrize("blocked", BLOCKED_FLAG_SAMPLES, ids=[b[0] for b in BLOCKED_FLAG_SAMPLES])
    def test_blocked_via_double_dash(self, blocked):
        argv = ["--mode", "read-only", "--"] + blocked + ["-"]
        with pytest.raises(SystemExit):
            _parse_then_scan(argv)

    # --- Path 3: trailing args after '-' stdin marker ---
    @pytest.mark.parametrize("blocked", BLOCKED_FLAG_SAMPLES, ids=[b[0] for b in BLOCKED_FLAG_SAMPLES])
    def test_blocked_via_trailing_after_stdin(self, blocked):
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
    def test_safe_via_normal_passthrough(self, safe):
        argv = ["--mode", "read-only"] + safe + ["-"]
        _parse_then_scan(argv)  # should not raise

    @pytest.mark.parametrize("safe", SAFE_FLAG_SAMPLES, ids=[s[0] for s in SAFE_FLAG_SAMPLES])
    def test_safe_via_double_dash(self, safe):
        argv = ["--mode", "read-only", "--"] + safe + ["-"]
        _parse_then_scan(argv)  # should not raise

    @pytest.mark.parametrize("safe", SAFE_FLAG_SAMPLES, ids=[s[0] for s in SAFE_FLAG_SAMPLES])
    def test_safe_via_trailing_after_stdin(self, safe):
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
            mode="read-only", resume=False, persist=False, web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt", worktree_dir=None, passthrough=[],
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
            mode="write", resume=False, persist=False, web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt", worktree_dir=None, passthrough=[],
        )
        assert "--full-auto" in args
        assert "--sandbox" in args
        idx = args.index("--sandbox")
        assert args[idx + 1] == "workspace-write"

    def test_persist_no_ephemeral(self):
        args = build_codex_args(
            mode="read-only", resume=False, persist=True, web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt", worktree_dir=None, passthrough=[],
        )
        assert "--ephemeral" not in args

    def test_web_search(self):
        args = build_codex_args(
            mode="read-only", resume=False, persist=False, web_search=True,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt", worktree_dir=None, passthrough=[],
        )
        assert "-c" in args
        idx = args.index("-c")
        assert args[idx + 1] == "web_search_request=true"

    def test_worktree_cd(self):
        args = build_codex_args(
            mode="write", resume=False, persist=False, web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt", worktree_dir="/tmp/wt-123", passthrough=[],
        )
        assert "--cd" in args
        idx = args.index("--cd")
        assert args[idx + 1] == "/tmp/wt-123"

    def test_resume(self):
        args = build_codex_args(
            mode="read-only", resume=True, persist=False, web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt", worktree_dir=None, passthrough=[],
        )
        assert args[:3] == ["exec", "resume", "--last"]
        assert "--sandbox" not in args
        assert "-o" in args
        idx = args.index("-o")
        assert args[idx + 1] == "/tmp/r.txt"

    def test_review_subcommand(self):
        args = build_codex_args(
            mode="read-only", resume=False, persist=False, web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt", worktree_dir=None,
            passthrough=["review", "--uncommitted"],
        )
        assert args[0] == "exec"
        assert args[1] == "review"
        assert "--uncommitted" in args

    def test_color_always_present(self):
        args = build_codex_args(
            mode="read-only", resume=False, persist=False, web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt", worktree_dir=None, passthrough=[],
        )
        assert "--color" in args
        idx = args.index("--color")
        assert args[idx + 1] == "never"

    def test_passthrough_appended(self):
        args = build_codex_args(
            mode="read-only", resume=False, persist=False, web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt", worktree_dir=None,
            passthrough=["--model", "o3"],
        )
        assert "--model" in args
        assert "o3" in args

    def test_skip_git_repo_check_appended(self):
        args = build_codex_args(
            mode="read-only", resume=False, persist=False, web_search=False,
            skip_git_repo_check=True,
            result_file="/tmp/r.txt", worktree_dir=None, passthrough=[],
        )
        assert "--skip-git-repo-check" in args

    def test_skip_git_repo_check_not_appended_when_false(self):
        args = build_codex_args(
            mode="read-only", resume=False, persist=False, web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt", worktree_dir=None, passthrough=[],
        )
        assert "--skip-git-repo-check" not in args

    def test_skip_git_repo_check_with_resume(self):
        args = build_codex_args(
            mode="read-only", resume=True, persist=False, web_search=False,
            skip_git_repo_check=True,
            result_file="/tmp/r.txt", worktree_dir=None, passthrough=[],
        )
        assert "--skip-git-repo-check" in args

    def test_resume_still_appends_passthrough(self):
        args = build_codex_args(
            mode="read-only", resume=True, persist=False, web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt", worktree_dir=None,
            passthrough=["--model", "o3"],
        )
        assert "--model" in args
        assert "o3" in args

    def test_write_mode_has_ephemeral(self):
        args = build_codex_args(
            mode="write", resume=False, persist=False, web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt", worktree_dir=None, passthrough=[],
        )
        assert "--ephemeral" in args

    def test_review_base_subcommand(self):
        args = build_codex_args(
            mode="read-only", resume=False, persist=False, web_search=False,
            skip_git_repo_check=False,
            result_file="/tmp/r.txt", worktree_dir=None,
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
        parsed, pt = parse_args_with_passthrough(
            ["--mode", "write", "--model", "gpt-4", "-"]
        )
        assert parsed.mode == "write"
        assert pt == ["--model", "gpt-4"]

    def test_stdin_marker_stops_parsing(self):
        _, pt = parse_args_with_passthrough(
            ["--mode", "read-only", "-", "--extra"]
        )
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

    def test_all_wrapper_flags(self):
        parsed, passthrough = parse_args_with_passthrough([
            "--mode", "write", "--collision", "medium", "--timeout", "1200",
            "--web-search", "--resume", "--persist",
            "--skip-git-repo-check",
            "--review-prompt", "/tmp/p.md", "-",
        ])
        assert parsed.mode == "write"
        assert parsed.collision == "medium"
        assert parsed.timeout == 1200
        assert parsed.web_search is True
        assert parsed.resume is True
        assert parsed.persist is True
        assert parsed.skip_git_repo_check is True
        assert parsed.review_prompt == "/tmp/p.md"
        assert passthrough == []

    def test_mixed_wrapper_and_passthrough(self):
        parsed, pt = parse_args_with_passthrough([
            "--mode", "read-only", "review", "--uncommitted", "-",
        ])
        assert parsed.mode == "read-only"
        assert pt == ["review", "--uncommitted"]

    def test_double_dash_routes_to_passthrough(self):
        parsed, pt = parse_args_with_passthrough([
            "--mode", "read-only", "--", "--skip-git-repo-check", "-",
        ])
        assert parsed.mode == "read-only"
        assert pt == ["--skip-git-repo-check"]

    def test_double_dash_does_not_leak_into_passthrough(self):
        """The literal '--' must NOT appear in passthrough args."""
        _, pt = parse_args_with_passthrough([
            "--mode", "read-only", "--", "-m", "o3", "-",
        ])
        assert "--" not in pt
        assert pt == ["-m", "o3"]

    def test_double_dash_multiple_passthrough_flags(self):
        _, pt = parse_args_with_passthrough([
            "--mode", "write", "--", "-m", "o3", "-c", "temperature=0", "-",
        ])
        assert pt == ["-m", "o3", "-c", "temperature=0"]

    def test_double_dash_no_stdin_marker(self):
        """If no '-' after '--', everything goes to passthrough."""
        _, pt = parse_args_with_passthrough([
            "--mode", "read-only", "--", "--model", "o3",
        ])
        assert pt == ["--model", "o3"]

    def test_skip_git_repo_check_as_wrapper_flag(self):
        parsed, pt = parse_args_with_passthrough([
            "--mode", "read-only", "--skip-git-repo-check", "-",
        ])
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
        parsed, pt = parse_args_with_passthrough([
            "--mode", "read-only", "--", "--web-search", "--resume", "-",
        ])
        assert parsed.mode == "read-only"
        assert parsed.web_search is False
        assert parsed.resume is False
        assert pt == ["--web-search", "--resume"]

    def test_interleaved_passthrough_between_wrapper_flags(self):
        parsed, pt = parse_args_with_passthrough([
            "--model", "o3", "--mode", "write", "-c", "temperature=0", "-",
        ])
        assert parsed.mode == "write"
        assert pt == ["--model", "o3", "-c", "temperature=0"]
