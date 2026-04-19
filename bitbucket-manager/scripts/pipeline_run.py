#!/usr/bin/env python3
"""Trigger a Bitbucket pipeline."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_client import BitbucketClient
from bb_config import add_common_args, load_config, resolve_repo, resolve_workspace


def _parse_variables(values: list[str]) -> list[dict[str, object]]:
    variables: list[dict[str, object]] = []
    for item in values:
        key, sep, value = item.partition("=")
        if not sep:
            raise SystemExit(f"Invalid variable {item!r}; expected KEY=VALUE")
        variables.append({"key": key, "value": value})
    return variables


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Bitbucket pipeline")
    add_common_args(parser)
    parser.add_argument("--branch", required=True, help="Branch name to run against")
    parser.add_argument("--commit", help="Optional commit hash")
    parser.add_argument("--selector", default="default", help="Pipeline selector pattern")
    parser.add_argument(
        "--selector-type",
        default="custom",
        help="Pipeline selector type (default: custom)",
    )
    parser.add_argument(
        "--variable",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Pipeline variable (repeatable)",
    )
    parser.add_argument(
        "--format",
        choices=["detail", "json"],
        default="detail",
        help="Output format (default: detail)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show preview without executing")
    args = parser.parse_args()

    config = load_config(args.config)
    workspace = resolve_workspace(config, args.workspace)
    repo_slug = resolve_repo(config, args.repo)
    client = BitbucketClient(config)

    target: dict[str, object] = {
        "type": "pipeline_ref_target",
        "ref_type": "branch",
        "ref_name": args.branch,
        "selector": {"type": args.selector_type, "pattern": args.selector},
    }
    if args.commit:
        target["commit"] = {"type": "commit", "hash": args.commit}

    variables = _parse_variables(args.variable)

    if args.dry_run:
        preview = {
            "target": target,
            "variables": variables,
        }
        if args.format == "json":
            print(json.dumps(preview, indent=2))
        else:
            print(f"DRY RUN — would trigger pipeline on branch {args.branch}:")
            print(json.dumps(preview, indent=2))
        return

    result = client.run_pipeline(
        workspace,
        repo_slug,
        target=target,
        variables=variables or None,
    )

    if args.format == "json":
        print(json.dumps(result, indent=2))
        return

    print(
        f"Pipeline {result.get('uuid', '?')} triggered on branch {args.branch} "
        f"with selector {args.selector!r}."
    )


if __name__ == "__main__":
    main()
