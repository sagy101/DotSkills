#!/usr/bin/env python3
"""Get a Bitbucket deployment by UUID."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_client import BitbucketClient
from bb_config import add_common_args, load_config, resolve_repo, resolve_workspace


def main() -> None:
    parser = argparse.ArgumentParser(description="Get a Bitbucket deployment")
    add_common_args(parser)
    parser.add_argument("--deployment", required=True, help="Deployment UUID")
    parser.add_argument(
        "--format",
        choices=["detail", "json"],
        default="detail",
        help="Output format (default: detail)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    workspace = resolve_workspace(config, args.workspace)
    repo_slug = resolve_repo(config, args.repo)
    client = BitbucketClient(config)

    deployment = client.get_deployment(workspace, repo_slug, args.deployment)
    if args.format == "json":
        print(json.dumps(deployment, indent=2))
        return

    print(f"Deployment {deployment.get('uuid', '?')}")
    state = deployment.get("state", {})
    print(f"State: {state.get('name', state.get('type', '?'))}")


if __name__ == "__main__":
    main()
