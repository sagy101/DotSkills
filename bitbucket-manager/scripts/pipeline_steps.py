#!/usr/bin/env python3
"""List steps for a Bitbucket pipeline."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_client import BitbucketClient
from bb_config import add_common_args, load_config, resolve_repo, resolve_workspace


def main() -> None:
    parser = argparse.ArgumentParser(description="List steps for a Bitbucket pipeline")
    add_common_args(parser)
    parser.add_argument("--pipeline", required=True, help="Pipeline UUID")
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

    steps = client.list_pipeline_steps(
        workspace, repo_slug, args.pipeline, max_results=args.max_results
    )

    if args.format == "json":
        print(json.dumps(steps, indent=2))
        return

    if not steps:
        print(f"No steps found for pipeline {args.pipeline}.")
        return

    print(f"{'UUID':<40}  {'State':<14}  {'Started'}")
    print(f"{'─' * 40}  {'─' * 14}  {'─' * 25}")
    for step in steps:
        state = step.get("state", {})
        state_name = state.get("name") or state.get("type") or "?"
        print(f"{step.get('uuid', '?'):<40}  {state_name:<14}  {step.get('started_on', '?')}")


if __name__ == "__main__":
    main()
