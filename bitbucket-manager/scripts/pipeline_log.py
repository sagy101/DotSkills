#!/usr/bin/env python3
"""Fetch the raw log for a Bitbucket pipeline step."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_client import BitbucketClient
from bb_config import add_common_args, load_config, resolve_repo, resolve_workspace


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch a Bitbucket pipeline step log")
    add_common_args(parser)
    parser.add_argument("--pipeline", required=True, help="Pipeline UUID")
    parser.add_argument("--step", required=True, help="Step UUID")
    parser.add_argument("--log", required=True, help="Log UUID")
    args = parser.parse_args()

    config = load_config(args.config)
    workspace = resolve_workspace(config, args.workspace)
    repo_slug = resolve_repo(config, args.repo)
    client = BitbucketClient(config)

    log_text = client.get_pipeline_step_log(
        workspace, repo_slug, args.pipeline, args.step, args.log
    )
    print(log_text, end="" if log_text.endswith("\n") or not log_text else "\n")


if __name__ == "__main__":
    main()
