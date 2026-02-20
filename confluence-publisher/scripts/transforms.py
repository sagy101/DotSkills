"""
confluence-publisher skill — Shared Markdown/Confluence Transforms

All markdown → Confluence storage format conversions live here so that
publish_page.py and diff_pages.py share the same logic.
"""

import os
import re
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Dependencies (must be installed before importing this module)
# ---------------------------------------------------------------------------
import markdown as md_lib

# ---------------------------------------------------------------------------
# Mermaid regex (shared constant)
# ---------------------------------------------------------------------------

MERMAID_BLOCK_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)

# ---------------------------------------------------------------------------
# Markdown → Confluence storage format
# ---------------------------------------------------------------------------


def markdown_to_confluence_storage(md_content: str) -> str:
    """Convert Markdown to Confluence storage format (XHTML-based)."""
    html = md_lib.markdown(
        md_content,
        extensions=[
            "tables",
            "fenced_code",
            "codehilite",
            "toc",
            "sane_lists",
        ],
        extension_configs={
            "codehilite": {
                "css_class": "code",
                "guess_lang": False,
            }
        },
    )

    def unescape_html(text: str) -> str:
        return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")

    def make_code_macro(code: str, lang: str = "") -> str:
        code = unescape_html(code)
        if lang:
            return (
                f'<ac:structured-macro ac:name="code">'
                f'<ac:parameter ac:name="language">{lang}</ac:parameter>'
                f"<ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body>"
                f"</ac:structured-macro>"
            )
        return (
            f'<ac:structured-macro ac:name="code">'
            f"<ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body>"
            f"</ac:structured-macro>"
        )

    # Code blocks with language
    html = re.sub(
        r'<pre><code class="(?:language-)?(\w+)">(.*?)</code></pre>',
        lambda m: make_code_macro(m.group(2), m.group(1)),
        html,
        flags=re.DOTALL,
    )

    # Code blocks without language
    html = re.sub(
        r"<pre><code>(.*?)</code></pre>",
        lambda m: make_code_macro(m.group(1)),
        html,
        flags=re.DOTALL,
    )

    return html


# ---------------------------------------------------------------------------
# Cross-page link rewriting
# ---------------------------------------------------------------------------


def rewrite_md_links(html: str, current_file: str, manifest: dict, space_key: str) -> str:
    """
    Replace <a href="something.md"> links with Confluence page link macros,
    using the manifest to resolve relative paths to page IDs/titles.
    """
    current_dir = str(Path(current_file).parent)

    def replace_link(match):
        href = match.group(1)
        link_text = match.group(2)

        # Split off anchor fragment if present (e.g. "setup.md#section")
        anchor = ""
        if "#" in href:
            href, anchor = href.split("#", 1)
            anchor = "#" + anchor

        if not href.endswith(".md"):
            return match.group(0)

        resolved = os.path.normpath(os.path.join(current_dir, href))

        if resolved in manifest:
            page_title = manifest[resolved]["title"]
            anchor_attr = f' ac:anchor="{anchor[1:]}"' if anchor else ""
            return (
                f'<ac:link{anchor_attr}>'
                f'<ri:page ri:content-title="{page_title}" ri:space-key="{space_key}"/>'
                f'<ac:plain-text-link-body><![CDATA[{link_text}]]></ac:plain-text-link-body>'
                f'</ac:link>'
            )

        return match.group(0)

    return re.sub(
        r'<a href="([^"]+)">(.*?)</a>',
        replace_link,
        html,
        flags=re.DOTALL,
    )


# ---------------------------------------------------------------------------
# Mermaid → PNG rendering (used by publish)
# ---------------------------------------------------------------------------


def render_mermaid_blocks(md_content: str, tmp_dir: Path) -> tuple:
    """
    Find ```mermaid blocks, render each to PNG via mmdc, and replace
    with a placeholder that will become a Confluence attachment image macro.

    Returns (modified_markdown, list_of_png_paths).
    """
    png_files: list = []
    counter = 0

    def replace_block(match):
        nonlocal counter
        counter += 1
        mmd_content = match.group(1)
        mmd_file = tmp_dir / f"diagram-{counter}.mmd"
        png_file = tmp_dir / f"diagram-{counter}.png"

        mmd_file.write_text(mmd_content, encoding="utf-8")

        try:
            subprocess.run(
                [
                    "npx", "-y", "-p", "@mermaid-js/mermaid-cli", "mmdc",
                    "-i", str(mmd_file),
                    "-o", str(png_file),
                    "-b", "transparent",
                    "--scale", "2",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"  WARNING: Mermaid render failed for diagram-{counter}: {e}")
            return f"```\n{mmd_content}```"

        if png_file.exists():
            png_files.append(png_file)
            return f"<!-- MERMAID_IMG:diagram-{counter}.png -->"
        else:
            print(f"  WARNING: PNG not generated for diagram-{counter}")
            return f"```\n{mmd_content}```"

    modified = MERMAID_BLOCK_RE.sub(replace_block, md_content)
    return modified, png_files


def inject_image_macros(html: str) -> str:
    """Replace mermaid placeholders with Confluence attachment image macros."""
    def replace_placeholder(match):
        filename = match.group(1)
        return (
            f'<ac:image ac:width="800">'
            f'<ri:attachment ri:filename="{filename}"/>'
            f'</ac:image>'
        )

    return re.sub(
        r"<!-- MERMAID_IMG:(\S+?) -->",
        replace_placeholder,
        html,
    )


# ---------------------------------------------------------------------------
# Mermaid placeholder stripping (used by diff — no PNG rendering needed)
# ---------------------------------------------------------------------------


def strip_mermaid_blocks(md_content: str) -> str:
    """Replace mermaid blocks with stable placeholders for diffing."""
    counter = 0

    def replace_block(match):
        nonlocal counter
        counter += 1
        return f"[mermaid-diagram-{counter}]"

    return MERMAID_BLOCK_RE.sub(replace_block, md_content)


def normalize_remote_mermaid_macros(html: str) -> str:
    """Replace Confluence image macros for mermaid diagram PNGs with the same
    stable placeholders used by strip_mermaid_blocks."""
    counter = 0

    def replace_diagram_image(match):
        nonlocal counter
        counter += 1
        return f"[mermaid-diagram-{counter}]"

    return re.sub(
        r'<ac:image[^>]*>\s*<ri:attachment ri:filename="diagram-\d+\.png"\s*/>\s*</ac:image>',
        replace_diagram_image,
        html,
    )
