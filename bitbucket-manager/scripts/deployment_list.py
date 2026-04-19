#!/usr/bin/env python3
"""List Bitbucket deployments."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_client import BitbucketClient
from bb_config import add_common_args, load_config, resolve_repo, resolve_workspace


def main() -> None:
    parser = argparse.ArgumentParser(description="List Bitbucket deployments")
    add_common_args(parser)
    parser.add_argument(
        "--max-results",
        type=int,
        default=50,
        help="Maximum results to return (default: 50, 0 = all)",
    )
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

    deployments = client.list_deployments(workspace, repo_slug, max_results=args.max_results)
    if args.format == "json":
        print(json.dumps(deployments, indent=2))
        return

    if not deployments:
        print("No deployments found.")
        return

    print(f"{'UUID':<40}  {'State':<14}  {'Environment'}")
    print(f"{'─' * 40}  {'─' * 14}  {'─' * 30}")
    for deployment in deployments:
        state = deployment.get("state", {})
        state_name = state.get("name") or state.get("type") or "?"
        env = deployment.get("environment", {})
        env_name = env.get("name") or env.get("uuid") or "?"
        print(f"{deployment.get('uuid', '?'):<40}  {state_name:<14}  {env_name}")


if __name__ == "__main__":
    main()
