"""Tests for read-command auto-approval hook and whitelist patterns.

Validates that:
A. All whitelisted (read) commands are approved regardless of flag order/variations
B. No write commands are ever approved — safety over convenience
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HOOK_SCRIPT = REPO_ROOT / ".claude" / "hooks" / "approve-read-commands.sh"
READ_COMMANDS_JSON = REPO_ROOT / ".claude" / "hooks" / "read-commands.json"
WINDSURF_WHITELIST = REPO_ROOT / "docs" / "windsurf-read-whitelist.md"
SYNC_SCRIPT = REPO_ROOT / "skill-sync" / "scripts" / "sync.py"

# ---------------------------------------------------------------------------
# Load patterns once
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def read_patterns() -> list[dict]:
    return json.loads(READ_COMMANDS_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def windsurf_patterns() -> list[str]:
    """Extract patterns from the Windsurf whitelist markdown code blocks."""
    text = WINDSURF_WHITELIST.read_text(encoding="utf-8")
    patterns = []
    in_block = False
    for line in text.splitlines():
        if line.strip() == "```":
            in_block = not in_block
            continue
        if in_block and line.strip():
            patterns.append(line.strip())
    return patterns


# ---------------------------------------------------------------------------
# Helper: run the hook script with a given command
# ---------------------------------------------------------------------------


def _run_hook(command: str) -> tuple[int, str]:
    """Run the approve-read-commands.sh hook with a simulated tool input.

    Returns (exit_code, stdout).
    """
    tool_input = json.dumps({"tool_input": {"command": command}})
    result = subprocess.run(
        ["bash", str(HOOK_SCRIPT)],
        input=tool_input,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.returncode, result.stdout.strip()


def _glob_to_regex(pattern: str) -> str:
    """Convert a glob pattern (with *) to a regex, same logic as the hook script."""
    escaped = re.sub(r"([.[\^$()+{}|])", r"\\\1", pattern)
    return "^" + escaped.replace("*", ".*") + "$"


# ═══════════════════════════════════════════════════════════════════════════
# DATA FILES INTEGRITY
# ═══════════════════════════════════════════════════════════════════════════


class TestDataFilesIntegrity:
    def test_read_commands_json_is_valid(self, read_patterns):
        assert isinstance(read_patterns, list)
        assert len(read_patterns) > 0

    def test_every_entry_has_skill_and_pattern(self, read_patterns):
        for entry in read_patterns:
            assert "skill" in entry, f"Missing 'skill' in {entry}"
            assert "pattern" in entry, f"Missing 'pattern' in {entry}"
            assert entry["skill"].strip(), f"Empty skill in {entry}"
            assert entry["pattern"].strip(), f"Empty pattern in {entry}"

    def test_hook_script_exists_and_is_executable(self):
        assert HOOK_SCRIPT.exists()
        assert HOOK_SCRIPT.stat().st_mode & 0o111, "Hook script is not executable"

    def test_hook_script_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(HOOK_SCRIPT)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Bash syntax error: {result.stderr}"


# ═══════════════════════════════════════════════════════════════════════════
# WINDSURF WHITELIST CONSISTENCY
# ═══════════════════════════════════════════════════════════════════════════


class TestWindsurfWhitelistConsistency:
    """Ensure windsurf-read-whitelist.md and read-commands.json are in sync."""

    def test_all_json_patterns_in_whitelist(self, read_patterns, windsurf_patterns):
        json_set = {e["pattern"] for e in read_patterns}
        md_set = set(windsurf_patterns)
        missing = json_set - md_set
        assert not missing, f"Patterns in JSON but not in whitelist MD: {missing}"

    def test_all_whitelist_patterns_in_json(self, read_patterns, windsurf_patterns):
        json_set = {e["pattern"] for e in read_patterns}
        md_set = set(windsurf_patterns)
        extra = md_set - json_set
        assert not extra, f"Patterns in whitelist MD but not in JSON: {extra}"


# ═══════════════════════════════════════════════════════════════════════════
# READ COMMANDS — MUST BE APPROVED
# ═══════════════════════════════════════════════════════════════════════════

# Realistic read command invocations: various flag orders, paths, arguments

_READ_COMMANDS = [
    # --- jira-manager ---
    "python3 /home/user/.claude/skills/jira-manager/scripts/fetch_tickets.py --key PROJ-101",
    "python3 /home/user/.claude/skills/jira-manager/scripts/fetch_tickets.py --jql 'status=Done' --format table",
    "python3 /home/user/.claude/skills/jira-manager/scripts/fetch_tickets.py --board-id 123 --filter 'assignee=currentUser()'",
    "python3 /home/user/.claude/skills/jira-manager/scripts/fetch_tickets.py --keys PROJ-1,PROJ-2 --format json --max-results 10",
    "python3 /home/user/.claude/skills/jira-manager/scripts/fetch_tickets.py --children-of PROJ-100",
    "python3 /home/user/.claude/skills/jira-manager/scripts/fetch_tickets.py --boards",
    "python3 /home/user/.claude/skills/jira-manager/scripts/discover_fields.py --all --apply",
    "python3 /home/user/.claude/skills/jira-manager/scripts/discover_fields.py --search QBR",
    "python3 /home/user/.claude/skills/jira-manager/scripts/discover_fields.py --fields-for-type epic",
    "python3 /home/user/.claude/skills/jira-manager/scripts/diff_tickets.py --manifest",
    "python3 /home/user/.claude/skills/jira-manager/scripts/validate_estimates.py --epic PROJ-100",
    "python3 /home/user/.claude/skills/jira-manager/scripts/jira_setup_env.py",
    # --- bitbucket-manager ---
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/bb_preflight.py",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/bb_preflight.py --skip-connectivity",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/pr_get.py --pr 42",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/pr_get.py --pr 42 --format json",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/pr_list.py --state OPEN",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/pr_list.py --state MERGED --author jane --max-results 20",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/pr_list.py --branch feature/login --format json",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/pr_comments.py --pr 42",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/pr_comments.py --pr 42 43 44 --status unresolved --has-replies",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/pr_checks.py --pr 42",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/pr_checks.py --pr 42 --format json",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/build_status.py --commit abc123",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/build_status.py --branch main",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/pr_jira.py --pr 42",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/pr_jira.py --pr 42 --format json",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/repo_list.py",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/repo_list.py --name api --max-results 100",
    # --- jenkins-manager ---
    "python3 /home/user/.claude/skills/jenkins-manager/scripts/jenkins_preflight.py",
    "python3 /home/user/.claude/skills/jenkins-manager/scripts/jenkins_preflight.py --skip-connectivity",
    "python3 /home/user/.claude/skills/jenkins-manager/scripts/get_status.py",
    "python3 /home/user/.claude/skills/jenkins-manager/scripts/get_status.py --build 1094 --watch --interval 30",
    "python3 /home/user/.claude/skills/jenkins-manager/scripts/get_status.py --folder MyFolder --job my-service --branch main --format json",
    "python3 /home/user/.claude/skills/jenkins-manager/scripts/get_logs.py --tail 50 --grep ERROR",
    "python3 /home/user/.claude/skills/jenkins-manager/scripts/get_logs.py --build 142 --tail 0",
    "python3 /home/user/.claude/skills/jenkins-manager/scripts/get_test_results.py --failures-only",
    "python3 /home/user/.claude/skills/jenkins-manager/scripts/get_test_results.py --build 142 --format json",
    "python3 /home/user/.claude/skills/jenkins-manager/scripts/get_changesets.py --build 142 --format json",
    "python3 /home/user/.claude/skills/jenkins-manager/scripts/get_queue_item.py --queue-id 12345",
    "python3 /home/user/.claude/skills/jenkins-manager/scripts/list_folders.py",
    "python3 /home/user/.claude/skills/jenkins-manager/scripts/list_folders.py --format json",
    "python3 /home/user/.claude/skills/jenkins-manager/scripts/list_jobs.py --folder MyFolder --name my-service",
    # --- eks-pod-ops ---
    "python3 /home/user/.claude/skills/eks-pod-ops/scripts/eks_preflight.py",
    "python3 /home/user/.claude/skills/eks-pod-ops/scripts/eks_preflight.py --env stg",
    "python3 /home/user/.claude/skills/eks-pod-ops/scripts/eks_ops.py pods --env stg --service my-service",
    "python3 /home/user/.claude/skills/eks-pod-ops/scripts/eks_ops.py pods --env stg --all",
    "python3 /home/user/.claude/skills/eks-pod-ops/scripts/eks_ops.py pods --env stg --service my-service --describe",
    "python3 /home/user/.claude/skills/eks-pod-ops/scripts/eks_ops.py logs --env stg --service my-service",
    "python3 /home/user/.claude/skills/eks-pod-ops/scripts/eks_ops.py logs --env stg --service my-service --tail 500 --since 1h",
    "python3 /home/user/.claude/skills/eks-pod-ops/scripts/eks_ops.py logs --env stg --service my-service --previous",
    "python3 /home/user/.claude/skills/eks-pod-ops/scripts/eks_ops.py logs --env stg --service my-service --all-pods --follow",
    "python3 /home/user/.claude/skills/eks-pod-ops/scripts/eks_ops.py logs --env stg --pod my-service-abc123 --tail 200",
    # --- sbt-build-test ---
    "bash /home/user/.claude/skills/sbt-build-test/scripts/sbt_status.sh /path/to/service",
    "bash /home/user/.claude/skills/sbt-build-test/scripts/sbt_status.sh /path/to/service --workspace",
    "bash /home/user/.claude/skills/sbt-build-test/scripts/sbt_status.sh /path/to/service --plan-change /path/to/commons",
    "bash /home/user/.claude/skills/sbt-build-test/scripts/sbt_status.sh /path/to/service --verify platform-commons --json",
    # --- confluence-publisher ---
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/validate_manifest.py",
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/verify_hierarchy.py",
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/discover_pages.py",
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/diff_pages.py --file README.md",
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/diff_pages.py --all --summary",
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/diff_pages.py --all --output /tmp/diff.txt",
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/diff_versions.py --page 1079706804 --from-version 56",
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/diff_versions.py --page 1079706804 --from-version 56 --to-version 59 --output /tmp/diff.txt",
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/page_versions.py --page 1079706804 --list",
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/page_versions.py --page 1079706804 --list --limit 50",
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/page_versions.py --page 1079706804 --fetch 56 --output /tmp/v56.html",
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/page_versions.py --page 1079706804 --fetch latest --text --output /tmp/latest.txt",
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/confluence_setup_env.py",
    # --- codebase-analyzer ---
    "python3 /home/user/.claude/skills/codebase-analyzer/scripts/analyze.py --path . --output terminal",
    "python3 /home/user/.claude/skills/codebase-analyzer/scripts/analyze.py --path /repo --output json --sections summary,languages",
    "python3 /home/user/.claude/skills/codebase-analyzer/scripts/analyze.py --path /repo --output markdown --config custom.yaml",
    "python3 /home/user/.claude/skills/codebase-analyzer/scripts/analyzer_setup_env.py",
    # --- review-prompts ---
    "python3 /home/user/.claude/skills/review-prompts/scripts/build-prompt.py security",
    "python3 /home/user/.claude/skills/review-prompts/scripts/build-prompt.py code-review -o /tmp/cr.md",
    "python3 /home/user/.claude/skills/review-prompts/scripts/build-prompt.py --list",
    # --- codex-subagent ---
    "python3 /home/user/.claude/skills/codex-subagent/scripts/run_codex.py --mode read-only -",
    "python3 /home/user/.claude/skills/codex-subagent/scripts/run_codex.py --mode read-only --web-search -",
    "python3 /home/user/.claude/skills/codex-subagent/scripts/run_codex.py --mode read-only --review-prompt /tmp/sec.md -",
    "python3 /home/user/.claude/skills/codex-subagent/scripts/run_codex.py --mode read-only --timeout 300 -",
    "python3 /home/user/.claude/skills/codex-subagent/scripts/run_codex.py --status",
]


class TestReadCommandsApproved:
    """Every read command must be approved by the hook script."""

    @pytest.mark.parametrize("command", _READ_COMMANDS, ids=lambda c: c.split("/")[-1][:60])
    def test_read_command_approved(self, command):
        exit_code, stdout = _run_hook(command)
        assert exit_code == 0, f"Read command NOT approved (exit {exit_code}): {command}"
        assert '"approve"' in stdout, f"Missing approve decision for: {command}"


# Also test with different base paths (user-level vs project-level)
_PATH_VARIANTS = [
    "/home/user/.claude/skills/",
    "/home/user/myproject/.claude/skills/",
    "/Users/dev/.claude/skills/",
    "/tmp/test-project/.windsurf/skills/",
    "/home/user/.codeium/windsurf/skills/",
]


class TestReadCommandsWithDifferentPaths:
    """Read commands should be approved regardless of the skill install path."""

    @pytest.mark.parametrize("base_path", _PATH_VARIANTS)
    def test_fetch_tickets_any_path(self, base_path):
        cmd = f"python3 {base_path}jira-manager/scripts/fetch_tickets.py --key PROJ-101"
        exit_code, stdout = _run_hook(cmd)
        assert exit_code == 0, f"Not approved with path {base_path}: {cmd}"

    @pytest.mark.parametrize("base_path", _PATH_VARIANTS)
    def test_get_status_any_path(self, base_path):
        cmd = f"python3 {base_path}jenkins-manager/scripts/get_status.py --build 42"
        exit_code, stdout = _run_hook(cmd)
        assert exit_code == 0, f"Not approved with path {base_path}: {cmd}"


# ═══════════════════════════════════════════════════════════════════════════
# WRITE COMMANDS — MUST NEVER BE APPROVED
# ═══════════════════════════════════════════════════════════════════════════

_WRITE_COMMANDS = [
    # --- jira-manager ---
    "python3 /home/user/.claude/skills/jira-manager/scripts/create_ticket.py --type story --summary Title",
    "python3 /home/user/.claude/skills/jira-manager/scripts/create_ticket.py --type sub-task --summary Sub --parent PROJ-101",
    "python3 /home/user/.claude/skills/jira-manager/scripts/bulk_create.py --source tickets.md --epic PROJ-100 --dry-run",
    "python3 /home/user/.claude/skills/jira-manager/scripts/update_ticket.py --key PROJ-101 --summary New --status Done",
    "python3 /home/user/.claude/skills/jira-manager/scripts/bulk_update.py --tickets PROJ-1,PROJ-2 --status Done --confirm",
    "python3 /home/user/.claude/skills/jira-manager/scripts/delete_ticket.py --key PROJ-110 --confirm",
    "python3 /home/user/.claude/skills/jira-manager/scripts/delete_ticket.py --key PROJ-110 --dry-run",
    # --- bitbucket-manager ---
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/pr_create.py --title Add --source feature/x --dry-run",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/pr_create.py --title Add --source feature/x --destination main",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/pr_update.py --pr 42 --title New",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/pr_merge.py --pr 42 --dry-run",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/pr_merge.py --pr 42 --strategy squash",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/pr_decline.py --pr 42",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/pr_decline.py --pr 42 --dry-run",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/pr_comment.py --pr 42 --body LGTM",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/pr_comment.py --pr 42 --body Fix --file src/app.py --line 25",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/pr_comment.py --pr 42 --edit 12345 --body Updated",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/pr_comment.py --pr 42 --delete 12345",
    "python3 /home/user/.claude/skills/bitbucket-manager/scripts/pr_comment.py --pr 42 --resolve 12345",
    # --- jenkins-manager ---
    "python3 /home/user/.claude/skills/jenkins-manager/scripts/trigger_build.py --dry-run",
    "python3 /home/user/.claude/skills/jenkins-manager/scripts/trigger_build.py --folder F --job J --branch main",
    "python3 /home/user/.claude/skills/jenkins-manager/scripts/trigger_build.py --parameters ENV=staging",
    # --- eks-pod-ops ---
    "python3 /home/user/.claude/skills/eks-pod-ops/scripts/eks_ops.py exec --env dev --service my-service -- ls /app",
    "python3 /home/user/.claude/skills/eks-pod-ops/scripts/eks_ops.py exec --env stg --service my-service -- env | grep HEAP",
    "python3 /home/user/.claude/skills/eks-pod-ops/scripts/eks_ops.py restart --env dev --service my-service",
    "python3 /home/user/.claude/skills/eks-pod-ops/scripts/eks_ops.py restart --env dev --service my-service --watch",
    # --- sbt-build-test ---
    "bash /home/user/.claude/skills/sbt-build-test/scripts/sbt_build.sh /path/to/service -- compile",
    "bash /home/user/.claude/skills/sbt-build-test/scripts/sbt_build.sh /path/to/service -- test",
    "bash /home/user/.claude/skills/sbt-build-test/scripts/sbt_build.sh --all --auto-publish-deps -- compile",
    "bash /home/user/.claude/skills/sbt-build-test/scripts/sbt_refresh.sh /path/to/service --publish-upstreams --clean-target --rebuild",
    "bash /home/user/.claude/skills/sbt-build-test/scripts/sbt_refresh.sh /path/to/service --dry-run",
    "bash /home/user/.claude/skills/sbt-build-test/scripts/sbt_reset.sh",
    "bash /home/user/.claude/skills/sbt-build-test/scripts/sbt_reset.sh --local-only",
    # --- confluence-publisher ---
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/publish_page.py --file README.md --title Docs --mode create",
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/publish_page.py --file doc.md --title Doc --mode update --page-id 123",
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/delete_page.py --file old.md",
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/delete_page.py --page-id 123456 --dry-run",
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/surgical_edit.py --page 123 --find old --replace new",
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/surgical_edit.py --page 123 --replacements edits.json --dry-run",
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/replace_element.py --page 123 --heading Phases --element table --output /tmp/t.html",
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/replace_element.py --page 123 --old /tmp/t.html --new /tmp/t2.html",
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/export_pages.py --manifest",
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/export_pages.py --tree --dry-run",
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/page_versions.py --page 123 --revert 56",
    "python3 /home/user/.claude/skills/confluence-publisher/scripts/page_versions.py --page 123 --revert 56 --confirm",
    # --- skill-creator ---
    "python3 /home/user/.claude/skills/skill-creator/scripts/init_skill.py my-new-skill --path .",
    # --- skill-sync ---
    "python3 /home/user/.claude/skills/skill-sync/scripts/sync.py --source . --level user --targets all",
    # --- codex-subagent ---
    "python3 /home/user/.claude/skills/codex-subagent/scripts/run_codex.py --mode write --collision high -",
    "python3 /home/user/.claude/skills/codex-subagent/scripts/run_codex.py --mode write --collision medium -",
]


class TestWriteCommandsRejected:
    """No write command must ever be approved by the hook."""

    @pytest.mark.parametrize("command", _WRITE_COMMANDS, ids=lambda c: c.split("/")[-1][:60])
    def test_write_command_rejected(self, command):
        exit_code, stdout = _run_hook(command)
        assert exit_code != 0, f"WRITE command was APPROVED (DANGEROUS): {command}"
        assert '"approve"' not in stdout, f"Approve decision for write cmd: {command}"


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASES — TRICKY COMMANDS THAT MUST BE CORRECTLY CLASSIFIED
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Commands where read/write distinction depends on subcommand or flags."""

    # eks_ops.py: pods=read, logs=read, exec=write, restart=write
    def test_eks_pods_is_read(self):
        cmd = "python3 /path/to/eks-pod-ops/scripts/eks_ops.py pods --env prod --all"
        assert _run_hook(cmd)[0] == 0

    def test_eks_logs_is_read(self):
        cmd = "python3 /path/to/eks-pod-ops/scripts/eks_ops.py logs --env prod --service x"
        assert _run_hook(cmd)[0] == 0

    def test_eks_exec_is_write(self):
        cmd = "python3 /path/to/eks-pod-ops/scripts/eks_ops.py exec --env prod --service x -- ls"
        assert _run_hook(cmd)[0] != 0

    def test_eks_restart_is_write(self):
        cmd = "python3 /path/to/eks-pod-ops/scripts/eks_ops.py restart --env prod --service x"
        assert _run_hook(cmd)[0] != 0

    # page_versions.py: --list=read, --fetch=read, --revert=write
    def test_page_versions_list_is_read(self):
        cmd = "python3 /path/to/confluence-publisher/scripts/page_versions.py --page 123 --list"
        assert _run_hook(cmd)[0] == 0

    def test_page_versions_fetch_is_read(self):
        cmd = "python3 /path/to/confluence-publisher/scripts/page_versions.py --page 123 --fetch 56 --output /tmp/x"
        assert _run_hook(cmd)[0] == 0

    def test_page_versions_revert_is_write(self):
        cmd = "python3 /path/to/confluence-publisher/scripts/page_versions.py --page 123 --revert 56"
        assert _run_hook(cmd)[0] != 0

    def test_page_versions_revert_confirm_is_write(self):
        cmd = "python3 /path/to/confluence-publisher/scripts/page_versions.py --page 123 --revert 56 --confirm"
        assert _run_hook(cmd)[0] != 0

    # run_codex.py: --mode read-only=read, --mode write=write, --status=read
    def test_codex_read_only_is_read(self):
        cmd = "python3 /path/to/codex-subagent/scripts/run_codex.py --mode read-only -"
        assert _run_hook(cmd)[0] == 0

    def test_codex_status_is_read(self):
        cmd = "python3 /path/to/codex-subagent/scripts/run_codex.py --status"
        assert _run_hook(cmd)[0] == 0

    def test_codex_write_is_write(self):
        cmd = "python3 /path/to/codex-subagent/scripts/run_codex.py --mode write --collision high -"
        assert _run_hook(cmd)[0] != 0

    # pr_comments.py (plural, view) is read; pr_comment.py (singular, action) is write
    def test_pr_comments_view_is_read(self):
        cmd = "python3 /path/to/bitbucket-manager/scripts/pr_comments.py --pr 42"
        assert _run_hook(cmd)[0] == 0

    def test_pr_comment_post_is_write(self):
        cmd = "python3 /path/to/bitbucket-manager/scripts/pr_comment.py --pr 42 --body LGTM"
        assert _run_hook(cmd)[0] != 0

    # Ensure script name substring won't cause false positives
    def test_build_status_is_read_not_build(self):
        """build_status.py is read-only; don't confuse with sbt_build.sh."""
        cmd = "python3 /path/to/bitbucket-manager/scripts/build_status.py --branch main"
        assert _run_hook(cmd)[0] == 0

    def test_sbt_build_is_write(self):
        cmd = "bash /path/to/sbt-build-test/scripts/sbt_build.sh /path -- compile"
        assert _run_hook(cmd)[0] != 0


