#!/usr/bin/env python3
"""
confluence-publisher skill — Hierarchy Verifier

Walks the Confluence page tree from root_page_id and prints the actual hierarchy,
cross-referencing with the manifest to show which pages are tracked.

Usage:
    python verify_hierarchy.py --config .confluence.json
"""

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from config_loader import load_config, connect, load_manifest, get_all_children


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Confluence page hierarchy")
    parser.add_argument(
        "--config",
        help="Path to .confluence.json (default: auto-detect from cwd up)",
    )
    return parser.parse_args()


def get_children(confluence, page_id: str) -> list:
    children = get_all_children(confluence, page_id)
    return [(c["id"], c["title"]) for c in children]


def print_tree(confluence, page_id, title, manifest_lookup, visited_ids, indent=0):
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
