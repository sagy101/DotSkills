#!/usr/bin/env python3
"""
confluence-publisher skill — Single Page Publisher

Publishes one markdown file to Confluence with Mermaid→PNG support.
Config-driven: reads .confluence.json from the project root.

Usage:
    # Update existing page
    python publish_page.py --config .confluence.json \
        --file README.md --title "Project Home" --mode update --page-id 123456

    # Create child page
    python publish_page.py --config .confluence.json \
        --file plan/README.md --title "Design & Plan" --mode create --parent-id 123456

    # With attachments
    python publish_page.py --config .confluence.json \
        --file docs/setup.md --title "Setup Guide" --mode create --parent-id 123456 \
        --attachments "docs/diagram.pdf,docs/schema.png"

Output: prints PAGE_ID=<id> on success (for chaining parent IDs).
Manifest: auto-updates .confluence-manifest.json with {file → {id, title, parent_id, last_published}}.
"""

import argparse
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests  # type: ignore[import-untyped]

# ---------------------------------------------------------------------------
# Ensure script dir is on path for shared module imports
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from confluence_config import (  # noqa: E402
    ConfluenceConfig,
    add_config_arg,
    connect,
    ensure_deps,
    load_config,
    load_manifest,
    resolve_credentials,
    save_manifest,
)
from page_utils import resolve_title, strip_title_heading  # noqa: E402

ensure_deps({"atlassian-python-api": "atlassian", "markdown": "markdown"})

from atlassian import Confluence  # noqa: E402
from transforms import (  # noqa: E402
    MERMAID_BLOCK_RE,
    inject_image_macros,
    markdown_to_confluence_storage,
    render_mermaid_blocks,
    rewrite_md_links,
)

# ---------------------------------------------------------------------------
# Confluence operations
# ---------------------------------------------------------------------------


def _attach_with_retry(
    confluence: Confluence,
    page_id: str,
    filepath: Path,
    comment: str,
    max_attempts: int = 3,
    backoff: int = 5,
) -> None:
    """Upload a single file as an attachment with retries."""
    for attempt in range(max_attempts):
        try:
            confluence.attach_file(
                filename=str(filepath),
                name=filepath.name,
                page_id=page_id,
                comment=comment,
            )
            return
        except Exception as e:
            if attempt < max_attempts - 1:
                wait = backoff * (attempt + 1)
                print(
                    f"  Upload failed (attempt {attempt + 1}/{max_attempts}), retrying in {wait}s: {e}"
                )
                time.sleep(wait)
            else:
                print(f"  ERROR: Upload failed after {max_attempts} attempts: {e}")
                raise


def _render_and_prepare_body(
    md_content: str,
    tmp_path: Path,
    current_file: str | None,
    manifest: dict[str, Any] | None,
    space_key: str,
) -> tuple[str, list[Path]]:
    """Convert markdown to Confluence storage format, rendering mermaid and rewriting links.

    Returns (body_html, png_files).
    """
    png_files: list[Path] = []

    if MERMAID_BLOCK_RE.search(md_content):
        mermaid_count = len(MERMAID_BLOCK_RE.findall(md_content))
        print(f"  Rendering {mermaid_count} Mermaid diagram(s) to PNG...")
        md_content, png_files = render_mermaid_blocks(md_content, tmp_path)

    body = markdown_to_confluence_storage(md_content)

    if png_files:
        body = inject_image_macros(body)

    if manifest and current_file:
        link_count_before = len(re.findall(r'<a href="[^"]+\.md">', body))
        if link_count_before > 0:
            body = rewrite_md_links(body, current_file, manifest, space_key)
            link_count_after = len(re.findall(r'<a href="[^"]+\.md">', body))
            rewritten = link_count_before - link_count_after
            print(
                f"  Rewriting links: {rewritten}/{link_count_before} resolved to Confluence pages"
            )

    return body, png_files


def _create_or_update(
    confluence: Confluence,
    config: ConfluenceConfig,
    mode: str,
    title: str,
    body: str,
    page_id: str | None,
    parent_id: str | None,
) -> tuple[str, str]:
    """Create or update a page. Returns (result_id, page_url)."""
    if mode == "update":
        existing = confluence.get_page_by_id(page_id, expand="version")
        if not existing:
            print(f"  ERROR: Page {page_id} not found")
            sys.exit(1)
        result = confluence.update_page(
            page_id=page_id,
            title=title,
            body=body,
            type="page",
            representation="storage",
        )
        result_id = page_id
    else:
        result = confluence.create_page(
            space=config.space_key,
            title=title,
            body=body,
            parent_id=parent_id,
            type="page",
            representation="storage",
        )
        result_id = result.get("id", "")

    page_url = f"{config.confluence_url}/pages/{result_id}"
    if "_links" in result and "webui" in result["_links"]:
        base_url = result["_links"].get("base", config.confluence_url)
        page_url = base_url + result["_links"]["webui"]

    return str(result_id), page_url


