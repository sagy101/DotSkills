#!/usr/bin/env python3
"""End-to-end test for bitbucket-manager skill.

Exercises every operation script exactly as documented in SKILL.md.
Creates a temporary branch + PR, runs all operations, then cleans up.

Requirements:
  - Run from a git repo with a Bitbucket Cloud remote
  - BITBUCKET_EMAIL and BITBUCKET_TOKEN set (or in .env)
  - .bitbucket.json configured with workspace

Usage:
  python3 tests/bitbucket-manager/test_e2e.py
  python3 tests/bitbucket-manager/test_e2e.py --keep   # skip cleanup (for debugging)
"""

import contextlib
import re
import subprocess
import sys
import time
from pathlib import Path

# Scripts live in bitbucket-manager/scripts/ relative to repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT_DIR = _REPO_ROOT / "bitbucket-manager" / "scripts"
_PYTHON = sys.executable
_TIMESTAMP = str(int(time.time()))
_BRANCH = f"test/bb-skill-e2e-{_TIMESTAMP}"

_passed = 0
_failed = 0
_skipped = 0
_pr_id = None


def _extract_comment_id(result: subprocess.CompletedProcess) -> str | None:
    """Extract comment ID from 'Comment #NNN' in stdout."""
    for line in result.stdout.splitlines():
        m = re.search(r"Comment #(\d+)", line)
        if m:
            return m.group(1)
    return None


def _run(script: str, *args: str, expect_fail: bool = False) -> subprocess.CompletedProcess:
    """Run a skill script and return the result."""
    cmd = [_PYTHON, str(_SCRIPT_DIR / script), *args]
    return subprocess.run(cmd, capture_output=True, text=True)


def _check(
    name: str,
    result: subprocess.CompletedProcess,
    *,
    expect_exit: int = 0,
    stdout_contains: str | None = None,
    stdout_not_contains: str | None = None,
) -> bool:
    """Evaluate a test step. Returns True if passed."""
    global _passed, _failed

    ok = True
    reasons = []

    if result.returncode != expect_exit:
        ok = False
        reasons.append(f"exit {result.returncode} (expected {expect_exit})")

    if stdout_contains and stdout_contains not in result.stdout:
        ok = False
        reasons.append(f"stdout missing: '{stdout_contains}'")

    if stdout_not_contains and stdout_not_contains in result.stdout:
        ok = False
        reasons.append(f"stdout should not contain: '{stdout_not_contains}'")

    if ok:
        _passed += 1
        # Extract first meaningful line from stdout for context
        first_line = ""
        for line in result.stdout.strip().splitlines():
            if line.strip():
                first_line = line.strip()[:80]
                break
        print(f"[PASS] {name} — {first_line}")
    else:
        _failed += 1
        detail = "; ".join(reasons)
        print(f"[FAIL] {name} — {detail}")
        if result.stderr.strip():
            for line in result.stderr.strip().splitlines()[:5]:
                print(f"       stderr: {line}")
        if result.stdout.strip():
            for line in result.stdout.strip().splitlines()[:5]:
                print(f"       stdout: {line}")

    return ok


def _cleanup() -> None:
    """Delete the remote test branch. Always runs."""
    print()
    try:
        result = subprocess.run(
            ["git", "push", "origin", "--delete", _BRANCH],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"[CLEANUP] Remote branch {_BRANCH} deleted")
        else:
            print(f"[CLEANUP] Could not delete remote branch {_BRANCH}: {result.stderr.strip()}")
    except Exception as e:
        print(f"[CLEANUP] Error deleting remote branch: {e}")

    # Switch back and delete local branch
    with contextlib.suppress(Exception):
        subprocess.run(["git", "checkout", "-"], capture_output=True, text=True)
        subprocess.run(["git", "branch", "-D", _BRANCH], capture_output=True, text=True)
        print(f"[CLEANUP] Local branch {_BRANCH} deleted")


