"""
Bidirectional Markdown <-> Jira Wiki Markup converter.

Provides:
    md_to_jira_markup(text)   — Convert GitHub-flavored Markdown to Jira wiki markup
    jira_markup_to_md(text)   — Convert Jira wiki markup to Markdown

The MD→Jira path uses the `markdown` library (MD→HTML) then regex-based
HTML→Jira conversion for maximum fidelity.

The Jira→MD path uses direct regex translation of Jira wiki syntax to
Markdown, then optionally the `markdownify` library for any residual HTML.

Mirrors the confluence-publisher skill pattern (markdown + markdownify deps).
"""

import html as html_lib
import re
import shutil
import subprocess
import sys
import tempfile
import types
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# ---------------------------------------------------------------------------
# Lazy dependency loading
# ---------------------------------------------------------------------------

_markdown_lib: types.ModuleType | None = None
_markdownify: Callable[..., str] | None = None


def _get_markdown() -> types.ModuleType:
    global _markdown_lib
    if _markdown_lib is None:
        try:
            import markdown  # type: ignore[import-untyped]

            _markdown_lib = markdown
        except ImportError:
            print(
                "ERROR: 'markdown' package not installed. "
                "Run: python3 <skill_dir>/scripts/setup_env.py",
                file=sys.stderr,
            )
            sys.exit(1)
    return _markdown_lib


def _get_markdownify() -> Callable[..., str]:
    global _markdownify
    if _markdownify is None:
        try:
            from markdownify import markdownify as md_convert  # type: ignore[import-untyped]

            _markdownify = md_convert
        except ImportError:
            print(
                "ERROR: 'markdownify' package not installed. "
                "Run: python3 <skill_dir>/scripts/setup_env.py",
                file=sys.stderr,
            )
            sys.exit(1)
    return _markdownify


# ===================================================================
# Markdown → Jira Wiki Markup
# ===================================================================


