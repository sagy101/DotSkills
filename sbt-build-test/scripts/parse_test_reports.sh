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
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

target_dir = Path(sys.argv[1])
verbose = sys.argv[2] if len(sys.argv) > 2 else ""
message_limit = 240
report_dir = target_dir / "test-reports"

if not report_dir.is_dir():
    print(f"ERROR: No test-reports directory found at {report_dir}", file=sys.stderr)
    print("Hint: Run tests first with 'sbt test' to generate reports.", file=sys.stderr)
    raise SystemExit(2)

xml_files = sorted(report_dir.glob("TEST-*.xml"))
if not xml_files:
    print(f"ERROR: No TEST-*.xml files found in {report_dir}", file=sys.stderr)
    raise SystemExit(2)

total_tests = 0
total_failures = 0
total_errors = 0
total_skipped = 0
total_suites = 0
failed_suites = []

print("=== Test Report Summary ===")
print()

for xml_file in xml_files:
    suite_name = xml_file.stem.removeprefix("TEST-")
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

print()
print("--- Totals ---")
print(f"  Suites:   {total_suites}")
print(f"  Tests:    {total_tests}")
print(f"  Passed:   {total_tests - total_failures - total_errors - total_skipped}")
print(f"  Failed:   {total_failures}")
print(f"  Errors:   {total_errors}")
print(f"  Skipped:  {total_skipped}")

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
    if verbose != "--verbose":
        print("  Hint: rerun with --verbose to print full XML paths for failed suites")
    print()
    print("=== RESULT: FAILED ===")
    raise SystemExit(1)

print()
print("=== RESULT: ALL PASSED ===")
PY
