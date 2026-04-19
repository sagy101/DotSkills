#!/usr/bin/env python3
"""List Confluence spaces."""

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from confluence_api import list_spaces  # noqa: E402
from confluence_config import load_config  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="List Confluence spaces")
    parser.add_argument(
        "--type",
        choices=["global", "personal"],
        dest="space_type",
        help="Filter by space type",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum spaces to return (default: 50)",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    args = parser.parse_args()

    config = load_config()
    spaces = list_spaces(config, space_type=args.space_type, limit=args.limit)

    if not spaces:
        print("No spaces found.")
        return

    if args.format == "json":
        import json
        from dataclasses import asdict

        print(json.dumps([asdict(s) for s in spaces], indent=2))
        return

    print(f"{'Key':<12} {'Type':<10} {'Status':<10} Name")
    print("-" * 60)
    for s in spaces:
        print(f"{s.key:<12} {s.space_type:<10} {s.status:<10} {s.name}")
    print(f"\nTotal: {len(spaces)}")


if __name__ == "__main__":
    main()
