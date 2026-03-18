#!/usr/bin/env python3
"""
Codebase Analyzer — JSON Formatter

Renders analysis results as structured JSON to stdout.
All metric computation is delegated to analyze.py shared helpers.
"""

import json
import sys
from collections.abc import Callable
from pathlib import Path

from analyze import (
    AnalysisResult,
    compute_file_distribution,
    compute_language_breakdown,
    compute_large_files,
    compute_summary,
    compute_todo_files,
)


def _build_categories(result: AnalysisResult) -> dict:
    """Build category breakdown as a dict."""
    cats = result.categories
    out = {}
    for cat_name in ["code", "tests", "test_data", "docs", "plans", "scripts"]:
        cat = cats.get(cat_name)
        if cat and cat.files:
            code_lines = cat.code_lines
            out[cat_name] = {
                "files": len(cat.files),
                "total_lines": cat.total_lines,
                "code_lines": code_lines,
                "comment_lines": cat.comment_lines,
                "blank_lines": cat.blank_lines,
                "comment_pct": round(
                    (cat.comment_lines / code_lines * 100) if code_lines else 0, 1
                ),
                "todos": cat.todo_count,
                "fixmes": cat.fixme_count,
            }
    return out


# Section name → builder mapping
_BUILDERS: dict[str, Callable[[AnalysisResult], object]] = {
    "summary": lambda r: compute_summary(r),
    "categories": lambda r: _build_categories(r),
    "languages": lambda r: compute_language_breakdown(r),
    "file-distribution": lambda r: compute_file_distribution(r),
    "large-files": lambda r: compute_large_files(r),
    "todos": lambda r: compute_todo_files(r),
    "churn": lambda r: [{"file": Path(f).name, "changes": c} for f, c in r.most_changed],
}


def render_json(result: AnalysisResult, sections: list[str]) -> None:
    """Render the analysis as JSON to stdout."""
    output: dict = {"repo": str(result.repo_root)}

    for section in sections:
        builder = _BUILDERS.get(section)
        if builder:
            output[section.replace("-", "_")] = builder(result)

    json.dump(output, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
