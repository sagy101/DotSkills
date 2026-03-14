#!/usr/bin/env python3
"""Merge a Bitbucket pull request."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_config import add_common_args, load_config, resolve_repo, resolve_workspace
from bb_client import BitbucketClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge a Bitbucket pull request")
    add_common_args(parser)
    parser.add_argument("--pr", required=True, type=int, help="PR ID to merge")
    parser.add_argument("--strategy", default="merge_commit",
                        choices=["merge_commit", "squash", "fast_forward"],
                        help="Merge strategy (default: merge_commit)")
    parser.add_argument("--close-source-branch", action="store_true",
                        help="Close source branch after merge")
    parser.add_argument("--message", help="Merge commit message")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show merge preconditions without merging")
    args = parser.parse_args()

    config = load_config(args.config)
    workspace = resolve_workspace(config, args.workspace)
    repo_slug = resolve_repo(config, args.repo)
    client = BitbucketClient(config)

    if args.dry_run:
        pr = client.get_pr(workspace, repo_slug, args.pr)
        state = pr.get("state", "?")
        title = pr.get("title", "?")
        source = pr.get("source", {}).get("branch", {}).get("name", "?")
        dest = pr.get("destination", {}).get("branch", {}).get("name", "?")

        # Check reviewers/approvals
        participants = pr.get("participants", [])
        approvals = [p for p in participants if p.get("approved")]
        reviewers = pr.get("reviewers", [])

        # Check build statuses
        statuses = client.get_pr_statuses(workspace, repo_slug, args.pr)
        failed = [s for s in statuses if s.get("state") == "FAILED"]
        pending = [s for s in statuses if s.get("state") == "INPROGRESS"]

        # Check open tasks
        task_count = pr.get("task_count", 0)

        print(f"DRY RUN — Merge preconditions for PR #{args.pr}:")
        print(f"  Title:      {title}")
        print(f"  State:      {state}")
        print(f"  Branch:     {source} → {dest}")
        print(f"  Approvals:  {len(approvals)}/{len(reviewers)}")
        print(f"  Checks:     {len(statuses)} total, {len(failed)} failed, {len(pending)} pending")
        print(f"  Open tasks: {task_count}")
        print(f"  Strategy:   {args.strategy}")

        if state != "OPEN":
            print(f"\n  WARNING: PR is {state}, not OPEN — cannot merge.")
        if failed:
            print(f"\n  WARNING: {len(failed)} build check(s) FAILED.")
        if pending:
            print(f"\n  WARNING: {len(pending)} build check(s) still running.")
        return

    result = client.merge_pr(
        workspace=workspace,
        repo_slug=repo_slug,
        pr_id=args.pr,
        merge_strategy=args.strategy,
        close_source_branch=args.close_source_branch,
        message=args.message,
    )

    state = result.get("state", "?")
    print(f"PR #{args.pr} merged (state: {state}).")


if __name__ == "__main__":
    main()
