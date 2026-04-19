#!/usr/bin/env python3
"""Search Confluence content using CQL queries."""

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from confluence_api import search_cql  # noqa: E402
from confluence_config import load_config  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Search Confluence using CQL")
    parser.add_argument(
        "--cql",
        required=True,
        help="CQL query (e.g. 'type=page AND space=DOCS AND title~\"API\"')",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Maximum results (default: 25)",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    args = parser.parse_args()

    config = load_config()
    results = search_cql(config, args.cql, limit=args.limit)

    if not results:
        print("No results found.")
        return

    if args.format == "json":
        import json
        from dataclasses import asdict

        print(json.dumps([asdict(r) for r in results], indent=2))
        return

    print(f"{'ID':<12} {'Type':<8} {'Space':<10} Title")
    print("-" * 70)
    for r in results:
        print(f"{r.content_id:<12} {r.content_type:<8} {r.space_key:<10} {r.title}")
    print(f"\nTotal: {len(results)}")


if __name__ == "__main__":
    main()
