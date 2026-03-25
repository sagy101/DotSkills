#!/usr/bin/env python3
"""Find and render mermaid code blocks on a Confluence page to PNG images.

Scans the page HTML for code blocks with language="mermaid", renders each to
PNG via mmdc (Mermaid CLI), uploads PNGs as page attachments, and replaces
the code blocks with <ac:image> macros pointing to the uploaded PNGs.

Usage:
    python render_mermaid.py --page 1079706804
    python render_mermaid.py --page 1079706804 --dry-run
    python render_mermaid.py --page https://company.atlassian.net/wiki/spaces/X/pages/123/Title
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from confluence_api import fetch_page, update_page_body  # noqa: E402
from confluence_config import add_config_arg, connect, load_config  # noqa: E402
from page_utils import extract_page_id  # noqa: E402

# Pattern for Confluence code macro with language=mermaid
MERMAID_CODE_RE = re.compile(
    r'<ac:structured-macro[^>]*ac:name="code"[^>]*>'
    r".*?<ac:parameter\s+ac:name=\"language\">mermaid</ac:parameter>"
    r".*?<ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>"
    r".*?</ac:structured-macro>",
    re.DOTALL,
)


def _find_mmdc() -> str | None:
    """Find the mmdc binary (Mermaid CLI)."""
    mmdc = shutil.which("mmdc")
    if mmdc:
        return mmdc
    # Try npx
    try:
        result = subprocess.run(
            ["npx", "--yes", "@mermaid-js/mermaid-cli", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return "npx"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _render_mermaid_to_png(mermaid_src: str, output_path: Path, mmdc_path: str) -> bool:
    """Render mermaid source to a PNG file. Returns True on success."""
    mmd_file = output_path.with_suffix(".mmd")
    mmd_file.write_text(mermaid_src, encoding="utf-8")

    if mmdc_path == "npx":
        cmd = [
            "npx",
            "-y",
            "-p",
            "@mermaid-js/mermaid-cli",
            "mmdc",
            "-i",
            str(mmd_file),
            "-o",
            str(output_path),
            "-b",
            "transparent",
            "--scale",
            "2",
        ]
    else:
        cmd = [
            mmdc_path,
            "-i",
            str(mmd_file),
            "-o",
            str(output_path),
            "-b",
            "transparent",
            "--scale",
            "2",
        ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return result.returncode == 0 and output_path.exists()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def render_mermaid_on_page(
    page_ref: str,
    *,
    config_path: str | None = None,
    dry_run: bool = False,
    width: int = 800,
) -> int:
    """Find and render all mermaid code blocks on a page. Returns count of rendered diagrams."""
    config = load_config(config_path)
    confluence = connect(config)
    page_id = extract_page_id(page_ref)

    page = fetch_page(config, page_id)
    html = page.html

    blocks = list(MERMAID_CODE_RE.finditer(html))
    if not blocks:
        print("No mermaid code blocks found on this page.")
        return 0

    print(f"Found {len(blocks)} mermaid code block(s)")

    if dry_run:
        for i, m in enumerate(blocks, 1):
            src = m.group(1).replace("\\n", "\n")[:80]
            print(f"  #{i}: {src}...")
        print(f"\n[DRY RUN] Would render {len(blocks)} diagram(s). No changes made.")
        return len(blocks)

    mmdc = _find_mmdc()
    if not mmdc:
        print(
            "ERROR: mmdc (Mermaid CLI) not found. Install via: npm install -g @mermaid-js/mermaid-cli"
        )
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        new_html = html
        rendered_count = 0

        # Process in reverse order to preserve positions
        for i, m in enumerate(reversed(blocks), 1):
            idx = len(blocks) - i
            mermaid_src = m.group(1).replace("\\n", "\n")
            png_name = f"mermaid-diagram-{idx + 1}.png"
            png_path = tmp_path / png_name

            print(f"  Rendering diagram {idx + 1}/{len(blocks)}...")
            if _render_mermaid_to_png(mermaid_src, png_path, mmdc):
                # Upload as attachment
                try:
                    confluence.attach_file(str(png_path), name=png_name, page_id=page_id)
                    size_kb = png_path.stat().st_size / 1024
                    print(f"    Uploaded {png_name} ({size_kb:.0f} KB)")
                except Exception as e:
                    print(f"    WARNING: Failed to upload {png_name}: {e}")
                    continue

                # Replace code block with image macro
                img_macro = (
                    f'<ac:image ac:width="{width}">'
                    f'<ri:attachment ri:filename="{png_name}" />'
                    f"</ac:image>"
                )
                new_html = new_html[: m.start()] + img_macro + new_html[m.end() :]
                rendered_count += 1
            else:
                print(f"    WARNING: Failed to render diagram {idx + 1}")

        if rendered_count > 0:
            update_page_body(
                config,
                page_id,
                page.title,
                new_html,
                message=f"Render {rendered_count} mermaid diagram(s) to PNG",
            )
            print(f"\nRendered {rendered_count}/{len(blocks)} diagram(s)")
            print(f"  Page updated to version {page.version + 1}")
        else:
            print("\nNo diagrams were rendered successfully.")

    return rendered_count


def main():
    parser = argparse.ArgumentParser(
        description="Render mermaid code blocks on a Confluence page to PNG images"
    )
    add_config_arg(parser)
    parser.add_argument("--page", required=True, help="Page ID, full URL, or tiny link")
    parser.add_argument("--dry-run", action="store_true", help="Show blocks without rendering")
    parser.add_argument(
        "--width", type=int, default=800, help="Image width in pixels (default: 800)"
    )
    args = parser.parse_args()

    page_id = extract_page_id(args.page)
    print(f"Scanning page {page_id} for mermaid code blocks...")

    count = render_mermaid_on_page(
        args.page,
        config_path=args.config,
        dry_run=args.dry_run,
        width=args.width,
    )
    sys.exit(0 if count >= 0 else 1)


if __name__ == "__main__":
    main()
