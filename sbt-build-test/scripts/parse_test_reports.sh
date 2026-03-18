#!/usr/bin/env bash
# parse_test_reports.sh — Parse JUnit XML test reports from SBT
#
# Usage: parse_test_reports.sh <target-dir> [--verbose]
#
# Scans target/test-reports/ for TEST-*.xml files and produces a summary.
# With --verbose, also lists individual failed test cases with their error messages.
#
# Exit codes:
#   0 — all tests passed
#   1 — one or more tests failed
#   2 — no test reports found

set -euo pipefail

TARGET_DIR="${1:?Usage: parse_test_reports.sh <target-dir> [--verbose]}"
VERBOSE="${2:-}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

REPO_ROOT="$(find_repo_root_for_path "$TARGET_DIR" || true)"
if [ -n "$REPO_ROOT" ]; then
  LOCK_FILE="$(test_activity_lock_file "$REPO_ROOT")"
  if [ -f "$LOCK_FILE" ]; then
    echo "ERROR: Refusing to parse test reports while an sbt test command is active for $REPO_ROOT" >&2
    echo "Hint: wait for the active test run to finish, then rerun parse_test_reports.sh." >&2
    exit 2
  fi
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required to parse JUnit XML reports" >&2
  exit 2
fi

python3 - "$TARGET_DIR" "$VERBOSE" <<'PY'
import os
import re
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

target_dir = Path(sys.argv[1])
verbose = sys.argv[2] if len(sys.argv) > 2 else ""
message_limit = 500
report_dir = target_dir / "test-reports"

if not report_dir.is_dir():
    print(f"ERROR: No test-reports directory found at {report_dir}", file=sys.stderr)
    print("Hint: Run tests first with 'sbt test' to generate reports.", file=sys.stderr)
    raise SystemExit(2)

xml_files = sorted(report_dir.glob("TEST-*.xml"))
if not xml_files:
    print(f"ERROR: No TEST-*.xml files found in {report_dir}", file=sys.stderr)
    raise SystemExit(2)