# ═══════════════════════════════════════════════════════════════════════════
# INJECTION / BYPASS ATTEMPTS — MUST ALL BE REJECTED
# ═══════════════════════════════════════════════════════════════════════════


class TestSecurityBypass:
    """Attempts to trick the hook into approving a write command."""

    def test_semicolon_injection(self):
        cmd = "python3 /path/to/jira-manager/scripts/fetch_tickets.py --key X; python3 /path/to/jira-manager/scripts/delete_ticket.py --key X --confirm"
        exit_code, _ = _run_hook(cmd)
        assert exit_code != 0, "Semicolon injection was approved"

    def test_pipe_injection(self):
        cmd = "python3 /path/to/jenkins-manager/scripts/get_status.py | python3 /path/to/jenkins-manager/scripts/trigger_build.py"
        exit_code, _ = _run_hook(cmd)
        assert exit_code != 0, "Pipe injection was approved"

    def test_and_injection(self):
        cmd = "python3 /path/to/bitbucket-manager/scripts/pr_get.py --pr 42 && python3 /path/to/bitbucket-manager/scripts/pr_merge.py --pr 42"
        exit_code, _ = _run_hook(cmd)
        assert exit_code != 0, "&& injection was approved"

    def test_backtick_injection(self):
        cmd = "python3 /path/to/jira-manager/scripts/fetch_tickets.py --key `rm -rf /`"
        # Backticks are shell injection vectors — rejected by the operator check
        # even though the base command is a read. Defense in depth: reject first,
        # let the sandbox handle anything that slips through.
        exit_code, _ = _run_hook(cmd)
        assert exit_code != 0, "Backtick injection was approved"

    def test_empty_command(self):
        exit_code, _ = _run_hook("")
        assert exit_code != 0

    def test_no_tool_input(self):
        result = subprocess.run(
            ["bash", str(HOOK_SCRIPT)],
            input="{}",
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0

    def test_null_command(self):
        result = subprocess.run(
            ["bash", str(HOOK_SCRIPT)],
            input='{"tool_input": {"command": null}}',
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0


# ═══════════════════════════════════════════════════════════════════════════
# PATTERN REGEX CORRECTNESS
# ═══════════════════════════════════════════════════════════════════════════


class TestPatternRegex:
    """Verify that glob-to-regex conversion produces correct patterns."""

    def test_star_becomes_dotstar(self):
        regex = _glob_to_regex("*/scripts/fetch_tickets.py *")
        assert re.match(regex, "/any/path/scripts/fetch_tickets.py --key X")
        assert not re.match(regex, "/any/path/scripts/create_ticket.py --key X")

    def test_dots_are_escaped(self):
        regex = _glob_to_regex("*/scripts/build-prompt.py *")
        # The dot in .py must be literal
        assert re.match(regex, "/path/scripts/build-prompt.py --list")
        assert not re.match(regex, "/path/scripts/build-promptXpy --list")

    def test_subcommand_patterns(self):
        pods_regex = _glob_to_regex("*/scripts/eks_ops.py pods *")
        assert re.match(pods_regex, "/p/scripts/eks_ops.py pods --env stg")
        assert not re.match(pods_regex, "/p/scripts/eks_ops.py exec --env stg")
        assert not re.match(pods_regex, "/p/scripts/eks_ops.py restart --env stg")

    def test_flag_patterns(self):
        list_regex = _glob_to_regex("*/scripts/page_versions.py --list *")
        assert re.match(list_regex, "/p/scripts/page_versions.py --list --limit 50")
        assert not re.match(list_regex, "/p/scripts/page_versions.py --revert 56")

    def test_no_args_pattern(self):
        """Patterns ending without * should match exact (e.g., setup scripts)."""
        regex = _glob_to_regex("*/scripts/jira_setup_env.py")
        assert re.match(regex, "/path/scripts/jira_setup_env.py")
        # Should NOT match with extra args (no trailing *)
        assert not re.match(regex, "/path/scripts/jira_setup_env.py --flag")
