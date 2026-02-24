#!/usr/bin/env python3
"""
Codebase Analyzer — Rich Terminal Formatter

Renders analysis results as rich, colored terminal output using the Rich library.
All metric computation is delegated to analyze.py shared helpers.
"""

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from analyze import (
    AnalysisResult,
    compute_file_distribution,
    compute_language_breakdown,
    compute_large_files,
    compute_summary,
    compute_todo_files,
)

HEADER_STYLE = "bold cyan"


def _ratio_style(ratio: float) -> str:
    """Return a Rich style string for a test:code ratio value."""
    if ratio >= 0.8:
        return "green"
    if ratio >= 0.5:
        return "yellow"
    return "red"


def _render_summary(result: AnalysisResult, console: Console) -> None:
    """Print the top-level summary panel."""
    s = compute_summary(result)

    text = Text()
    text.append("Files: ", style="bold")
    text.append(f"{s['total_files']:,}\n")
    text.append("Total Lines: ", style="bold")
    text.append(f"{s['total_lines']:,}\n")
    text.append("Code Lines: ", style="bold green")
    text.append(f"{s['total_code']:,}\n", style="green")
    text.append("Comments: ", style="bold yellow")
    text.append(f"{s['total_comments']:,}\n", style="yellow")
    text.append("TODOs: ", style="bold cyan")
    text.append(f"{s['total_todos']:,}  ")
    text.append("FIXMEs: ", style="bold red")
    text.append(f"{s['total_fixmes']:,}\n", style="red")

    if s["test_code_ratio"] is not None:
        ratio = s["test_code_ratio"]
        text.append("Test:Code Ratio: ", style="bold")
        text.append(f"{ratio:.2f}\n", style=_ratio_style(ratio))

    console.print(Panel(text, title=f"[{HEADER_STYLE}]Codebase Summary[/]", border_style="cyan"))


