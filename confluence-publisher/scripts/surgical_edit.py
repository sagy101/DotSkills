#!/usr/bin/env python3
"""
confluence-publisher skill — Surgical Page Editor

Apply targeted find/replace edits to a Confluence page's storage HTML without
overwriting the entire page. Preserves manual formatting in untouched sections.

This script does NOT involve markdown conversion — it operates directly on
Confluence storage format HTML.

Usage:
    # Apply replacements from a JSON file
    python surgical_edit.py --config .confluence.json \
        --page 1079706804 --replacements edits.json

    # Inline single replacement
    python surgical_edit.py --config .confluence.json \
        --page 1079706804 --find "old text" --replace "new text"

    # Dry run (show diff without pushing)
    python surgical_edit.py --config .confluence.json \
        --page 1079706804 --replacements edits.json --dry-run

    # Replace all occurrences (default: first occurrence only)
    python surgical_edit.py --config .confluence.json \
        --page 1079706804 --find "old" --replace "new" --replace-all

    # Save diff report to file
    python surgical_edit.py --config .confluence.json \
        --page 1079706804 --replacements edits.json --output /tmp/report.txt

Replacements JSON format:
    [
        {"find": "old text 1", "replace": "new text 1"},
        {"find": "old text 2", "replace": "new text 2", "replace_all": true}
    ]
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from confluence_api import fetch_page, update_page_body  # noqa: E402
from confluence_config import add_config_arg, load_config  # noqa: E402
from html_diff import (  # noqa: E402
    format_diff_report,
    normalize_html,
    section_integrity_check,
    semantic_diff,
)
from page_utils import extract_page_id  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply surgical find/replace edits to a Confluence page"
    )
    add_config_arg(parser)
    parser.add_argument(
        "--page",
        required=True,
        help="Page ID, full URL, or tiny link",
    )
    parser.add_argument(
        "--replacements",
        help="Path to JSON file with replacement pairs",
    )
    parser.add_argument("--find", help="Text to find (inline single replacement)")
    parser.add_argument("--replace", help="Text to replace with (inline single replacement)")
    parser.add_argument(
        "--replace-all",
        action="store_true",
        help="Replace all occurrences (default: first only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without pushing",
    )
    parser.add_argument(
        "--output",
        help="Save diff report to file instead of stdout",
    )
    parser.add_argument(
        "--message",
        help="Version message for the Confluence edit",
    )
    parser.add_argument(
        "--check-sections",
        help="Comma-separated list of section markers to verify after edit",
    )
    return parser.parse_args()


def _validate_replacement_item(item: Any, idx: int) -> None:
    """Validate a single replacement dict from a JSON file. Exits on error."""
    if not isinstance(item, dict):
        print(f"ERROR: Replacement #{idx} is not an object")
        sys.exit(1)
    if "find" not in item or "replace" not in item:
        print(f"ERROR: Replacement #{idx} missing 'find' or 'replace' key")
        sys.exit(1)
    if not isinstance(item["find"], str) or not isinstance(item["replace"], str):
        print(f"ERROR: Replacement #{idx} 'find'/'replace' must be strings")
        sys.exit(1)


def _load_replacements_file(path: Path) -> list[dict[str, str]]:
    """Load and validate a replacements JSON file. Exits on error."""
    if not path.exists():
        print(f"ERROR: Replacements file not found: {path}")
        sys.exit(1)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        print("ERROR: Replacements JSON must be a list of {find, replace} objects")
        sys.exit(1)
    for idx, item in enumerate(data, 1):
        _validate_replacement_item(item, idx)
    return data


def load_replacements(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Build the replacement list from CLI args."""
    replacements: list[dict[str, Any]] = []

    if args.replacements:
        replacements.extend(_load_replacements_file(Path(args.replacements)))

    if args.find is not None and args.replace is not None:
        replacements.append(
            {
                "find": args.find,
                "replace": args.replace,
                "replace_all": args.replace_all,
            }
        )
    elif args.find is not None or args.replace is not None:
        print("ERROR: --find and --replace must be used together")
        sys.exit(1)

    if not replacements:
        print("ERROR: No replacements specified. Use --replacements or --find/--replace")
        sys.exit(1)

    return replacements


def _encode_unicode_to_html_entities(text: str) -> str:
    """Encode common Unicode characters to their HTML entity equivalents.

    Handles characters that Confluence stores as named/numeric HTML entities
    but that agents/humans typically type as Unicode (e.g. → vs &rarr;).
    """
    _UNICODE_TO_ENTITY = {
        "\u2192": "&rarr;",  # →
        "\u2190": "&larr;",  # ←
        "\u2194": "&harr;",  # ↔
        "\u2014": "&mdash;",  # —
        "\u2013": "&ndash;",  # –
        "\u2265": "&ge;",  # ≥
        "\u2264": "&le;",  # ≤
        "\u00a0": "&nbsp;",  # non-breaking space
        "\u2026": "&hellip;",  # …
        "\u00d7": "&times;",  # ×
        "\u2018": "&lsquo;",  # '
        "\u2019": "&rsquo;",  # '
        "\u201c": "&ldquo;",  # "
        "\u201d": "&rdquo;",  # "
    }
    result = text
    for char, entity in _UNICODE_TO_ENTITY.items():
        result = result.replace(char, entity)
    return result


