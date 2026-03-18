#!/usr/bin/env python3
"""View Jenkins build console output with redaction."""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jenkins_client import JenkinsClient
from jenkins_config import add_common_args, load_config, resolve_branch, resolve_job_path
from jenkins_redaction import redact_text, strip_ansi


def main() -> None:
    parser = argparse.ArgumentParser(description="View Jenkins build console output")
    add_common_args(parser)
    parser.add_argument("--build", type=int, help="Build number (default: last build)")
    parser.add_argument(
        "--tail", type=int, default=100, help="Show last N lines (default: 100, 0 for all)"
    )
    parser.add_argument("--grep", help="Filter lines matching regex pattern")
    parser.add_argument("--format", choices=["raw", "json"], default="raw", help="Output format")
    args = parser.parse_args()

    config = load_config(args.config)
    client = JenkinsClient(config)

    folder, job = resolve_job_path(config, args.folder, args.job)
    if not job:
        print("ERROR: Could not determine job name.")
        print("Provide --job <name> or set job_cache in .jenkins.json")
        sys.exit(1)

    branch = resolve_branch(config, args.branch)

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

    # Fetch console output
    console = client.get_build_console(folder, job, branch, build_number)

    # Strip ANSI codes and redact secrets before any output
    console = strip_ansi(console)
    console = redact_text(console)

    # Apply filters
    lines = console.splitlines()

    if args.grep:
        try:
            pattern = re.compile(args.grep, re.IGNORECASE)
            lines = [line for line in lines if pattern.search(line)]
        except re.error:
            grep_lower = args.grep.lower()
            lines = [line for line in lines if grep_lower in line.lower()]

    if args.tail and args.tail > 0:
        lines = lines[-args.tail :]

    if args.format == "json":
        import json

        print(
            json.dumps(
                {
                    "build_number": build_number,
                    "folder": folder,
                    "job": job,
                    "branch": branch,
                    "line_count": len(lines),
                    "lines": lines,
                },
                indent=2,
            )
        )
        return

    # Header
    job_path = f"{folder}/{job}" if folder else job
    branch_str = f" @ {branch}" if branch else ""
    print(f"Console output for {job_path}{branch_str} #{build_number}")
    print(
        f"(showing {'last ' + str(args.tail) + ' lines' if args.tail else 'all lines'}"
        f"{', grep: ' + args.grep if args.grep else ''})"
    )
    print("-" * 72)

    for line in lines:
        print(line)


if __name__ == "__main__":
    main()