def _html_to_jira(html_content: str) -> str:
    """Convert HTML (from the markdown library) to Jira wiki markup."""
    text = html_content

    # --- Code blocks (must be done before inline code) ---
    # Fenced code blocks with language
    text = re.sub(
        r'<pre><code class="(?:language-)?(\w+)">(.*?)</code></pre>',
        lambda m: "{code:"
        + m.group(1)
        + "}\n"
        + html_lib.unescape(m.group(2)).strip()
        + "\n{code}",
        text,
        flags=re.DOTALL,
    )
    # Fenced code blocks without language
    text = re.sub(
        r"<pre><code>(.*?)</code></pre>",
        lambda m: "{code}\n" + html_lib.unescape(m.group(1)).strip() + "\n{code}",
        text,
        flags=re.DOTALL,
    )

    # --- Inline code ---
    text = re.sub(r"<code>(.*?)</code>", r"{{\1}}", text)

    # --- Headings ---
    for level in range(6, 0, -1):
        text = re.sub(
            rf"<h{level}>(.*?)</h{level}>",
            rf"h{level}. \1\n",
            text,
        )

    # --- Bold ---
    text = re.sub(r"<strong>(.*?)</strong>", r"*\1*", text)

    # --- Italic ---
    text = re.sub(r"<em>(.*?)</em>", r"_\1_", text)

    # --- Strikethrough ---
    text = re.sub(r"<del>(.*?)</del>", r"-\1-", text)

    # --- Links ---
    text = re.sub(r'<a href="([^"]+)"[^>]*>(.*?)</a>', r"[\2|\1]", text)

    # --- Images ---
    text = re.sub(r'<img[^>]+src="([^"]+)"[^>]*alt="([^"]*)"[^>]*/?>', r"!\1!", text)
    text = re.sub(r'<img[^>]+src="([^"]+)"[^>]*/?>', r"!\1!", text)

    # --- Tables ---
    text = _convert_html_tables(text)

    # --- Lists ---
    text = _convert_html_lists(text)

    # --- Blockquotes ---
    text = re.sub(
        r"<blockquote>(.*?)</blockquote>",
        lambda m: "{quote}\n" + m.group(1).strip() + "\n{quote}",
        text,
        flags=re.DOTALL,
    )

    # --- Horizontal rules ---
    text = re.sub(r"<hr\s*/?>", "----", text)

    # --- Paragraphs ---
    # Use \n\n before content to ensure a blank line separates paragraphs from
    # preceding list items.  Without this, Jira wiki markup interprets bold
    # labels (e.g. *DoD:*) as list continuations when they follow ** items.
    text = re.sub(r"<p>(.*?)</p>", r"\n\n\1\n", text, flags=re.DOTALL)

    # --- Line breaks ---
    text = re.sub(r"<br\s*/?>", "\n", text)

    # --- Strip remaining HTML tags ---
    text = re.sub(r"</?[^>]+>", "", text)

    # --- Unescape HTML entities ---
    text = html_lib.unescape(text)

    # --- Ensure blank line before headings ---
    # Jira wiki requires a blank line before h1.-h6. headings for proper rendering.
    text = re.sub(r"(?<!\n)\n(h[1-6]\. )", r"\n\n\1", text)

    # --- Clean up excessive blank lines ---
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _convert_html_tables(text: str) -> str:
    """Convert HTML tables to Jira wiki markup tables."""

    def _table_to_jira(match: re.Match[str]) -> str:
        table_html = match.group(0)
        rows = re.findall(r"<tr>(.*?)</tr>", table_html, re.DOTALL)
        jira_rows = []

        for row in rows:
            # Header cells
            headers = re.findall(r"<th[^>]*>(.*?)</th>", row, re.DOTALL)
            if headers:
                cells = [c.strip() for c in headers]
                jira_rows.append("|| " + " || ".join(cells) + " ||")
                continue

            # Data cells
            data = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
            if data:
                cells = [c.strip() for c in data]
                jira_rows.append("| " + " | ".join(cells) + " |")

        return "\n".join(jira_rows)

    return re.sub(r"<table>.*?</table>", _table_to_jira, text, flags=re.DOTALL)


def _find_balanced_tag(
    src: str, open_tag: str, close_tag: str, start: int = 0
) -> tuple[int, int] | None:
    """Return *(start, end)* of the first balanced *open_tag*…*close_tag* span."""
    pos = src.find(open_tag, start)
    if pos == -1:
        return None
    depth = 0
    i = pos
    while i < len(src):
        if src[i : i + len(open_tag)] == open_tag:
            depth += 1
            i += len(open_tag)
        elif src[i : i + len(close_tag)] == close_tag:
            depth -= 1
            if depth == 0:
                return (pos, i + len(close_tag))
            i += len(close_tag)
        else:
            i += 1
    return None


def _split_li_items(inner: str) -> list[str]:
    """Split *inner* into top-level ``<li>…</li>`` bodies (balanced)."""
    items: list[str] = []
    i = 0
    while i < len(inner):
        span = _find_balanced_tag(inner, "<li>", "</li>", i)
        if not span:
            break
        s, e = span
        items.append(inner[s + 4 : e - 5])
        i = e
    return items


def _process_html_list(html_text: str, prefix: str, depth: int) -> list[str]:
    """Recursively convert a ``<ul>…</ul>`` or ``<ol>…</ol>`` block to Jira lines."""
    lines: list[str] = []
    bullet = prefix * (depth + 1)

    inner = re.sub(r"^<[uo]l>\s*", "", html_text)
    inner = re.sub(r"\s*</[uo]l>\s*$", "", inner)

    for item in _split_li_items(inner):
        nested_lists: list[tuple[str, str]] = []
        clean = item
        for tag, pfx in (("ul", "*"), ("ol", "#")):
            while True:
                span = _find_balanced_tag(clean, f"<{tag}>", f"</{tag}>")
                if not span:
                    break
                ns, ne = span
                nested_lists.append((clean[ns:ne], pfx))
                clean = clean[:ns] + clean[ne:]

        item_text = re.sub(r"</?p>", "", clean).strip()
        if item_text:
            lines.append(f"{bullet} {item_text}")

        for nested_html, nested_pfx in nested_lists:
            lines.extend(_process_html_list(nested_html, nested_pfx, depth + 1))

    return lines


