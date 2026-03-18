#!/usr/bin/env python3
"""Check build status for a Jenkins job/branch."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jenkins_client import JenkinsClient
from jenkins_config import add_common_args, load_config, resolve_branch, resolve_job_path


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Jenkins build status")
    add_common_args(parser)
    parser.add_argument(
        "--format", choices=["table", "json"], default="table", help="Output format"
    )
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
        discovered = client.find_job(job)
        if discovered:
            folder, job = discovered
        else:
            print(f"ERROR: Job '{job}' not found in Jenkins.")
            print("Use --folder and --job flags, or add to job_cache in .jenkins.json")
            sys.exit(1)

    # Try to get last build
    build = client.get_last_build(folder, job, branch)

    if not build:
        job_path = f"{folder}/{job}" if folder else job
        branch_str = f" @ {branch}" if branch else ""
        print(f"No builds found for {job_path}{branch_str}")
        sys.exit(0)

    if args.format == "json":
        print(json.dumps(build, indent=2))
        return

    # Table output
    job_path = f"{folder}/{job}" if folder else job
    branch_str = f" @ {branch}" if branch else ""
    print(f"Build status for {job_path}{branch_str}:")
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


if __name__ == "__main__":
    main()