# ── Find the most recent SBT log file for this project ─────────────────────
def find_sbt_log(target_dir: Path) -> Path | None:
    """Find the most recent SBT log file for this project."""
    repo_root = target_dir
    while repo_root != repo_root.parent:
        if (repo_root / "build.sbt").exists():
            break
        repo_root = repo_root.parent
    else:
        return None

    cache_root = Path(os.environ.get("SBT_BUILD_CACHE_ROOT", Path.home() / ".sbt-build-cache"))
    log_dir = cache_root / "logs"
    if not log_dir.is_dir():
        return None

    # Sanitize the repo root path to match the log file naming convention
    sanitized = re.sub(r"[^a-zA-Z0-9._-]", "_", str(repo_root))
    candidates = sorted(
        [f for f in log_dir.iterdir() if f.name.startswith(sanitized) and f.suffix == ".log"],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def parse_sbt_log_failures(log_path: Path) -> set[str]:
    """Extract failed test suite names from SBT log's [error] Failed tests: block."""
    failed = set()
    if not log_path or not log_path.exists():
        return failed
    try:
        text = log_path.read_text(errors="replace")
    except OSError:
        return failed

    in_failed_block = False
    for line in text.splitlines():
        # Strip ANSI codes for matching
        clean = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", line)
        if "[error] Failed tests:" in clean:
            in_failed_block = True
            continue
        if in_failed_block:
            stripped = clean.strip()
            if stripped.startswith("[error]"):
                suite = stripped.removeprefix("[error]").strip()
                if suite and not suite.startswith("("):
                    failed.add(suite)
            else:
                in_failed_block = False
    return failed


total_tests = 0
total_failures = 0
total_errors = 0
total_skipped = 0
total_suites = 0
failed_suites = []
xml_suite_names = set()

print("=== Test Report Summary ===")
print()

for xml_file in xml_files:
    suite_name = xml_file.stem.removeprefix("TEST-")
    xml_suite_names.add(suite_name)
    try:
        root = ET.parse(xml_file).getroot()
    except ET.ParseError as exc:
        print(f"ERROR: Failed to parse JUnit XML report {xml_file}: {exc}", file=sys.stderr)
        raise SystemExit(2)

    tests = int(root.attrib.get("tests", "0") or "0")
    failures = int(root.attrib.get("failures", "0") or "0")
    errors = int(root.attrib.get("errors", "0") or "0")
    skipped = int(root.attrib.get("skipped", "0") or "0")
    time = root.attrib.get("time", "?") or "?"

    total_tests += tests
    total_failures += failures
    total_errors += errors
    total_skipped += skipped
    total_suites += 1

    if failures == 0 and errors == 0:
        print(f"  PASS  ({tests} tests, {time}s): {suite_name}")
    else:
        print(f"  FAIL  ({failures} failures, {errors} errors / {tests} tests, {time}s): {suite_name}")
        failed_suites.append((xml_file, root, suite_name))

# ── Cross-reference SBT log for crashed suites ─────────────────────────────
sbt_log = find_sbt_log(target_dir)
sbt_failed = parse_sbt_log_failures(sbt_log)
crashed_suites = []
if sbt_failed:
    for suite in sorted(sbt_failed):
        if suite not in xml_suite_names:
            crashed_suites.append(suite)
            print(f"  CRASH (no JUnit XML produced): {suite}")

print()
print("--- Totals ---")
print(f"  Suites:   {total_suites}")
print(f"  Tests:    {total_tests}")
print(f"  Passed:   {total_tests - total_failures - total_errors - total_skipped}")
print(f"  Failed:   {total_failures}")
print(f"  Errors:   {total_errors}")
print(f"  Skipped:  {total_skipped}")
if crashed_suites:
    print(f"  Crashed:  {len(crashed_suites)} (no XML — test runner crashed before producing results)")

has_failures = total_failures > 0 or total_errors > 0 or len(crashed_suites) > 0

if crashed_suites:
    print()
    print("--- Crashed Test Suites (no JUnit XML) ---")
    print("  These suites appear in SBT's [error] Failed tests: but produced no XML report.")
    print("  This usually means the test runner crashed (e.g. ClassCastException, OutOfMemoryError)")
    print("  before JUnit XML could be written.")
    for suite in crashed_suites:
        print(f"    CRASHED: {suite}")
    if sbt_log:
        print(f"  SBT log: {sbt_log}")
    print()

if total_failures > 0 or total_errors > 0:
    print()
    print("--- Failed Test Details ---")
    for xml_file, root, suite_name in failed_suites:
        print()
        print(f"  Suite: {suite_name}")
        for testcase in root.findall("testcase"):
            test_name = testcase.attrib.get("name", "<unknown>")
            for child_name in ("failure", "error"):
                for node in testcase.findall(child_name):
                    message = (node.attrib.get("message") or "").strip()
                    if not message:
                        text = (node.text or "").strip()
                        message = text.splitlines()[0] if text else "<no message>"
                    display_message = message
                    if verbose != "--verbose" and len(display_message) > message_limit:
                        display_message = display_message[:message_limit - 3].rstrip() + "..."
                    print(f"    FAILED: {test_name}")
                    print(f"    Message: {display_message}")
                    print()
        if verbose == "--verbose":
            print(f"    Full XML: {xml_file}")

# ── TOP FAILURES section (always shown, up to 5) ──────────────────────────
if total_failures > 0 or total_errors > 0:
    print()
    print("--- Top Failures ---")
    shown = 0
    for xml_file, root, suite_name in failed_suites:
        if shown >= 5:
            break
        for testcase in root.findall("testcase"):
            if shown >= 5:
                break
            test_name = testcase.attrib.get("name", "<unknown>")
            for child_name in ("failure", "error"):
                for node in testcase.findall(child_name):
                    if shown >= 5:
                        break
                    message = (node.attrib.get("message") or "").strip()
                    if not message:
                        text = (node.text or "").strip()
                        message = text.splitlines()[0] if text else "<no message>"
                    short_msg = message[:200].rstrip() + ("..." if len(message) > 200 else "")
                    print(f"  {shown + 1}. {suite_name} > {test_name}")
                    print(f"     {short_msg}")
                    shown += 1

if has_failures:
    if verbose != "--verbose":
        print()
        print("  Hint: rerun with --verbose to print full XML paths for failed suites")
    print()
    print("=== RESULT: FAILED ===")
    raise SystemExit(1)

print()
print("=== RESULT: ALL PASSED ===")
PY