def _convert_html_lists(text: str) -> str:
    """Convert HTML lists to Jira wiki markup lists."""
    for tag, prefix in (("ul", "*"), ("ol", "#")):
        while True:
            span = _find_balanced_tag(text, f"<{tag}>", f"</{tag}>")
            if not span:
                break
            s, e = span
            lines = _process_html_list(text[s:e], prefix, 0)
            text = text[:s] + "\n".join(lines) + text[e:]

    return text


def _normalize_nested_list_indent(text: str) -> str:
    """Normalize 2-space indented nested list items to 4-space.

    Python-Markdown requires 4-space indentation for nested lists.
    Many authors use 2-space indentation (common in GitHub-flavored
    markdown editors).  This function detects indented list markers
    whose leading whitespace is a multiple of 2 but not 4 and doubles
    them so the downstream parser recognises the nesting.
    """
    _LIST_MARKER = re.compile(r"^( +)([-*+] |\d+\. )")
    lines = text.split("\n")
    result: list[str] = []
    for line in lines:
        m = _LIST_MARKER.match(line)
        if m:
            indent = len(m.group(1))
            if indent % 4 != 0 and indent % 2 == 0:
                result.append(" " * (indent * 2) + line.lstrip())
                continue
        result.append(line)
    return "\n".join(result)


def _preprocess_markdown_blocks(text: str) -> str:
    """Ensure blank lines between block-level elements that the markdown parser
    would otherwise merge.

    Python-Markdown (with ``sane_lists``) does **not** start a new block
    element (list, heading) after a preceding paragraph / blockquote / table
    row unless there is a blank line.  Authors often omit the blank line and
    the parser silently absorbs the content into the wrong block.

    This function injects blank lines at known problem boundaries so that the
    downstream ``markdown`` library correctly recognises separate blocks.

    Handled patterns:
    - paragraph → unordered list (``- `` / ``* ``)
    - paragraph → ordered list (``1. ``)
    - bold/italic label line → any list
    - blockquote line → list
    - table row → heading (``#``)
    - table row → list
    """
    # List-start marker at BOL: - , * , + , or digit(s).
    _LIST_START = r"[-*+] |\d+\. "
    _HEADING_START = r"#{1,6} "
    # Single \n NOT preceded by \n and NOT followed by \n — i.e. the boundary
    # between two non-blank lines.  This prevents double-injection when a blank
    # line already exists.
    _SEP = r"(?<!\n)\n(?!\n)"

    # 1. Paragraph (non-blank, non-list, non-heading, non-blockquote,
    #    non-table, non-HR, non-code-fence) followed immediately by a list start.
    text = re.sub(
        rf"^([^\s\-\*\+#>|`].+){_SEP}({_LIST_START})",
        r"\1\n\n\2",
        text,
        flags=re.MULTILINE,
    )

    # 2. Bold/italic label lines (start with * or _) followed by a list/heading.
    #    Rule 1 skips these because * is excluded.  Handle explicitly.
    text = re.sub(
        rf"^([\*_]{{1,3}}[^*_\n]+[\*_]{{1,3}}:?\s*){_SEP}({_LIST_START}|{_HEADING_START})",
        r"\1\n\n\2",
        text,
        flags=re.MULTILINE,
    )

    # 3. Blockquote line followed immediately by a list start (list gets
    #    swallowed into the blockquote otherwise).
    text = re.sub(
        rf"^(>.+){_SEP}({_LIST_START})",
        r"\1\n\n\2",
        text,
        flags=re.MULTILINE,
    )

    # 4. Table row followed immediately by a heading or list (heading becomes
    #    a table cell otherwise).
    return re.sub(
        rf"^(\|.+\|)\s*{_SEP}({_HEADING_START}|{_LIST_START})",
        r"\1\n\n\2",
        text,
        flags=re.MULTILINE,
    )


