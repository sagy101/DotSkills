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
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure script dir is on path for shared module imports
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from config_loader import (
    load_config,
    resolve_credentials,
    load_manifest,
    save_manifest,
    resolve_title,
    ensure_deps,
    ConfluenceConfig,
)

ensure_deps({"atlassian-python-api": "atlassian", "markdown": "markdown"})

from atlassian import Confluence  # noqa: E402
from transforms import (  # noqa: E402
    MERMAID_BLOCK_RE,
    markdown_to_confluence_storage,
    rewrite_md_links,
    render_mermaid_blocks,
    inject_image_macros,
)


# ---------------------------------------------------------------------------
# Confluence operations
# ---------------------------------------------------------------------------


def connect(config: ConfluenceConfig) -> Confluence:
    username, token = resolve_credentials(config)
    return Confluence(
        url=config.confluence_url,
        username=username,
        password=token,
        cloud=True,
    )


def publish_page(
    confluence: Confluence,
    config: ConfluenceConfig,
    file_path: Path,
    title: str,
    mode: str,
    page_id: str | None = None,
    parent_id: str | None = None,
    current_file: str | None = None,
    manifest: dict | None = None,
) -> tuple:
    """Publish a single page. Returns (page_id, page_url)."""
    md_content = file_path.read_text(encoding="utf-8")

    has_mermaid = bool(MERMAID_BLOCK_RE.search(md_content))
    png_files: list = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        if has_mermaid:
            mermaid_count = len(MERMAID_BLOCK_RE.findall(md_content))
            print(f"  Rendering {mermaid_count} Mermaid diagram(s) to PNG...")
            md_content, png_files = render_mermaid_blocks(md_content, tmp_path)

        body = markdown_to_confluence_storage(md_content)

        if png_files:
            body = inject_image_macros(body)

        if manifest and current_file:
            link_count_before = len(re.findall(r'<a href="[^"]+\.md">', body))
            if link_count_before > 0:
                body = rewrite_md_links(body, current_file, manifest, config.space_key)
                link_count_after = len(re.findall(r'<a href="[^"]+\.md">', body))
                rewritten = link_count_before - link_count_after
                print(f"  Rewriting links: {rewritten}/{link_count_before} resolved to Confluence pages")

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
            base_url = config.confluence_url.removesuffix("/wiki")
            page_url = base_url + result["_links"]["webui"]

        if png_files:
            print(f"  Uploading {len(png_files)} diagram attachment(s)...")
            for png in png_files:
                confluence.attach_file(
                    filename=str(png),
                    name=png.name,
                    page_id=result_id,
                    comment="Mermaid diagram (auto-generated)",
                )

    return result_id, page_url


def upload_attachments(
    confluence: Confluence,
    page_id: str,
    attachment_paths: list,
) -> None:
    """Upload files as attachments to a page."""
    for path in attachment_paths:
        if not path.exists():
            print(f"  WARNING: Attachment not found: {path}")
            continue
        print(f"  Uploading attachment: {path.name}")
        confluence.attach_file(
            filename=str(path),
            name=path.name,
            page_id=page_id,
            comment="Uploaded by confluence-publisher skill",
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish one markdown file to Confluence"
    )
    parser.add_argument(
        "--config",
        help="Path to .confluence.json (default: auto-detect from cwd up)",
    )
    parser.add_argument("--file", required=True, help="Markdown file (relative to docs_dir)")
    parser.add_argument("--title", help="Confluence page title (default: auto-detect from file)")
    parser.add_argument("--mode", required=True, choices=["create", "update"])
    parser.add_argument("--page-id", help="Page ID (for update mode)")
    parser.add_argument("--parent-id", help="Parent page ID (for create mode)")
    parser.add_argument(
        "--attachments",
        help="Comma-separated attachment paths (relative to docs_dir)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    config = load_config(args.config)
    manifest = load_manifest(config)

    file_path = config.docs_root / args.file
    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    # Resolve title
    md_content = file_path.read_text(encoding="utf-8")
    title = args.title or resolve_title(args.file, md_content, config)

    # Resolve parent_id for creates
    parent_id = args.parent_id
    if args.mode == "create" and not parent_id:
        parent_id = config.root_page_id

    print(f"Publishing: {args.file}")
    print(f"  Title:  {title}")
    print(f"  Mode:   {args.mode}")
    print(f"  Target: {config.confluence_url} / {config.space_key}")
    print(f"  Manifest: {len(manifest)} pages known")

    confluence = connect(config)

    # Test connection
    try:
        confluence.get_space(config.space_key)
    except Exception as e:
        print(f"ERROR: Cannot connect to Confluence space {config.space_key}: {e}")
        sys.exit(1)

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

    # Update manifest
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


if __name__ == "__main__":
    main()
