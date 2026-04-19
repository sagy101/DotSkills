#!/usr/bin/env python3
"""Get a Bitbucket deployment environment by UUID."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_client import BitbucketClient
from bb_config import add_common_args, load_config, resolve_repo, resolve_workspace


def main() -> None:
    parser = argparse.ArgumentParser(description="Get a Bitbucket environment")
    add_common_args(parser)
    parser.add_argument("--environment", required=True, help="Environment UUID")
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

    environment = client.get_environment(workspace, repo_slug, args.environment)
    if args.format == "json":
        print(json.dumps(environment, indent=2))
        return

    print(f"Environment {environment.get('uuid', '?')}")
    print(f"Name: {environment.get('name', '?')}")


if __name__ == "__main__":
    main()