def md_to_jira_markup(text: str) -> str:
    """Convert Markdown text to Jira wiki markup.

    Pipeline: Markdown → HTML (via markdown lib) → Jira wiki markup (via regex).
    """
    if not text or not text.strip():
        return text

    text = _normalize_nested_list_indent(text)
    text = _preprocess_markdown_blocks(text)

    md = _get_markdown()
    html_content = md.markdown(
        text,
        extensions=["tables", "fenced_code", "sane_lists"],
    )
    return _html_to_jira(html_content)


# ===================================================================
# Jira Wiki Markup → Markdown
# ===================================================================


def _jira_code_block_to_md(m: re.Match[str]) -> str:
    """Convert a ``{code:params}...{code}`` match to a Markdown fenced block."""
    params = m.group(1) or ""
    body = (m.group(2) or "").strip("\n")
    lang = ""
    if params:
        for part in params.split("|"):
            if "=" in part:
                k, v = part.split("=", 1)
                if k.strip().lower() == "language":
                    lang = v.strip()
            else:
                lang = part.strip()
    return f"```{lang}\n{body}\n```"


def jira_markup_to_md(text: str) -> str:
    """Convert Jira wiki markup to Markdown.

    Uses direct regex translation for common Jira patterns.
    """
    if not text or not text.strip():
        return text

    # --- Code blocks ---
    text = re.sub(
        r"\{code:([^}]+)\}\s*\n?(.*?)\n?\{code\}",
        _jira_code_block_to_md,
        text,
        flags=re.DOTALL,
    )
    text = re.sub(
        r"\{code\}\s*\n?(.*?)\n?\{code\}",
        lambda m: f"```\n{(m.group(1) or '').strip(chr(10))}\n```",
        text,
        flags=re.DOTALL,
    )

    # --- Inline code ---
    text = re.sub(r"\{\{(.*?)\}\}", r"`\1`", text)

    # --- Headings (h1. through h6.) ---
    for level in range(6, 0, -1):
        hashes = "#" * level
        text = re.sub(
            rf"^h{level}\.\s+(.*)$",
            rf"{hashes} \1",
            text,
            flags=re.MULTILINE,
        )

    # --- Bold (*text*) ---
    # Must not match list bullets (* item) — require non-space after opening *
    text = re.sub(r"(?<!\w)\*(\S[^*\n]*)\*(?!\w)", r"**\1**", text)

    # --- Italic (_text_) ---
    text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"*\1*", text)

    # --- Strikethrough (-text-) ---
    text = re.sub(r"(?<!\w)-([^-\n]+)-(?!\w)", r"~~\1~~", text)

    # --- Links [text|url] ---
    text = re.sub(r"\[([^|\]]+)\|([^\]]+)\]", r"[\1](\2)", text)
    # Simple links [url]
    text = re.sub(r"\[([^\]|]+)\](?!\()", r"[\1](\1)", text)

    # --- Images !url! ---
    text = re.sub(r"!([^!\s]+)!", r"![](\1)", text)

    # --- Tables ---
    text = _jira_tables_to_md(text)

    # --- Lists ---
    text = _jira_lists_to_md(text)

    # --- Blockquotes ---
    text = re.sub(
        r"\{quote\}\s*\n?(.*?)\n?\{quote\}",
        lambda m: "\n".join("> " + line for line in m.group(1).splitlines()),
        text,
        flags=re.DOTALL,
    )

    # --- Horizontal rules ---
    text = re.sub(r"^----\s*$", "---", text, flags=re.MULTILINE)

    # --- Panels ---
    text = re.sub(
        r"\{panel(?::title=([^}]*))?\}(.*?)\{panel\}",
        lambda m: (f"**{m.group(1)}**\n" if m.group(1) else "") + m.group(2).strip(),
        text,
        flags=re.DOTALL,
    )

    # --- Noformat ---
    text = re.sub(
        r"\{noformat\}(.*?)\{noformat\}",
        r"```\n\1\n```",
        text,
        flags=re.DOTALL,
    )

    # --- Color (strip, keep text) ---
    text = re.sub(r"\{color:[^}]+\}(.*?)\{color\}", r"\1", text, flags=re.DOTALL)

    # Clean up
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _jira_tables_to_md(text: str) -> str:
    """Convert Jira wiki tables to Markdown tables."""
    lines = text.splitlines()
    result = []
    in_table = False
    header_done = False

    for line in lines:
        stripped = line.strip()

        # Header row: || col1 || col2 ||
        if stripped.startswith("||") and stripped.endswith("||"):
            cells = [c.strip() for c in stripped.split("||") if c.strip()]
            result.append("| " + " | ".join(cells) + " |")
            result.append("| " + " | ".join("---" for _ in cells) + " |")
            in_table = True
            header_done = True
            continue

        # Data row: | col1 | col2 |
        if stripped.startswith("|") and stripped.endswith("|") and not stripped.startswith("||"):
            cells = [c.strip() for c in stripped.split("|") if c.strip()]
            if not header_done and not in_table:
                # First row is header
                result.append("| " + " | ".join(cells) + " |")
                result.append("| " + " | ".join("---" for _ in cells) + " |")
                in_table = True
                header_done = True
            else:
                result.append("| " + " | ".join(cells) + " |")
                in_table = True
            continue

        if in_table:
            in_table = False
            header_done = False

        result.append(line)

    return "\n".join(result)


