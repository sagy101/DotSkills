#!/usr/bin/env python3
"""Get build status for a commit SHA or branch HEAD."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_config import add_common_args, load_config, resolve_repo, resolve_workspace
from bb_client import BitbucketClient


def _resolve_branch_head(branch: str) -> str:
    """Resolve a branch name to its HEAD commit SHA using git."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", f"origin/{branch}"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    # Fallback: try without origin/ prefix
    try:
        result = subprocess.run(
            ["git", "rev-parse", branch],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    print(f"ERROR: Could not resolve branch '{branch}' to a commit SHA.")
    print("Provide --commit <sha> explicitly, or ensure the branch is fetched locally.")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Get build status for a commit or branch")
    add_common_args(parser)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--commit", help="Commit SHA")
    group.add_argument("--branch", help="Branch name (resolves to HEAD SHA)")
    parser.add_argument("--format", choices=["table", "json"], default="table",
                        help="Output format (default: table)")
    args = parser.parse_args()

    config = load_config(args.config)
    workspace = resolve_workspace(config, args.workspace)
    repo_slug = resolve_repo(config, args.repo)
    client = BitbucketClient(config)

    sha = args.commit if args.commit else _resolve_branch_head(args.branch)

    statuses = client.get_commit_statuses(workspace, repo_slug, sha)

    if args.format == "json":
        print(json.dumps(statuses, indent=2))
        return

    if not statuses:
        print(f"No build statuses for commit {sha[:12]}.")
        return

    print(f"Build statuses for {sha[:12]}:")
    print()
    print(f"{'State':<12}  {'Name':<40}  {'URL'}")
    print(f"{'─'*12}  {'─'*40}  {'─'*50}")

    for s in statuses:
        state = s.get("state", "?")
        name = s.get("name", s.get("key", "?"))[:40]
        url = s.get("url", "")
        print(f"{state:<12}  {name:<40}  {url}")

    passed = sum(1 for s in statuses if s.get("state") == "SUCCESSFUL")
    failed = sum(1 for s in statuses if s.get("state") == "FAILED")
    pending = sum(1 for s in statuses if s.get("state") == "INPROGRESS")
    print(f"\n{len(statuses)} check(s): {passed} passed, {failed} failed, {pending} pending.")


if __name__ == "__main__":
    main()
