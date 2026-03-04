#!/usr/bin/env python3
"""
confluence-publisher skill — Manifest Validator

Validates that manifest entries are consistent with both local files and Confluence.
Checks:
  1. Each MD file in the manifest exists on disk
  2. Each Confluence page exists and the title matches
  3. Reports mismatches so they can be fixed

Usage:
    python validate_manifest.py --config .confluence.json
"""

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from config_loader import add_config_arg, load_config, connect, load_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate confluence manifest")
    add_config_arg(parser)
    return parser.parse_args()


def fetch_page_title(confluence, page_id: str):
    """Fetch page title from Confluence. Returns (exists: bool, title: str|None)."""
    try:
        page = confluence.get_page_by_id(page_id)
        if page:
            return True, page["title"]
    except Exception:
        pass
    return False, None


def classify_entry(file_exists: bool, page_exists: bool, actual_title, expected_title) -> str:
    """Return a status string for one manifest entry."""
    if file_exists and page_exists and actual_title == expected_title:
        return "OK"
    if not file_exists:
        return "NO FILE"
    if not page_exists:
        return "NO PAGE"
    return "TITLE"


def print_suggested_fixes(results: list) -> None:
    """Print suggested fixes for entries with issues."""
    print("\nSuggested fixes:")
    for md_file, status, info, actual_title in results:
        if status == "NO FILE":
            print(f'  "{md_file}": file missing on disk — remove from manifest or create file')
        elif status == "NO PAGE":
            print(f'  "{md_file}": page {info["id"]} not found — remove from manifest or re-create')
        elif status == "TITLE":
            print(f'  "{md_file}": update manifest title to "{actual_title}"')


def main():
    args = parse_args()
    config = load_config(args.config)
    manifest = load_manifest(config)

    if not manifest:
        print("ERROR: Manifest is empty or not found")
        print(f"  Expected at: {config.manifest_file}")
        print("  Run discover_pages.py or publish pages first.")
        sys.exit(1)

    confluence = connect(config)

    counts = {"OK": 0, "TITLE": 0, "NO FILE": 0, "NO PAGE": 0}
    results = []

    print(f"Validating {len(manifest)} manifest entries...")
    print(f"  Config:   {config.confluence_url} / {config.space_key}")
    print(f"  Docs dir: {config.docs_root}")
    print()
    print(f"{'Status':<10} {'MD File':<50} {'Expected Title':<35} {'Actual Title'}")
    print("-" * 140)

    for md_file, info in sorted(manifest.items()):
        file_path = config.docs_root / md_file
        file_exists = file_path.exists()
        page_exists, actual_title = fetch_page_title(confluence, info["id"])

        status = classify_entry(file_exists, page_exists, actual_title, info["title"])
        counts[status] = counts.get(status, 0) + 1
        results.append((md_file, status, info, actual_title))

        actual_display = actual_title or "(not found)"
        file_flag = "" if file_exists else " [MISSING]"
        print(f"{status:<10} {md_file + file_flag:<50} {info['title']:<35} {actual_display}")

    print("-" * 140)
    errs = counts.get("NO FILE", 0) + counts.get("NO PAGE", 0)
    warns = counts.get("TITLE", 0)
    print(f"\nSummary: {counts['OK']} OK, {warns} title mismatches, {errs} errors")

    if warns > 0 or errs > 0:
        print_suggested_fixes([r for r in results if r[1] != "OK"])
        sys.exit(1)
    else:
        print("\nAll manifest entries are valid.")


if __name__ == "__main__":
    main()