def _jira_lists_to_md(text: str) -> str:
    """Convert Jira wiki list markers to Markdown list markers.

    Handles both unordered (* markers) and ordered (# markers) lists,
    including nested lists (**, ##, *#, #* etc).
    """
    lines = text.splitlines()
    result = []

    for line in lines:
        stripped = line.strip()

        # Mixed or pure list markers: sequences of * and # followed by space
        list_match = re.match(r"^([*#]{1,6})\s+(.*)$", stripped)
        if list_match:
            markers = list_match.group(1)
            content = list_match.group(2)
            depth = len(markers) - 1
            indent = "  " * depth
            # Last marker determines list type
            bullet = "1." if markers[-1] == "#" else "-"
            result.append(f"{indent}{bullet} {content}")
            continue

        result.append(line)

    return "\n".join(result)


# ===================================================================
# Mermaid diagram rendering (```mermaid blocks → PNG)
# ===================================================================

MERMAID_BLOCK_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)


def _find_mmdc() -> str | None:
    """Locate the mmdc binary (Mermaid CLI) or fall back to npx."""
    mmdc = shutil.which("mmdc")
    if mmdc:
        return mmdc
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


def _render_to_png(mmd_file: Path, png_file: Path, mmdc_path: str) -> bool:
    """Render a .mmd file to PNG. Returns True on success."""
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
            str(png_file),
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
            str(png_file),
            "-b",
            "transparent",
            "--scale",
            "2",
        ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return result.returncode == 0 and png_file.exists()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def render_mermaid_blocks(
    md_text: str, output_dir: str | Path | None = None
) -> tuple[str, list[str]]:
    """Render ````` mermaid`` code blocks in *md_text* to PNG images.

    Each block is replaced with a markdown image reference pointing to the
    rendered PNG (absolute path), which the downstream ``extract_local_images``
    pipeline will pick up and rewrite to a basename for Jira attachment syntax.

    Returns ``(modified_markdown, list_of_png_absolute_paths)``.

    Requires ``mmdc`` (Mermaid CLI) or ``npx``.  If neither is available the
    blocks are left untouched and a warning is printed.
    """
    blocks = list(MERMAID_BLOCK_RE.finditer(md_text))
    if not blocks:
        return md_text, []

    mmdc = _find_mmdc()
    if not mmdc:
        print(
            "WARNING: mmdc not found — mermaid blocks left as code. "
            "Install via: npm i -g @mermaid-js/mermaid-cli",
            file=sys.stderr,
        )
        return md_text, []

    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="jira-mermaid-"))
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    png_paths: list[str] = []
    counter = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal counter
        counter += 1
        mmd_src = match.group(1)
        mmd_file = output_dir / f"mermaid-diagram-{counter}.mmd"
        png_file = output_dir / f"mermaid-diagram-{counter}.png"

        mmd_file.write_text(mmd_src, encoding="utf-8")

        if _render_to_png(mmd_file, png_file, mmdc):
            png_paths.append(str(png_file))
            return f"![Mermaid Diagram {counter}]({png_file})"

        print(
            f"WARNING: Failed to render mermaid diagram {counter}",
            file=sys.stderr,
        )
        return match.group(0)

    modified = MERMAID_BLOCK_RE.sub(_replace, md_text)

    rendered = len(png_paths)
    total = len(blocks)
    if rendered > 0:
        print(f"  Rendered {rendered}/{total} mermaid diagram(s) to PNG")
    return modified, png_paths


