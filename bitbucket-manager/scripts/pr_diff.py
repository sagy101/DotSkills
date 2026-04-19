#!/usr/bin/env python3
"""Show the diff for a Bitbucket pull request."""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_client import BitbucketClient
from bb_config import add_common_args, load_config, resolve_repo, resolve_workspace


class DiffFileSummary(TypedDict):
    path: str
    additions: int
    deletions: int


class DiffSummary(TypedDict):
    file_count: int
    files: list[DiffFileSummary]


def _summarize_diff(diff_text: str) -> DiffSummary:
    files: list[DiffFileSummary] = []
    current: DiffFileSummary | None = None
    for line in diff_text.splitlines():
        m = re.match(r"^diff --git a/(.+?) b/(.+)$", line)
        if m:
            current = {"path": m.group(2), "additions": 0, "deletions": 0}
            files.append(current)
            continue
        if current is None:
            continue
        if line.startswith("+++ ") or line.startswith("--- "):
            continue
        if line.startswith("+") and not line.startswith("+++"):
            current["additions"] += 1
        elif line.startswith("-") and not line.startswith("---"):
            current["deletions"] += 1
    return {"file_count": len(files), "files": files}


def _print_summary(pr_id: int, diff_text: str) -> None:
    summary = _summarize_diff(diff_text)
    print(f"PR #{pr_id} diff summary: {summary['file_count']} file(s)")
    for entry in summary["files"]:
        print(f"  {entry['path']}: +{entry['additions']} -{entry['deletions']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Show a Bitbucket PR diff")
    add_common_args(parser)
    parser.add_argument("--pr", required=True, type=int, help="PR ID")
    parser.add_argument(
        "--format",
        choices=["diff", "summary", "json"],
        default="diff",
        help="Output format (default: diff)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    workspace = resolve_workspace(config, args.workspace)
    repo_slug = resolve_repo(config, args.repo)
    client = BitbucketClient(config)

    diff_text = client.get_pr_diff(workspace, repo_slug, args.pr)

    if args.format == "json":
        payload = {"pr": args.pr, "diff": diff_text, "summary": _summarize_diff(diff_text)}
        print(json.dumps(payload, indent=2))
    elif args.format == "summary":
        _print_summary(args.pr, diff_text)
    else:
        print(diff_text, end="" if diff_text.endswith("\n") or not diff_text else "\n")


if __name__ == "__main__":
    main()