def _decode_html_entities(text: str) -> str:
    """Decode HTML entities to Unicode (e.g. &rarr; → →)."""
    import html as html_module

    return html_module.unescape(text)


def _try_entity_normalization(html_content: str, find: str) -> tuple[str, str] | None:
    """Try to match find string by normalizing HTML entities.

    Returns (normalized_find, strategy_name) if a match is found, None otherwise.
    """
    # Strategy 1: encode Unicode in find → HTML entities (most common case:
    # agent typed → but page has &rarr;)
    encoded = _encode_unicode_to_html_entities(find)
    if encoded != find and html_content.count(encoded) > 0:
        return encoded, "Unicode→entity"

    # Strategy 2: decode HTML entities in find → Unicode (less common:
    # agent copied &rarr; but page has →)
    decoded = _decode_html_entities(find)
    if decoded != find and html_content.count(decoded) > 0:
        return decoded, "entity→Unicode"

    return None


def apply_replacements(html: str, replacements: list[dict[str, Any]]) -> tuple[str, list[str]]:
    """Apply replacements to HTML. Returns (modified_html, log_messages).

    Automatically normalizes HTML entities when a find string doesn't match.
    For example, if the find string contains → (Unicode) but the page HTML
    uses &rarr; (entity), the script detects this and matches correctly.
    """
    log = []
    for i, r in enumerate(replacements, 1):
        find = r["find"]
        replace = r["replace"]

        if not find:
            log.append(f"  #{i} SKIPPED: empty 'find' string (would corrupt HTML)")
            continue
        replace_all = r.get("replace_all", False)

        count = html.count(find)
        if count == 0:
            # Try entity normalization before giving up
            normalized = _try_entity_normalization(html, find)
            if normalized:
                norm_find, strategy = normalized
                # Also normalize the replace string the same way
                if strategy == "Unicode→entity":
                    norm_replace = _encode_unicode_to_html_entities(replace)
                else:
                    norm_replace = _decode_html_entities(replace)
                count = html.count(norm_find)
                log.append(
                    f"  #{i} Auto-normalized ({strategy}): '{find[:40]}...' → '{norm_find[:40]}...'"
                )
                find = norm_find
                replace = norm_replace
            else:
                log.append(f"  #{i} NOT FOUND: {find[:80]}...")
                continue

        if replace_all:
            html = html.replace(find, replace)
            log.append(
                f"  #{i} Replaced {count} occurrence(s): {find[:60]}... -> {replace[:60]}..."
            )
        else:
            html = html.replace(find, replace, 1)
            log.append(
                f"  #{i} Replaced 1 of {count} occurrence(s): {find[:60]}... -> {replace[:60]}..."
            )

    return html, log


def main():
    args = parse_args()
    config = load_config(args.config)
    page_id = extract_page_id(args.page)
    replacements = load_replacements(args)

    # Fetch current page
    print(f"Fetching page {page_id}...")
    snapshot = fetch_page(config, page_id)
    print(f"  Title:   {snapshot.title}")
    print(f"  Version: {snapshot.version}")
    print(f"  Size:    {len(snapshot.html)} chars")
    print()

    # Apply replacements
    print(f"Applying {len(replacements)} replacement(s)...")
    modified_html, log = apply_replacements(snapshot.html, replacements)
    for msg in log:
        print(msg)
    print()

    if modified_html == snapshot.html:
        print("No changes were made (all find strings not found or identical).")
        sys.exit(0)

    # Compute semantic diff
    old_normalized = normalize_html(snapshot.html)
    new_normalized = normalize_html(modified_html)
    changes = semantic_diff(old_normalized, new_normalized)

    # Section integrity check
    markers = None
    if args.check_sections:
        markers = [m.strip() for m in args.check_sections.split(",")]
    integrity = section_integrity_check(snapshot.html, modified_html, markers)

    # Format report
    report = format_diff_report(changes, integrity)

    # Output report
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Diff report saved to {args.output}")
    else:
        print(report)

    # Summary
    print(
        f"HTML size: {len(snapshot.html)} -> {len(modified_html)} ({len(modified_html) - len(snapshot.html):+d} chars)"
    )

    if args.dry_run:
        print("\n[DRY RUN] No changes pushed to Confluence.")
        sys.exit(0)

    # Push update
    version_msg = args.message or f"Surgical edit: {len(replacements)} replacement(s)"
    new_version = update_page_body(
        config,
        page_id,
        snapshot.title,
        modified_html,
        message=version_msg,
    )
    print(f"\nPage updated to version {new_version}")
    print(f"  {config.confluence_url}/pages/{page_id}")


if __name__ == "__main__":
    main()
