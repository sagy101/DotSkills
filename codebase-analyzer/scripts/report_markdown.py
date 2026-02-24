#!/usr/bin/env python3
"""
Codebase Analyzer — Markdown Formatter

Renders analysis results as Markdown to stdout.
Suitable for embedding in PRs, docs, or publishing to wikis.
All metric computation is delegated to analyze.py shared helpers.
"""

import sys
from pathlib import Path

from analyze import (
    AnalysisResult,
    compute_file_distribution,
    compute_language_breakdown,
    compute_large_files,
    compute_summary,
    compute_todo_files,
)


def _write(text: str) -> None:
    sys.stdout.write(text)


def _ratio_quality(ratio: float) -> str:
    """Return a human-readable quality label for a test:code ratio."""
    if ratio >= 0.8:
        return "Good"
    if ratio >= 0.5:
        return "Fair"
    return "Low"


def _render_summary(result: AnalysisResult) -> None:
    s = compute_summary(result)

    _write("## Summary\n\n")
    _write("| Metric | Value |\n|---|---|\n")
    _write(f"| Files | {s['total_files']:,} |\n")
    _write(f"| Total Lines | {s['total_lines']:,} |\n")
    _write(f"| Code Lines | {s['total_code']:,} |\n")
    _write(f"| Comments | {s['total_comments']:,} |\n")
    _write(f"| Blank Lines | {s['total_blank']:,} |\n")
    _write(f"| TODOs | {s['total_todos']:,} |\n")
    _write(f"| FIXMEs | {s['total_fixmes']:,} |\n")
    _write(f"| Comment % | {s['comment_pct']:.1f}% |\n")

    if s["test_code_ratio"] is not None:
        ratio = s["test_code_ratio"]
        _write(f"| Test:Code Ratio | {ratio:.2f} ({_ratio_quality(ratio)}) |\n")

    _write(f"| Analysis Time | {s['analysis_time']:.2f}s |\n")
    _write("\n")


def _render_categories(result: AnalysisResult) -> None:
    cats = result.categories

    code_stats = cats.get("code")
    test_stats = cats.get("tests")

    if code_stats and test_stats and code_stats.files and test_stats.files:
        _write("## Code vs Tests\n\n")
        _write("| Metric | Code | Tests |\n|---|---|---|\n")
        _write(f"| Files | {len(code_stats.files):,} | {len(test_stats.files):,} |\n")
        _write(f"| Total Lines | {code_stats.total_lines:,} | {test_stats.total_lines:,} |\n")
        _write(f"| Code Lines | {code_stats.code_lines:,} | {test_stats.code_lines:,} |\n")
        _write(f"| Comments | {code_stats.comment_lines:,} | {test_stats.comment_lines:,} |\n")
        _write(f"| Blank Lines | {code_stats.blank_lines:,} | {test_stats.blank_lines:,} |\n")
        _write("\n")

    _write("## Categories\n\n")
    _write("| Category | Files | Total | Code | Comments | TODOs |\n")
    _write("|---|---|---|---|---|---|\n")

    for cat_name in ["code", "tests", "test_data", "docs", "plans", "scripts"]:
        cat = cats.get(cat_name)
        if cat and cat.files:
            _write(
                f"| {cat_name.capitalize()} | {len(cat.files):,} | {cat.total_lines:,} "
                f"| {cat.code_lines:,} | {cat.comment_lines:,} | {cat.todo_count:,} |\n"
            )

    _write("\n")


def _render_languages(result: AnalysisResult) -> None:
    _write("## Language Breakdown\n\n")
    _write("| Language | Files | Code Lines | Comments |\n|---|---|---|---|\n")

    for entry in compute_language_breakdown(result)[:12]:
        _write(
            f"| {entry['language']} | {entry['files']:,} "
            f"| {entry['code']:,} | {entry['comments']:,} |\n"
        )

    _write("\n")


def _render_file_distribution(result: AnalysisResult) -> None:
    buckets = compute_file_distribution(result)
    total = sum(buckets.values()) or 1

    _write("## File Size Distribution\n\n")
    _write("| Size (lines) | Count | Percent |\n|---|---|---|\n")

    for bucket, count in buckets.items():
        pct = count / total * 100
        _write(f"| {bucket} | {count:,} | {pct:.1f}% |\n")

    _write("\n")


def _render_large_files(result: AnalysisResult) -> None:
    large = compute_large_files(result)
    threshold = result.config.get("large_file_threshold", 500)

    _write(f"## Large Files (>{threshold} lines)\n\n")

    if not large:
        _write(f"All code files are under {threshold} lines.\n\n")
        return

    _write("| File | Lines | Language |\n|---|---|---|\n")
    for entry in large[:10]:
        _write(f"| {entry['file']} | {entry['lines']:,} | {entry['language']} |\n")
    _write("\n")


def _render_todos(result: AnalysisResult) -> None:
    todo_files = compute_todo_files(result)

    if not todo_files:
        _write("## TODOs / FIXMEs\n\nNo TODOs or FIXMEs found.\n\n")
        return

    _write("## TODOs / FIXMEs\n\n")
    _write("| File | TODOs | FIXMEs |\n|---|---|---|\n")
    for entry in todo_files:
        _write(f"| {entry['file']} | {entry['todos']} | {entry['fixmes']} |\n")
    _write("\n")


def _render_churn(result: AnalysisResult) -> None:
    if not result.most_changed:
        # Only show if requested; if list is empty but section requested, say so?
        # Actually, result.most_changed is only populated if "churn" was requested.
        # If it's empty, it might mean no git repo or no changes.
        # We can't easily distinguish "not requested" from "no results" here easily 
        # without passing sections, but render_markdown iterates sections.
        # So if we are here, it was requested.
        _write("## Most Changed Files\n\nNo churn data available (git not found or no history).\n\n")
        return

    _write("## Most Changed Files\n\n")
    _write("| File | Changes |\n|---|---|\n")
    for file_path, count in result.most_changed:
        _write(f"| {Path(file_path).name} | {count} |\n")
    _write("\n")


_RENDERERS = {
    "summary": _render_summary,
    "categories": _render_categories,
    "languages": _render_languages,
    "file-distribution": _render_file_distribution,
    "large-files": _render_large_files,
    "todos": _render_todos,
    "churn": _render_churn,
}


def render_markdown(result: AnalysisResult, sections: list[str]) -> None:
    """Render the analysis as Markdown to stdout."""
    _write(f"# Codebase Analysis: {result.repo_root.name}\n\n")

    for section in sections:
        renderer = _RENDERERS.get(section)
        if renderer:
            renderer(result)

    _write(f"---\n*Analysis completed in {result.analysis_time:.2f}s*\n")
