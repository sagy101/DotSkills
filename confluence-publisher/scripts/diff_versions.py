#!/usr/bin/env python3
"""
confluence-publisher skill — Version Diff

Compare two versions of the same Confluence page and produce a semantic diff
report showing exactly what changed. Strips Confluence noise attributes
(ac:local-id, local-id, data-table-width) for clean comparison.

Usage:
    # Diff version 56 vs latest
    python diff_versions.py --config .confluence.json \
        --page 1079706804 --from-version 56

    # Diff version 56 vs version 59
    python diff_versions.py --config .confluence.json \
        --page 1079706804 --from-version 56 --to-version 59

    # Save report to file (avoids terminal truncation)
    python diff_versions.py --config .confluence.json \
        --page 1079706804 --from-version 56 --output /tmp/diff.txt

    # Check that specific sections survived the edit
    python diff_versions.py --config .confluence.json \
        --page 1079706804 --from-version 56 \
        --check-sections "Problem Definition,Solution Architecture,Risk & Mitigation"

    # Auto-detect sections from headings (no --check-sections needed)
    python diff_versions.py --config .confluence.json \
        --page 1079706804 --from-version 56
"""

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from config_loader import add_config_arg, load_config
from page_utils import extract_page_id
from confluence_api import fetch_page
from html_diff import (
    normalize_html,
    semantic_diff,
    section_integrity_check,
    format_diff_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare two versions of a Confluence page"
    )
    add_config_arg(parser)
    parser.add_argument(
        "--page",
        required=True,
        help="Page ID, full URL, or tiny link",
    )
    parser.add_argument(
        "--from-version",
        required=True,
        type=int,
        help="Version number to compare FROM (older)",
    )
    parser.add_argument(
        "--to-version",
        type=int,
        default=None,
        help="Version number to compare TO (newer). Default: latest",
    )
    parser.add_argument(
        "--output",
        help="Save report to file instead of printing to stdout",
    )
    parser.add_argument(
        "--check-sections",
        help="Comma-separated list of section markers to verify. "
             "Default: auto-detect from headings in the older version",
    )
    parser.add_argument(
        "--max-text-len",
        type=int,
        default=500,
        help="Max length of text snippets in the report (default: 500)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config(args.config)
    page_id = extract_page_id(args.page)

    # Fetch both versions
    print(f"Fetching version {args.from_version}...")
    old_snap = fetch_page(config, page_id, version=args.from_version)
    print(f"  Title:   {old_snap.title}")
    print(f"  Author:  {old_snap.by}")
    print(f"  Date:    {old_snap.when}")
    print(f"  Size:    {len(old_snap.html)} chars")

    to_label = f"version {args.to_version}" if args.to_version else "latest"
    print(f"\nFetching {to_label}...")
    new_snap = fetch_page(config, page_id, version=args.to_version)
    print(f"  Title:   {new_snap.title}")
    print(f"  Version: {new_snap.version}")
    print(f"  Author:  {new_snap.by}")
    print(f"  Date:    {new_snap.when}")
    print(f"  Size:    {len(new_snap.html)} chars")
    print()

    # Normalize and diff
    old_norm = normalize_html(old_snap.html)
    new_norm = normalize_html(new_snap.html)

    if old_norm == new_norm:
        print("No semantic differences found (only noise attributes changed).")
        sys.exit(0)

    changes = semantic_diff(old_norm, new_norm)

    # Section integrity
    markers = None
    if args.check_sections:
        markers = [m.strip() for m in args.check_sections.split(",")]
    integrity = section_integrity_check(old_snap.html, new_snap.html, markers)

    # Build report
    header = (
        f"Page: {old_snap.title} (id={page_id})\n"
        f"Comparing: v{old_snap.version} ({old_snap.when}) -> v{new_snap.version} ({new_snap.when})\n"
        f"HTML size: {len(old_snap.html)} -> {len(new_snap.html)} "
        f"({len(new_snap.html) - len(old_snap.html):+d} chars)\n\n"
    )
    report = header + format_diff_report(changes, integrity, max_text_len=args.max_text_len)

    # Output
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Report saved to {args.output} ({len(changes)} changes)")
    else:
        print(report)

    # Exit code: 1 if changes found (like diff command)
    if changes:
        sys.exit(1)


if __name__ == "__main__":
    main()
