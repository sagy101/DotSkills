#!/usr/bin/env python3
"""View commits/changes included in a Jenkins build."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jenkins_client import JenkinsClient
from jenkins_config import add_common_args, load_config, resolve_branch, resolve_job_path


def _format_timestamp(ts: int) -> str:
    """Format Unix timestamp (ms) to human-readable datetime."""
    dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _short_sha(commit_id: str) -> str:
    """Shorten commit SHA to 8 chars."""
    return commit_id[:8] if commit_id else "?"


def main() -> None:
    parser = argparse.ArgumentParser(description="View commits included in a Jenkins build")
    add_common_args(parser)
    parser.add_argument("--build", type=int, help="Build number (default: last build)")
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

    # Fetch changesets
    changesets = client.get_build_changesets(folder, job, branch, build_number)

    # Flatten all commits from all changesets
    all_commits = []
    for cs in changesets:
        kind = cs.get("kind", "unknown")
        for item in cs.get("items", []):
            item["_scm_kind"] = kind
            all_commits.append(item)

    if args.format == "json":
        print(json.dumps(changesets, indent=2))
        return

    job_path = f"{folder}/{job}" if folder else job
    branch_str = f" @ {branch}" if branch else ""
    print(f"Changes in {job_path}{branch_str} #{build_number}:")
    print()

    if not all_commits:
        print("  No changes found in this build.")
        return

    print(f"{'Commit':<10} {'Author':<25} {'Message'}")
    print("-" * 80)
    for commit in all_commits:
        sha = _short_sha(commit.get("commitId", ""))
        author = commit.get("author", {}).get("fullName", "unknown")
        msg = commit.get("msg", "").split("\n")[0]  # First line only
        # Truncate long messages
        if len(msg) > 60:
            msg = msg[:57] + "..."
        print(f"{sha:<10} {author:<25} {msg}")

    # Show affected files summary
    total_files = sum(len(c.get("affectedPaths", [])) for c in all_commits)
    if total_files:
        print(f"\n{len(all_commits)} commit(s), {total_files} file(s) affected")
    else:
        print(f"\n{len(all_commits)} commit(s)")


if __name__ == "__main__":
    main()