def _render_categories(result: AnalysisResult, console: Console) -> None:
    """Print the category breakdown table."""
    cats = result.categories

    code_stats = cats.get("code")
    test_stats = cats.get("tests")

    if code_stats and test_stats and code_stats.files and test_stats.files:
        table = Table(title="Code vs Tests Comparison", show_header=True, header_style=HEADER_STYLE)
        table.add_column("Metric", style="dim")
        table.add_column("Code", justify="right")
        table.add_column("Tests", justify="right")

        table.add_row("Files", f"{len(code_stats.files):,}", f"{len(test_stats.files):,}")
        table.add_row("Total Lines", f"{code_stats.total_lines:,}", f"{test_stats.total_lines:,}")
        table.add_row(
            "[green]Pure Code[/]",
            f"[green]{code_stats.code_lines:,}[/]",
            f"[green]{test_stats.code_lines:,}[/]",
        )
        table.add_row("Comments", f"{code_stats.comment_lines:,}", f"{test_stats.comment_lines:,}")
        table.add_row("Blank Lines", f"{code_stats.blank_lines:,}", f"{test_stats.blank_lines:,}")

        code_pct = (
            (code_stats.comment_lines / code_stats.code_lines * 100) if code_stats.code_lines else 0
        )
        test_pct = (
            (test_stats.comment_lines / test_stats.code_lines * 100) if test_stats.code_lines else 0
        )
        table.add_row("Comment %", f"{code_pct:.1f}%", f"{test_pct:.1f}%")
        console.print(table)

    table = Table(title="All Categories", show_header=True, header_style=HEADER_STYLE)
    table.add_column("Category", style="bold")
    table.add_column("Files", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Code", justify="right", style="green")
    table.add_column("Comments", justify="right")
    table.add_column("TODOs", justify="right", style="cyan")

    for cat_name in ["code", "tests", "docs", "plans", "scripts"]:
        cat = cats.get(cat_name)
        if cat and cat.files:
            table.add_row(
                cat_name.capitalize(),
                f"{len(cat.files):,}",
                f"{cat.total_lines:,}",
                f"{cat.code_lines:,}",
                f"{cat.comment_lines:,}",
                f"{cat.todo_count:,}",
            )

    test_data = cats.get("test_data")
    if test_data and test_data.files:
        table.add_row(
            "[dim]Test Data[/]",
            f"[dim]{len(test_data.files):,}[/]",
            f"[dim]{test_data.total_lines:,}[/]",
            f"[dim]{test_data.code_lines:,}[/]",
            "[dim]-[/]",
            "[dim]-[/]",
        )

    console.print(table)


def _render_languages(result: AnalysisResult, console: Console) -> None:
    """Print the language breakdown table."""
    for label, category in [("All", None), ("Code Only", "code")]:
        breakdown = compute_language_breakdown(result, category)
        if not breakdown:
            continue

        table = Table(
            title=f"Language Breakdown ({label})", show_header=True, header_style=HEADER_STYLE
        )
        table.add_column("Language", style="bold")
        table.add_column("Files", justify="right")
        table.add_column("Code Lines", justify="right", style="green")
        table.add_column("Comments", justify="right")

        for entry in breakdown[:12]:
            table.add_row(
                entry["language"],
                f"{entry['files']:,}",
                f"{entry['code']:,}",
                f"{entry['comments']:,}",
            )

        console.print(table)


def _render_file_distribution(result: AnalysisResult, console: Console) -> None:
    """Print file-size distribution."""
    buckets = compute_file_distribution(result)
    total = sum(buckets.values()) or 1
    max_count = max(buckets.values()) or 1

    table = Table(title="File Size Distribution", show_header=True, header_style=HEADER_STYLE)
    table.add_column("Size (lines)", style="bold")
    table.add_column("Count", justify="right")
    table.add_column("Percent", justify="right")
    table.add_column("Distribution")

    for bucket, count in buckets.items():
        pct = count / total * 100
        bar_width = int((count / max_count) * 20)
        bar = "\u2588" * bar_width + "\u2591" * (20 - bar_width)
        table.add_row(bucket, f"{count:,}", f"{pct:.1f}%", f"[green]{bar}[/]")

    console.print(table)


def _render_large_files(result: AnalysisResult, console: Console) -> None:
    """Print large code files."""
    large = compute_large_files(result)
    threshold = result.config.get("large_file_threshold", 500)

    table = Table(
        title=f"Large Code Files (>{threshold} lines)",
        show_header=True,
        header_style="bold yellow",
    )
    table.add_column("Language", style="cyan")
    table.add_column("Lines", justify="right", style="yellow")
    table.add_column("File", style="dim")

    if not large:
        table.add_row("-", "[green]None[/]", f"[green]All files under {threshold} lines[/]")
    else:
        for entry in large[:10]:
            table.add_row(entry["language"], f"{entry['lines']:,}", entry["file"])

    console.print(table)


def _render_todos(result: AnalysisResult, console: Console) -> None:
    """Print files with TODOs/FIXMEs."""
    todo_files = compute_todo_files(result)
    
    table = Table(title="Files with TODOs/FIXMEs", show_header=True, header_style=HEADER_STYLE)
    table.add_column("File", style="dim")
    table.add_column("TODOs", justify="right", style="cyan")
    table.add_column("FIXMEs", justify="right", style="red")

    if not todo_files:
        table.add_row("-", "[green]0[/]", "[green]0[/]")
        console.print(table)
        return

    for entry in todo_files:
        table.add_row(entry["file"], str(entry["todos"]), str(entry["fixmes"]))

    console.print(table)


def _render_churn(result: AnalysisResult, console: Console) -> None:
    """Print most frequently changed files."""
    table = Table(
        title="Most Changed Files (recent 500 commits)",
        show_header=True,
        header_style=HEADER_STYLE,
    )
    table.add_column("File", style="dim")
    table.add_column("Changes", justify="right", style="yellow")

    if not result.most_changed:
        table.add_row("-", "[dim]No data[/]")
        console.print(table)
        return

    for file_path, count in result.most_changed:
        table.add_row(Path(file_path).name, str(count))

    console.print(table)


# Section name → renderer mapping
_RENDERERS = {
    "summary": _render_summary,
    "categories": _render_categories,
    "languages": _render_languages,
    "file-distribution": _render_file_distribution,
    "large-files": _render_large_files,
    "todos": _render_todos,
    "churn": _render_churn,
}


def render_terminal(result: AnalysisResult, sections: list[str]) -> None:
    """Render the analysis to the terminal using Rich."""
    console = Console()

    console.print(Panel(f"[bold]Analyzing:[/] {result.repo_root}", style="cyan"))
    console.print()

    for section in sections:
        renderer = _RENDERERS.get(section)
        if renderer:
            renderer(result, console)
            console.print()

    console.print(
        Panel(
            f"[green]Analysis complete in {result.analysis_time:.2f}s[/]",
            style="green",
        )
    )
