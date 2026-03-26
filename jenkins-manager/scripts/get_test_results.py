#!/usr/bin/env python3
"""View structured test results from Jenkins JUnit test reports.

Works with any language/framework that produces JUnit XML (Java, Python, JS, Go, etc.).
Requires the JUnit plugin to be installed on Jenkins (standard on 97%+ of instances).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jenkins_client import JenkinsClient
from jenkins_config import (
    add_common_args,
    load_config,
    resolve_branch,
    resolve_instance,
    resolve_job_path,
)


def _collect_failures(suites: list[dict]) -> list[dict]:
    """Extract failed test cases from suites."""
    failures: list[dict[str, str]] = []
    for suite in suites:
        suite_name = suite.get("name", "<unknown>")
        failures.extend(
            {
                "suite": suite_name,
                "class": case.get("className", ""),
                "test": case.get("name", ""),
                "error": case.get("errorDetails", "") or "",
            }
            for case in suite.get("cases", [])
            if case.get("status", "") in ("FAILED", "REGRESSION")
        )
    return failures


def _print_test_report(report: dict, *, failures_only: bool = False) -> None:
    """Print test report in human-readable table format."""
    pass_count = report.get("passCount", 0)
    fail_count = report.get("failCount", 0)
    skip_count = report.get("skipCount", 0)
    total = pass_count + fail_count + skip_count

    print("--- Test Totals ---")
    print(f"  Total:    {total}")
    print(f"  Passed:   {pass_count}")
    print(f"  Failed:   {fail_count}")
    print(f"  Skipped:  {skip_count}")

    if fail_count > 0:
        print("  Result:   FAILED")
    elif total == 0:
        print("  Result:   NO TESTS")
    else:
        print("  Result:   PASSED")

    suites = report.get("suites", [])
    if not suites:
        return

    failures = _collect_failures(suites)

    if failures:
        print()
        print("--- Failed Tests ---")
        for i, f in enumerate(failures, 1):
            print(f"  {i}. {f['class']} > {f['test']}")
            if f["error"]:
                lines = f["error"].strip().splitlines()[:3]
                for line in lines:
                    print(f"     {line[:200]}")
            print()

    if not failures_only and not failures:
        print()
        print("--- Suite Summary ---")
        for suite in suites:
            suite_name = suite.get("name", "<unknown>")
            cases = suite.get("cases", [])
            passed = sum(1 for c in cases if c.get("status") in ("PASSED", "FIXED"))
            failed = sum(1 for c in cases if c.get("status") in ("FAILED", "REGRESSION"))
            skipped = sum(1 for c in cases if c.get("status") == "SKIPPED")
            print(
                f"  {'FAIL' if failed else 'PASS'}  ({passed} passed, {failed} failed, {skipped} skipped): {suite_name}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="View Jenkins test results")
    add_common_args(parser)
    parser.add_argument("--build", type=int, help="Build number (default: last build)")
    parser.add_argument("--failures-only", action="store_true", help="Show only failed tests")
    parser.add_argument(
        "--format", choices=["table", "json"], default="table", help="Output format"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    instance = resolve_instance(config, args.instance)
    client = JenkinsClient(instance)

    folder, job = resolve_job_path(instance, args.folder, args.job)
    if not job:
        print("ERROR: Could not determine job name.")
        print("Provide --job <name> or set job_cache in .jenkins.json")
        sys.exit(1)

    branch = resolve_branch(instance, args.branch)

    # If no folder, try to discover it
    if not folder and job:
        result = client.find_job(job)
        if result:
            folder, job = result
        else:
            print(f"ERROR: Job '{job}' not found in Jenkins.")
            sys.exit(1)

    # Determine build number
    build_number = args.build
    if not build_number:
        build = client.get_last_build(folder, job, branch)
        if not build:
            job_path = f"{folder}/{job}" if folder else job
            branch_str = f" @ {branch}" if branch else ""
            print(f"No builds found for {job_path}{branch_str}")
            sys.exit(0)
        build_number = build.get("number")

    # Fetch test report
    job_path = f"{folder}/{job}" if folder else job
    branch_str = f" @ {branch}" if branch else ""
    print(f"Test results for {job_path}{branch_str} #{build_number}")
    print("-" * 72)

    report = client.get_test_report(folder, job, branch, build_number)

    if not report:
        print()
        print("No test reports available for this build.")
        print("This may mean:")
        print("  - The JUnit plugin is not installed on this Jenkins instance")
        print("  - Tests did not publish JUnit XML results")
        print("  - The build did not run tests")
        print()
        print(
            "Alternative: use get_logs.py --grep 'FAILED\\|ERROR\\|Tests run' to search console output"
        )
        sys.exit(0)

    if args.format == "json":
        print(json.dumps(report, indent=2))
        return

    print()
    _print_test_report(report, failures_only=args.failures_only)

    # Exit with appropriate code
    if report.get("failCount", 0) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