def _test_comments(pr: str, test_file: str) -> None:
    """Test comment posting, threading, display, filters, and bulk resolve."""
    global _skipped

    r = _run("pr_comment.py", "--pr", pr, "--body", "E2E test comment", "--dry-run")
    _check("pr_comment --dry-run", r, stdout_contains="DRY RUN")

    # Post inline comment 1 on the test file (inline comments can be resolved)
    r = _run(
        "pr_comment.py",
        "--pr",
        pr,
        "--body",
        f"E2E root comment 1 {_TIMESTAMP}",
        "--file",
        test_file,
        "--line",
        "3",
    )
    _check("pr_comment (root 1, inline)", r, stdout_contains="posted")
    cid1 = _extract_comment_id(r)

    # Post inline comment 2 on the test file
    r = _run(
        "pr_comment.py",
        "--pr",
        pr,
        "--body",
        f"E2E root comment 2 {_TIMESTAMP}",
        "--file",
        test_file,
        "--line",
        "5",
    )
    _check("pr_comment (root 2, inline)", r, stdout_contains="posted")
    cid2 = _extract_comment_id(r)

    # Post a reply to root comment 1 (creates a thread with replies)
    reply_id = None
    if cid1:
        r = _run(
            "pr_comment.py",
            "--pr",
            pr,
            "--body",
            f"E2E reply to root 1 {_TIMESTAMP}",
            "--parent-id",
            cid1,
        )
        _check("pr_comment (reply)", r, stdout_contains=f"replied to #{cid1}")
        reply_id = _extract_comment_id(r)

    # Threaded display
    r = _run("pr_comments.py", "--pr", pr)
    _check("pr_comments (threaded)", r, stdout_contains=f"E2E root comment 1 {_TIMESTAMP}")
    _check("pr_comments (has summary)", r, stdout_contains="threads")
    _check("pr_comments (has thread header)", r, stdout_contains="--- Thread 1/")
    if reply_id:
        _check("pr_comments (tree connector)", r, stdout_contains="+--")

    r = _run("pr_comments.py", "--pr", pr, "--format", "json")
    _check("pr_comments (json)", r, stdout_contains="E2E root comment")

    # Filters — all threads are unresolved at this point
    r = _run("pr_comments.py", "--pr", pr, "--status", "unresolved")
    _check("pr_comments --status unresolved", r, stdout_contains="UNRESOLVED")

    r = _run("pr_comments.py", "--pr", pr, "--status", "resolved")
    _check("pr_comments --status resolved (empty)", r, stdout_contains="no matching comments")

    # has-replies: root 1 has a reply, root 2 does not
    r = _run("pr_comments.py", "--pr", pr, "--has-replies")
    _check("--has-replies shows root 1", r, stdout_contains=f"E2E root comment 1 {_TIMESTAMP}")
    _check(
        "--has-replies excludes root 2", r, stdout_not_contains=f"E2E root comment 2 {_TIMESTAMP}"
    )

    r = _run("pr_comments.py", "--pr", pr, "--no-replies")
    _check("--no-replies shows root 2", r, stdout_contains=f"E2E root comment 2 {_TIMESTAMP}")
    _check(
        "--no-replies excludes root 1", r, stdout_not_contains=f"E2E root comment 1 {_TIMESTAMP}"
    )

    # Bulk resolve (dry-run then real)
    if cid1 and cid2:
        r = _run("pr_comment.py", "--pr", pr, "--resolve", cid1, cid2, "--dry-run")
        _check("--resolve bulk --dry-run", r, stdout_contains="DRY RUN")

        r = _run("pr_comment.py", "--pr", pr, "--resolve", cid1, cid2)
        _check("--resolve bulk", r, stdout_contains="Resolved 2/2")
    else:
        print("[SKIP] Could not extract comment IDs for bulk resolve test")
        _skipped += 2

    # Verify resolved filter after bulk resolve
    r = _run("pr_comments.py", "--pr", pr, "--status", "resolved")
    _check("--status resolved (after resolve)", r, stdout_contains="RESOLVED")


