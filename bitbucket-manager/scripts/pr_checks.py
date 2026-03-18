#!/usr/bin/env python3
"""List build/pipeline status checks for a Bitbucket pull request."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_client import BitbucketClient
from bb_config import add_common_args, load_config, resolve_repo, resolve_workspace


def main() -> None:
    parser = argparse.ArgumentParser(description="List build checks for a Bitbucket PR")
    add_common_args(parser)
    parser.add_argument("--pr", required=True, type=int, help="PR ID")
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    workspace = resolve_workspace(config, args.workspace)
    repo_slug = resolve_repo(config, args.repo)
    client = BitbucketClient(config)

    statuses = client.get_pr_statuses(workspace, repo_slug, args.pr)

    if args.format == "json":
        print(json.dumps(statuses, indent=2))
        return

    if not statuses:
        print(f"No build statuses for PR #{args.pr}.")
        return

    print(f"Build checks for PR #{args.pr}:")
    print()
    print(f"{'State':<12}  {'Name':<40}  {'URL'}")
    print(f"{'─' * 12}  {'─' * 40}  {'─' * 50}")

    for s in statuses:
        state = s.get("state", "?")
        name = s.get("name", s.get("key", "?"))[:40]
        url = s.get("url", "")
        # Color-code state text
        state_display = state
        print(f"{state_display:<12}  {name:<40}  {url}")

    passed = sum(1 for s in statuses if s.get("state") == "SUCCESSFUL")
    failed = sum(1 for s in statuses if s.get("state") == "FAILED")
    pending = sum(1 for s in statuses if s.get("state") == "INPROGRESS")
    print(f"\n{len(statuses)} check(s): {passed} passed, {failed} failed, {pending} pending.")


if __name__ == "__main__":
    main()
