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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# ---------------------------------------------------------------------------
# Lazy dependency loading
# ---------------------------------------------------------------------------

_markdown_lib = None
_markdownify = None


def _get_markdown():
    global _markdown_lib
    if _markdown_lib is None:
        try:
            import markdown
            _markdown_lib = markdown
        except ImportError:
            print(
                "ERROR: 'markdown' package not installed. "
                "Run: python3 <skill_dir>/scripts/setup_env.py",
                file=sys.stderr,
            )
            sys.exit(1)
    return _markdown_lib


def _get_markdownify():
    global _markdownify
    if _markdownify is None:
        try:
            from markdownify import markdownify as md_convert
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
        lambda m: "{code:" + m.group(1) + "}\n" + html_lib.unescape(m.group(2)).strip() + "\n{code}",
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
    text = re.sub(r'<a href="([^"]+)">(.*?)</a>', r"[\2|\1]", text)

    # --- Images ---
    text = re.sub(r'<img[^>]+src="([^"]+)"[^>]*alt="([^"]*)"[^>]*/?>',
                  r"!\1!", text)
    text = re.sub(r'<img[^>]+src="([^"]+)"[^>]*/?>',
                  r"!\1!", text)

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
    text = re.sub(r"<p>(.*?)</p>", r"\1\n", text, flags=re.DOTALL)

    # --- Line breaks ---
    text = re.sub(r"<br\s*/?>", "\n", text)

    # --- Strip remaining HTML tags ---
    text = re.sub(r"</?[^>]+>", "", text)

    # --- Unescape HTML entities ---
    text = html_lib.unescape(text)

    # --- Clean up excessive blank lines ---
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _convert_html_tables(text: str) -> str:
    """Convert HTML tables to Jira wiki markup tables."""

    def _table_to_jira(match):
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


def _convert_html_lists(text: str) -> str:
    """Convert HTML lists to Jira wiki markup lists."""

    def _process_list(html_text, prefix="*", depth=0):
        """Recursively process list items."""
        lines = []
        bullet = prefix * (depth + 1)

        # Find all list items at this level
        items = re.findall(r"<li>(.*?)</li>", html_text, re.DOTALL)
        for item in items:
            # Check for nested lists
            nested_ul = re.search(r"<ul>(.*?)</ul>", item, re.DOTALL)
            nested_ol = re.search(r"<ol>(.*?)</ol>", item, re.DOTALL)

            # Get text content (everything before nested list)
            item_text = re.sub(r"<[uo]l>.*?</[uo]l>", "", item, flags=re.DOTALL).strip()
            if item_text:
                lines.append(f"{bullet} {item_text}")

            if nested_ul:
                lines.extend(
                    _process_list(nested_ul.group(0), "*", depth + 1)
                )
            if nested_ol:
                lines.extend(
                    _process_list(nested_ol.group(0), "#", depth + 1)
                )

        return lines

    # Process unordered lists (outermost first)
    def _replace_ul(match):
        lines = _process_list(match.group(0), "*", 0)
        return "\n".join(lines)

    def _replace_ol(match):
        lines = _process_list(match.group(0), "#", 0)
        return "\n".join(lines)

    # Process outermost lists only (nested are handled recursively)
    # We need to be careful to only match top-level lists
    # Simple approach: process all <ul>...</ul> and <ol>...</ol>
    text = re.sub(r"<ul>(.*?)</ul>", _replace_ul, text, flags=re.DOTALL)
    text = re.sub(r"<ol>(.*?)</ol>", _replace_ol, text, flags=re.DOTALL)

    return text


def md_to_jira_markup(text: str) -> str:
    """Convert Markdown text to Jira wiki markup.

    Pipeline: Markdown → HTML (via markdown lib) → Jira wiki markup (via regex).
    """
    if not text or not text.strip():
        return text

    md = _get_markdown()
    html_content = md.markdown(
        text,
        extensions=["tables", "fenced_code", "sane_lists"],
    )
    return _html_to_jira(html_content)


# ===================================================================
# Jira Wiki Markup → Markdown
# ===================================================================


def jira_markup_to_md(text: str) -> str:
    """Convert Jira wiki markup to Markdown.

    Uses direct regex translation for common Jira patterns.
    """
    if not text or not text.strip():
        return text

    # --- Code blocks ---
    text = re.sub(
        r"\{code:(\w+)\}\s*\n(.*?)\n\{code\}",
        r"```\1\n\2\n```",
        text,
        flags=re.DOTALL,
    )
    text = re.sub(
        r"\{code\}\s*\n(.*?)\n\{code\}",
        r"```\n\1\n```",
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
# CLI interface
# ===================================================================


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert between Markdown and Jira wiki markup"
    )
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