def main() -> None:
    global _pr_id, _passed, _failed

    import argparse

    parser = argparse.ArgumentParser(description="E2E test for bitbucket-manager")
    parser.add_argument("--keep", action="store_true", help="Skip cleanup (for debugging)")
    args = parser.parse_args()

    print("Bitbucket Manager — E2E Test")
    print(f"Test branch: {_BRANCH}")
    print("=" * 50)
    print()

    # ── 0. Preflight ──────────────────────────────────────────────
    r = _run("bb_preflight.py")
    if not _check("preflight", r):
        print("\nPre-flight failed. Fix issues above before running e2e tests.")
        sys.exit(1)

    # ── 1. Setup: create test branch + push ───────────────────────
    print()
    print("── Setup ──")
    # Save current branch to return later
    current_branch = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True,
        text=True,
    ).stdout.strip()

    result = subprocess.run(
        ["git", "checkout", "-b", _BRANCH],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[FAIL] Could not create branch {_BRANCH}: {result.stderr.strip()}")
        sys.exit(1)

    # Create a test file so the branch has a real diff (needed for inline comments + resolve)
    _TEST_FILE = f"e2e-test-{_TIMESTAMP}.txt"
    _test_file_path = Path.cwd() / _TEST_FILE
    _test_file_path.write_text(
        f"# E2E test file — created by bitbucket-manager e2e test\n"
        f"# Timestamp: {_TIMESTAMP}\n"
        f"line 3\nline 4\nline 5\n"
    )
    subprocess.run(["git", "add", _TEST_FILE], capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "-m", f"test: e2e bitbucket-manager {_TIMESTAMP}"],
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        ["git", "push", "-u", "origin", _BRANCH],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[FAIL] Could not push branch {_BRANCH}: {result.stderr.strip()}")
        # Cleanup local branch
        subprocess.run(["git", "checkout", current_branch], capture_output=True, text=True)
        subprocess.run(["git", "branch", "-D", _BRANCH], capture_output=True, text=True)
        sys.exit(1)

    print(f"[SETUP] Branch {_BRANCH} created and pushed")
    print()

    try:
        # ── 2. pr_create (dry-run first, then real) ──────────────
        print("── PR Operations ──")

        # Dry run — as documented in SKILL.md
        r = _run(
            "pr_create.py",
            "--title",
            f"E2E test {_TIMESTAMP}",
            "--source",
            _BRANCH,
            "--description",
            "Automated e2e test — will be declined",
            "--dry-run",
        )
        _check("pr_create --dry-run", r, stdout_contains="DRY RUN")

        # Real create
        r = _run(
            "pr_create.py",
            "--title",
            f"E2E test {_TIMESTAMP}",
            "--source",
            _BRANCH,
            "--description",
            "Automated e2e test — will be declined",
        )
        if _check("pr_create", r, stdout_contains="created"):
            # Extract PR ID from output like "PR #42 created: ..."
            for line in r.stdout.splitlines():
                if "PR #" in line:
                    with contextlib.suppress(ValueError, IndexError):
                        _pr_id = int(line.split("PR #")[1].split()[0])
            if _pr_id:
                print(f"       PR ID: {_pr_id}")
            else:
                print("[FAIL] Could not extract PR ID from output")
                _failed += 1

        if not _pr_id:
            print("\nCannot continue without a PR ID.")
            return

        pr = str(_pr_id)

        # ── 3. pr_get ────────────────────────────────────────────
        r = _run("pr_get.py", "--pr", pr)
        _check("pr_get (detail)", r, stdout_contains=f"PR #{pr}")

        r = _run("pr_get.py", "--pr", pr, "--format", "json")
        _check("pr_get (json)", r, stdout_contains='"id"')

        # ── 4. pr_list ───────────────────────────────────────────
        r = _run("pr_list.py", "--state", "OPEN")
        _check("pr_list (table)", r, stdout_contains=pr)

        r = _run("pr_list.py", "--state", "OPEN", "--format", "json")
        _check("pr_list (json)", r, stdout_contains=f'"id": {pr}')

        r = _run("pr_list.py", "--branch", _BRANCH)
        _check("pr_list --branch", r, stdout_contains=pr)

        # ── 5. pr_update (dry-run first, then real) ──────────────
        r = _run("pr_update.py", "--pr", pr, "--title", f"E2E UPDATED {_TIMESTAMP}", "--dry-run")
        _check("pr_update --dry-run", r, stdout_contains="DRY RUN")

        r = _run(
            "pr_update.py",
            "--pr",
            pr,
            "--title",
            f"E2E UPDATED {_TIMESTAMP}",
            "--description",
            "Updated description",
        )
        _check("pr_update", r, stdout_contains="updated")

        # Verify update took effect
        r = _run("pr_get.py", "--pr", pr)
        _check("pr_get (after update)", r, stdout_contains=f"E2E UPDATED {_TIMESTAMP}")

        # ── 6–7. Comments: post, reply, display, filter, resolve ─
        _test_comments(pr, _TEST_FILE)

        # ── 8. pr_checks ─────────────────────────────────────────
        r = _run("pr_checks.py", "--pr", pr)
        # May have 0 statuses — that's fine, just verify no error
        _check("pr_checks (table)", r)

        r = _run("pr_checks.py", "--pr", pr, "--format", "json")
        _check("pr_checks (json)", r)

        # ── 9. pr_jira ───────────────────────────────────────────
        r = _run("pr_jira.py", "--pr", pr)
        # Test branch has no Jira keys — verify it handles that gracefully
        _check("pr_jira (table)", r)

        r = _run("pr_jira.py", "--pr", pr, "--format", "json")
        _check("pr_jira (json)", r, stdout_contains='"jira_keys"')

        # ── 10. pr_merge --dry-run ───────────────────────────────
        r = _run("pr_merge.py", "--pr", pr, "--dry-run")
        _check("pr_merge --dry-run", r, stdout_contains="DRY RUN")

        # ── 11. build_status ─────────────────────────────────────
        # Get the HEAD commit of the test branch
        head_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        ).stdout.strip()

        r = _run("build_status.py", "--commit", head_sha)
        _check("build_status --commit", r)

        r = _run("build_status.py", "--branch", _BRANCH)
        _check("build_status --branch", r)

        # ── 12. repo_list ────────────────────────────────────────
        r = _run("repo_list.py")
        _check("repo_list (table)", r)

        r = _run("repo_list.py", "--format", "json")
        _check("repo_list (json)", r, stdout_contains='"slug"')

        # ── 13. pr_decline (dry-run first, then real) ────────────
        r = _run("pr_decline.py", "--pr", pr, "--dry-run")
        _check("pr_decline --dry-run", r, stdout_contains="DRY RUN")

        r = _run("pr_decline.py", "--pr", pr)
        _check("pr_decline", r, stdout_contains="declined")

    finally:
        # ── Cleanup ──────────────────────────────────────────────
        if not args.keep:
            _cleanup()
        else:
            print(f"\n[KEEP] Branch {_BRANCH} and PR #{_pr_id} left for debugging")

    # ── Summary ──────────────────────────────────────────────────
    total = _passed + _failed
    print()
    print("=" * 50)
    if _failed == 0:
        print(f"{_passed}/{total} passed")
    else:
        print(f"{_passed}/{total} passed, {_failed} FAILED")
    sys.exit(0 if _failed == 0 else 1)


if __name__ == "__main__":
    main()