def publish_page(
    confluence: Confluence,
    config: ConfluenceConfig,
    file_path: Path,
    title: str,
    mode: str,
    page_id: str | None = None,
    parent_id: str | None = None,
    current_file: str | None = None,
    manifest: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Publish a single page. Returns (page_id, page_url)."""
    md_content = file_path.read_text(encoding="utf-8")
    md_content = strip_title_heading(md_content, title)

    with tempfile.TemporaryDirectory() as tmp_dir:
        body, png_files = _render_and_prepare_body(
            md_content,
            Path(tmp_dir),
            current_file,
            manifest,
            config.space_key,
        )
        result_id, page_url = _create_or_update(
            confluence,
            config,
            mode,
            title,
            body,
            page_id,
            parent_id,
        )
        if png_files:
            print(f"  Uploading {len(png_files)} diagram attachment(s)...")
            time.sleep(2)
            for i, png in enumerate(png_files):
                _attach_with_retry(
                    confluence, result_id, png, "Mermaid diagram (auto-generated)", backoff=5
                )
                if i < len(png_files) - 1:
                    time.sleep(1)  # throttle to avoid Confluence transaction conflicts
            # Re-save the page body so Confluence resolves ri:attachment
            # references — on initial create, attachments didn't exist yet
            # so Confluence rewrites filenames to UNKNOWN_ATTACHMENT.
            confluence.update_page(
                page_id=result_id,
                title=title,
                body=body,
                type="page",
                representation="storage",
            )

    return result_id, page_url


def _set_content_property(
    base_url: str,
    auth: tuple[str, str],
    page_id: str,
    key: str,
    value: str,
) -> bool:
    """Set a single Confluence content property. Returns True on success."""
    url = f"{base_url}/wiki/rest/api/content/{page_id}/property/{key}"
    resp = requests.put(
        url,
        auth=auth,
        json={"key": key, "value": value, "version": {"number": 1}},
        timeout=30,
    )
    if resp.status_code == 404:
        url_create = f"{base_url}/wiki/rest/api/content/{page_id}/property"
        resp = requests.post(
            url_create,
            auth=auth,
            json={"key": key, "value": value},
            timeout=30,
        )
    if resp.status_code not in (200, 201):
        print(f"  WARNING: Failed to set {key}: {resp.status_code} {resp.text[:120]}")
        return False
    print(f"  Set {key}: {value}")
    return True


def set_page_emoji(
    config: ConfluenceConfig,
    page_id: str,
    emoji: str,
) -> None:
    """Set the page emoji icon via Confluence content properties.

    Args:
        config: Confluence configuration.
        page_id: The page to set the emoji on.
        emoji: Unicode codepoint (e.g. '1f399') or the emoji character itself.
    """
    if len(emoji) <= 2 and not all(c in "0123456789abcdefABCDEF" for c in emoji):
        emoji = f"{ord(emoji):x}"

    auth = resolve_credentials(config)
    for prop in ["emoji-title-published", "emoji-title-draft"]:
        _set_content_property(config.confluence_url, auth, page_id, prop, emoji)


def upload_attachments(
    confluence: Confluence,
    page_id: str,
    attachment_paths: list[Path],
) -> None:
    """Upload files as attachments to a page."""
    for path in attachment_paths:
        if not path.exists():
            print(f"  WARNING: Attachment not found: {path}")
            continue
        size_mb = path.stat().st_size / (1024 * 1024)
        print(f"  Uploading attachment: {path.name} ({size_mb:.1f} MB)")
        _attach_with_retry(confluence, page_id, path, "Uploaded by confluence-publisher skill")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish one markdown file to Confluence")
    add_config_arg(parser)
    parser.add_argument("--file", help="Markdown file (relative to docs_dir)")
    parser.add_argument("--title", help="Confluence page title (default: auto-detect from file)")
    parser.add_argument("--mode", choices=["create", "update"])
    parser.add_argument("--page-id", help="Page ID (for update mode or --attachments-only)")
    parser.add_argument("--parent-id", help="Parent page ID (for create mode)")
    parser.add_argument(
        "--attachments",
        help="Comma-separated attachment paths (relative to docs_dir)",
    )
    parser.add_argument(
        "--attachments-only",
        action="store_true",
        help="Upload attachments only — do not modify page content. Requires --page-id and --attachments.",
    )
    parser.add_argument(
        "--emoji",
        help="Page emoji icon: unicode codepoint (e.g. 1f399) or emoji character",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be published without creating or updating pages",
    )
    args = parser.parse_args()

    if args.attachments_only:
        if not args.page_id:
            parser.error("--attachments-only requires --page-id")
        if not args.attachments:
            parser.error("--attachments-only requires --attachments")
    else:
        if not args.file:
            parser.error("--file is required (unless --attachments-only is set)")
        if not args.mode:
            parser.error("--mode is required (unless --attachments-only is set)")

    return args


def _handle_attachments_only(
    args: argparse.Namespace, config: ConfluenceConfig, confluence: Confluence
) -> None:
    """Handle --attachments-only mode (with dry-run support)."""
    if args.dry_run:
        print(f"[DRY RUN] Would upload attachments to page {args.page_id}")
        print(f"  Target: {config.confluence_url} / {config.space_key}")
        att_paths = [Path(p.strip()) for p in args.attachments.split(",")]
        for p in att_paths:
            full = p if p.is_absolute() else config.docs_root / p
            exists = "exists" if full.exists() else "MISSING"
            print(f"  Would upload: {p} ({exists})")
        print("\n[DRY RUN] No changes made.")
        return

    print(f"Uploading attachments to page {args.page_id}")
    print(f"  Target: {config.confluence_url} / {config.space_key}")
    att_paths = [Path(p.strip()) for p in args.attachments.split(",")]
    resolved = []
    for p in att_paths:
        if not p.is_absolute():
            p = config.docs_root / p
        resolved.append(p)
    upload_attachments(confluence, args.page_id, resolved)
    page_url = f"{config.confluence_url}/pages/{args.page_id}"
    print("\nSUCCESS")
    print(f"PAGE_ID={args.page_id}")
    print(f"PAGE_URL={page_url}")


def _handle_publish(
    args: argparse.Namespace, config: ConfluenceConfig, confluence: Confluence
) -> None:
    """Handle page publish mode (with dry-run support)."""
    manifest = load_manifest(config)

    file_path = config.docs_root / args.file
    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    md_content = file_path.read_text(encoding="utf-8")
    title = args.title or resolve_title(args.file, md_content, config)

    if args.mode == "update" and not args.page_id:
        print("ERROR: --page-id is required for update mode")
        sys.exit(1)

    parent_id = args.parent_id
    if args.mode == "create" and not parent_id:
        parent_id = config.root_page_id

    dry_prefix = "[DRY RUN] " if args.dry_run else ""
    print(f"{dry_prefix}Publishing: {args.file}")
    print(f"  Title:  {title}")
    print(f"  Mode:   {args.mode}")
    print(f"  Target: {config.confluence_url} / {config.space_key}")
    if args.mode == "create":
        print(f"  Parent: {parent_id}")
    else:
        print(f"  Page:   {args.page_id}")
    print(f"  Manifest: {len(manifest)} pages known")

    if args.dry_run:
        _print_dry_run_summary(args, config, md_content, manifest)
        return

    result_id, page_url = publish_page(
        confluence=confluence,
        config=config,
        file_path=file_path,
        title=title,
        mode=args.mode,
        page_id=args.page_id,
        parent_id=parent_id,
        current_file=args.file,
        manifest=manifest,
    )

    if args.attachments:
        att_paths = [config.docs_root / p.strip() for p in args.attachments.split(",")]
        upload_attachments(confluence, result_id, att_paths)

    if args.emoji:
        set_page_emoji(config, result_id, args.emoji)

    manifest[args.file] = {
        "id": str(result_id),
        "title": title,
        "parent_id": str(parent_id) if parent_id else None,
        "last_published": datetime.now(timezone.utc).isoformat(),
    }
    save_manifest(config, manifest)

    print("\nSUCCESS")
    print(f"PAGE_ID={result_id}")
    print(f"PAGE_URL={page_url}")


def _print_dry_run_summary(
    args: argparse.Namespace,
    config: ConfluenceConfig,
    md_content: str,
    manifest: dict[str, Any],
) -> None:
    """Render body and print dry-run summary without publishing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        body, png_files = _render_and_prepare_body(
            md_content,
            Path(tmp_dir),
            args.file,
            manifest,
            config.space_key,
        )
    print(f"  Body size: {len(body):,} chars")
    if png_files:
        print(f"  Mermaid PNGs: {len(png_files)}")
    if args.attachments:
        att_paths = [config.docs_root / p.strip() for p in args.attachments.split(",")]
        for p in att_paths:
            exists = "exists" if p.exists() else "MISSING"
            print(f"  Would attach: {p.name} ({exists})")
    if args.emoji:
        print(f"  Would set emoji: {args.emoji}")
    print("\n[DRY RUN] No changes made.")


def main():
    args = parse_args()

    config = load_config(args.config)
    confluence = connect(config)

    # Test connection
    try:
        confluence.get_space(config.space_key)
    except Exception as e:
        print(f"ERROR: Cannot connect to Confluence space {config.space_key}: {e}")
        sys.exit(1)

    if args.attachments_only:
        _handle_attachments_only(args, config, confluence)
    else:
        _handle_publish(args, config, confluence)


if __name__ == "__main__":
    main()
