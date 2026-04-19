#!/usr/bin/env python3
"""List Confluence pages in a space using REST v2."""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from confluence_api import list_pages  # noqa: E402
from confluence_config import load_config  # noqa: E402


def _serialise(items: Sequence[Any]) -> list[Any]:
    serialised: list[Any] = []
    for item in items:
        if not isinstance(item, type) and is_dataclass(item):
            serialised.append(asdict(item))
        else:
            serialised.append(item)
    return serialised


def main() -> None:
    parser = argparse.ArgumentParser(description="List Confluence pages in a space")
    parser.add_argument("--space-key", help="Space key to list pages from (defaults to config)")
    parser.add_argument("--title", help="Filter by page title")
    parser.add_argument("--status", help="Filter by page status")
    parser.add_argument("--type", dest="page_type", help="Filter by page subtype")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--format", choices=["table", "json"], default="table")
    args = parser.parse_args()

    config = load_config()
    pages = list_pages(
        config,
        space_key=args.space_key,
        title=args.title,
        status=args.status,
        page_type=args.page_type,
        limit=args.limit,
    )

    if not pages:
        print("No pages found.")
        return

    if args.format == "json":
        print(json.dumps(_serialise(pages), indent=2))
        return

    print(f"{'ID':<12} {'Status':<10} {'Type':<12} Title")
    print("-" * 80)
    for page in pages:
        print(
            f"{getattr(page, 'page_id', ''):<12} "
            f"{getattr(page, 'status', ''):<10} "
            f"{getattr(page, 'subtype', ''):<12} "
            f"{getattr(page, 'title', '')}"
        )
    print(f"\nTotal: {len(pages)}")


if __name__ == "__main__":
    main()