# ===================================================================
# Local image extraction (for auto-attachment support)
# ===================================================================

_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_URL_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)


def extract_local_images(md_text: str, base_dir: str | Path = ".") -> tuple[str, list[str]]:
    """Extract local image references from markdown and rewrite paths to basenames.

    Finds ``![alt](path)`` where *path* is a local file (not ``http://`` / ``https://``).
    Resolves each path relative to *base_dir* and rewrites the markdown reference
    to use just the filename so Jira wiki markup ``!filename.png!`` matches the
    attachment uploaded alongside the description.

    Returns ``(rewritten_markdown, resolved_file_paths)``.
    Missing files are warned about but still included in the list — the caller
    can filter or let ``upload_attachments`` handle the error.
    """
    base = Path(base_dir)
    found_paths: list[str] = []
    seen_basenames: dict[str, int] = {}

    def _rewrite(match: re.Match[str]) -> str:
        alt = match.group(1)
        raw_path = match.group(2).strip()

        if _URL_SCHEME_RE.match(raw_path):
            return match.group(0)

        resolved = (base / raw_path).resolve()

        if not resolved.exists() and base != Path.cwd().resolve():
            cwd_resolved = (Path.cwd() / raw_path).resolve()
            if cwd_resolved.exists():
                resolved = cwd_resolved

        if not resolved.exists():
            print(
                f"WARNING: Image not found: {raw_path} (resolved to {resolved})",
                file=sys.stderr,
            )

        basename = resolved.name

        # Handle duplicate basenames by de-duplicating in the path list
        if basename in seen_basenames:
            count = seen_basenames[basename] + 1
            seen_basenames[basename] = count
            stem = resolved.stem
            suffix = resolved.suffix
            basename = f"{stem}_{count}{suffix}"
        else:
            seen_basenames[basename] = 0

        found_paths.append(str(resolved))
        return f"![{alt}]({basename})"

    rewritten = _MD_IMAGE_RE.sub(_rewrite, md_text)
    return rewritten, found_paths


# ===================================================================
# CLI interface
# ===================================================================


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convert between Markdown and Jira wiki markup")
    parser.add_argument(
        "--direction",
        choices=["md2jira", "jira2md"],
        required=True,
        help="Conversion direction",
    )
    parser.add_argument("--text", help="Text to convert")
    parser.add_argument("--file", help="File to read text from")
    args = parser.parse_args()

    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        text = sys.stdin.read()

    if args.direction == "md2jira":
        print(md_to_jira_markup(text))
    else:
        print(jira_markup_to_md(text))
