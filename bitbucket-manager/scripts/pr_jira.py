#!/usr/bin/env python3
"""Extract Jira issue keys linked to a Bitbucket pull request.

Scans branch name, PR title, PR description, and commit messages for
Jira-style keys (e.g. PROJ-123). Optionally fetches issue summaries
from Jira if jira-manager config exists.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_client import BitbucketClient
from bb_config import add_common_args, load_config, resolve_repo, resolve_workspace

# Match Jira-style issue keys: 2+ uppercase letters, dash, 1+ digits
_JIRA_KEY_RE = re.compile(r"\b([A-Z]{2,}-\d+)\b")


def _extract_keys(*texts: str) -> list[str]:
    """Extract unique Jira keys from multiple text sources, preserving order."""
    seen = set()
    keys = []
    for text in texts:
        if not text:
            continue
        for match in _JIRA_KEY_RE.findall(text):
            if match not in seen:
                seen.add(match)
                keys.append(match)
    return keys


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Jira issue keys linked to a Bitbucket PR")
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

    pr = client.get_pr(workspace, repo_slug, args.pr)
    branch = pr.get("source", {}).get("branch", {}).get("name", "")
    title = pr.get("title", "")
    description = pr.get("description", "")

    # Fetch commit messages
    commits_data = client._paginate(
        f"/repositories/{workspace}/{repo_slug}/pullrequests/{args.pr}/commits",
    )
    commit_messages = " ".join(c.get("message", "") for c in commits_data)

    keys = _extract_keys(branch, title, description, commit_messages)

    if args.format == "json":
        print(json.dumps({"pr_id": args.pr, "jira_keys": keys}, indent=2))
        return

    if not keys:
        print(f"No Jira issue keys found in PR #{args.pr}.")
        return

    print(f"Jira issues linked to PR #{args.pr}:")
    print()
    for key in keys:
        print(f"  {key}")
    print(f"\n{len(keys)} issue(s) found.")


if __name__ == "__main__":
    main()
