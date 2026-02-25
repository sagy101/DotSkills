"""
confluence-publisher skill — Shared Markdown/Confluence Transforms

All markdown → Confluence storage format conversions live here so that
publish_page.py and diff_pages.py share the same logic.
"""

import html
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


ATTACHMENT_LINK_RE = re.compile(
    r'<a href="attachment:([^"]+)">(.*?)</a>', re.DOTALL
)


def rewrite_attachment_links(html_content: str) -> str:
    """Replace ``attachment:filename`` links with Confluence attachment macros.

    Markdown authors use the ``attachment:`` URL scheme to reference files
    that are uploaded as page attachments::

        [My Slides.pdf](attachment:My Slides.pdf)

    This function converts those into Confluence storage-format
    ``<ac:link><ri:attachment …/></ac:link>`` macros.
    """
    def _replace(match):
        filename = html.unescape(match.group(1))
        link_text = match.group(2)
        return (
            f'<ac:link>'
            f'<ri:attachment ri:filename="{filename}"/>'
            f'<ac:plain-text-link-body><![CDATA[{link_text}]]></ac:plain-text-link-body>'
            f'</ac:link>'
        )

    return ATTACHMENT_LINK_RE.sub(_replace, html_content)


def markdown_to_confluence_storage(md_content: str) -> str:
    """Convert Markdown to Confluence storage format (XHTML-based)."""
    html_content = md_lib.markdown(
        md_content,
        extensions=[
            "tables",
            "fenced_code",
            "toc",
            "sane_lists",
        ],
    )

    # Rewrite attachment: links before any other transforms
    html_content = rewrite_attachment_links(html_content)

    def make_code_macro(code: str, lang: str = "") -> str:
        code = html.unescape(code)
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
    html_content = re.sub(
        r'<pre><code class="(?:language-)?(\w+)">(.*?)</code></pre>',
        lambda m: make_code_macro(m.group(2), m.group(1)),
        html_content,
        flags=re.DOTALL,
    )

    # Code blocks without language
    html_content = re.sub(
        r"<pre><code>(.*?)</code></pre>",
        lambda m: make_code_macro(m.group(1)),
        html_content,
        flags=re.DOTALL,
    )

    return html_content


def preprocess_confluence_storage(html_content: str) -> str:
    """
    Pre-process Confluence storage HTML before passing to markdownify.
    Converts <ac:structured-macro ac:name="code"> to <pre><code> blocks
    so they are correctly converted to fenced code blocks.
    """
    def replace_code_macro(match):
        content = match.group(0)
        # Extract language
        lang_match = re.search(r'<ac:parameter ac:name="language">(\w+)</ac:parameter>', content)
        lang = lang_match.group(1) if lang_match else ""

        # Extract body
        # Try CDATA first
        body_match = re.search(r'<ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>', content, re.DOTALL)
        if body_match:
            code = body_match.group(1)
        else:
            # Fallback for non-CDATA (rare but possible)
            body_match = re.search(r'<ac:plain-text-body>(.*?)</ac:plain-text-body>', content, re.DOTALL)
            code = body_match.group(1) if body_match else ""

        # Unescape HTML entities in the code
        code = html.unescape(code)

        class_attr = f' class="language-{lang}"' if lang else ""
        return f'<pre><code{class_attr}>{code}</code></pre>'

    # Regex to find code macros
    # We use a non-greedy match for the content between tags
    pattern = r'<ac:structured-macro[^>]+ac:name="code"[^>]*>.*?</ac:structured-macro>'
    
    return re.sub(
        pattern,
        replace_code_macro,
        html_content,
        flags=re.DOTALL
    )


# ---------------------------------------------------------------------------
# Cross-page link rewriting
# ---------------------------------------------------------------------------


def rewrite_md_links(html_content: str, current_file: str, manifest: dict, space_key: str) -> str:
    """
    Replace <a href="something.md"> links with Confluence page link macros,
    using the manifest to resolve relative paths to page IDs/titles.
    """
    current_dir = Path(current_file).parent

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

        # Handle absolute paths (relative to docs root) vs relative paths
        if href.startswith("/"):
            # absolute path in repo -> relative to docs root
            # remove leading slash to make it relative to root
            resolved = os.path.normpath(href.lstrip("/"))
        else:
            resolved = os.path.normpath(current_dir / href)

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
        html_content,
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
