#!/usr/bin/env python3
"""
confluence-publisher skill — Hierarchy Verifier

Walks the Confluence page tree from root_page_id and prints the actual hierarchy,
cross-referencing with the manifest to show which pages are tracked.

Usage:
    python verify_hierarchy.py --config .confluence.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atlassian import Confluence

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from confluence_config import add_config_arg, connect, load_config, load_manifest  # noqa: E402
from page_utils import get_all_children  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Confluence page hierarchy")
    add_config_arg(parser)
    return parser.parse_args()


def get_children(confluence: Confluence, page_id: str) -> list[tuple[str, str]]:
    children = get_all_children(confluence, page_id)
    return [(c["id"], c["title"]) for c in children]


def print_tree(
    confluence: Confluence,
    page_id: str,
    title: str,
    manifest_lookup: dict[str, str],
    visited_ids: set[str],
    indent: int = 0,
) -> None:
    visited_ids.add(page_id)
    prefix = "  " * indent + ("|- " if indent > 0 else "")
    manifest_file = manifest_lookup.get(page_id, "")
    marker = f" <- {manifest_file}" if manifest_file else " [NOT IN MANIFEST]"
    print(f"{prefix}{title} (id={page_id}){marker}")

    children = get_children(confluence, page_id)
    for child_id, child_title in sorted(children, key=lambda x: x[1]):
        print_tree(confluence, child_id, child_title, manifest_lookup, visited_ids, indent + 1)


def main():
    args = parse_args()
    config = load_config(args.config)

    confluence = connect(config)

    manifest = load_manifest(config)
    manifest_lookup = {info["id"]: md_file for md_file, info in manifest.items()}

    root = confluence.get_page_by_id(config.root_page_id)
    if not root:
        print(f"ERROR: Root page {config.root_page_id} not found")
        sys.exit(1)

    print(f"Confluence Hierarchy under: {root['title']}")
    print(f"  URL:   {config.confluence_url}")
    print(f"  Space: {config.space_key}")
    print()
    tree_ids = set()
    print_tree(confluence, config.root_page_id, root["title"], manifest_lookup, tree_ids)

    print("\n--- Manifest entries NOT in tree ---")
    orphans = 0
    for md_file, info in sorted(manifest.items()):
        if info["id"] not in tree_ids:
            print(f'  {md_file}: id={info["id"]} title="{info["title"]}"')
            orphans += 1
    if orphans == 0:
        print("  (none)")


if __name__ == "__main__":
    main()
