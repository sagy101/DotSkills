#!/usr/bin/env python3
"""Check build status for a Jenkins job/branch."""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
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


def _format_duration(ms: int) -> str:
    """Format milliseconds into human-readable duration."""
    seconds = ms // 1000
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    secs = seconds % 60
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m {secs}s"


def _format_timestamp(ts: int) -> str:
    """Format Unix timestamp (ms) to human-readable datetime."""
    dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _print_build(
    build: dict,
    folder: str | None,
    job: str | None,
    branch: str | None,
    fmt: str = "table",
    watch_ts: str | None = None,
) -> None:
    """Print build info in table or JSON format."""
    if fmt == "json":
        print(json.dumps(build, indent=2))
        return

    job_path = f"{folder}/{job}" if folder else job
    branch_str = f" @ {branch}" if branch else ""
    header = f"Build status for {job_path}{branch_str}:"
    if watch_ts:
        header = f"[{watch_ts}] {header}"
    print(header)
    print()

    number = build.get("number", "?")
    result = build.get("result") or ("BUILDING" if build.get("building") else "UNKNOWN")
    duration = build.get("duration", 0)
    timestamp = build.get("timestamp", 0)
    url = build.get("url", "")

    print(f"  Build    #{number}")
    print(f"  Status   {result}")
    if duration:
        print(f"  Duration {_format_duration(duration)}")
    if timestamp:
        print(f"  Started  {_format_timestamp(timestamp)}")
    if url:
        print(f"  URL      {url}")


def _watch_build(
    client: "JenkinsClient",
    folder: str | None,
    job: str,
    branch: str | None,
    build: dict,
    fmt: str,
    interval: int,
    timeout: int,
    build_number: int | None = None,
) -> None:
    """Poll until build finishes or timeout. Exits the process."""
    start = time.monotonic()
    while True:
        is_building = build.get("building", False)
        now_ts = datetime.now(tz=timezone.utc).strftime("%H:%M:%S")
        _print_build(build, folder, job, branch, fmt=fmt, watch_ts=now_ts)

        if not is_building:
            result = build.get("result", "UNKNOWN")
            print()
            print(f"Build finished: {result}")
            sys.exit(0 if result == "SUCCESS" else 1)

        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            print()
            print(f"Timeout after {timeout}s — build still running.")
            sys.exit(2)

        remaining = timeout - elapsed
        sleep_time = min(interval, remaining)
        print()
        print(f"  Building... next check in {int(sleep_time)}s (timeout in {int(remaining)}s)")
        print()
        time.sleep(sleep_time)
        if build_number:
            build = client.get_build_info(folder, job, branch, build_number) or {}
        else:
            build = client.get_last_build(folder, job, branch) or {}
        if not build:
            print("Build disappeared during polling.")
            sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Jenkins build status")
    add_common_args(parser)
    parser.add_argument("--build", type=int, help="Build number (default: last build)")
    parser.add_argument(
        "--format", choices=["table", "json"], default="table", help="Output format"
    )
    parser.add_argument("--watch", action="store_true", help="Poll until build finishes")
    parser.add_argument(
        "--interval", type=int, default=60, help="Poll interval in seconds (default: 60)"
    )
    parser.add_argument(
        "--timeout", type=int, default=600, help="Max wait time in seconds (default: 600)"
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
        discovered = client.find_job(job)
        if discovered:
            folder, job = discovered
        else:
            print(f"ERROR: Job '{job}' not found in Jenkins.")
            print("Use --folder and --job flags, or add to job_cache in .jenkins.json")
            sys.exit(1)

    # Determine build
    build_number = args.build
    if build_number:
        build = client.get_build_info(folder, job, branch, build_number)
        if not build:
            job_path = f"{folder}/{job}" if folder else job
            branch_str = f" @ {branch}" if branch else ""
            print(f"Build #{build_number} not found for {job_path}{branch_str}")
            sys.exit(1)
    else:
        build = client.get_last_build(folder, job, branch)
        if not build:
            job_path = f"{folder}/{job}" if folder else job
            branch_str = f" @ {branch}" if branch else ""
            print(f"No builds found for {job_path}{branch_str}")
            sys.exit(0)

    if args.watch:
        _watch_build(
            client,
            folder,
            job,
            branch,
            build,
            args.format,
            args.interval,
            args.timeout,
            build_number=args.build,
        )
    else:
        _print_build(build, folder, job, branch, fmt=args.format)


if __name__ == "__main__":
    main()
