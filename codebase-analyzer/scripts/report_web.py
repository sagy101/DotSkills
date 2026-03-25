#!/usr/bin/env python3
"""
Codebase Analyzer — Streamlit Web Dashboard

Provides an interactive web-based visualization of codebase analysis results.

Usage (via analyze.py):
    python analyze.py --path /repo --output web

Direct usage:
    streamlit run report_web.py -- --path /repo
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import streamlit as st
from analyze import (
    CategoryStats,
    analyze_file,
    categorize_file,
    get_tracked_files,
    load_config,
    should_skip,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments passed after '--' in streamlit run."""
    parser = argparse.ArgumentParser(description="Codebase Analyzer Web Dashboard")
    parser.add_argument(
        "--path",
        default=".",
        help="Path to the repository root (default: current directory)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to .codebase-analysis.yaml (default: auto-detect in repo root)",
    )
    return parser.parse_args()


@st.cache_data(ttl=60)
def analyze_codebase(
    repo_root_str: str, config_path_str: str | None = None
) -> dict[str, CategoryStats]:
    """Run analysis and cache results for 60 seconds."""
    repo_root = Path(repo_root_str)
    config_path = Path(config_path_str) if config_path_str else None
    config = load_config(repo_root, config_path)
    categories: dict[str, CategoryStats] = {
        "code": CategoryStats(),
        "tests": CategoryStats(),
        "test_data": CategoryStats(),
        "docs": CategoryStats(),
        "plans": CategoryStats(),
        "scripts": CategoryStats(),
    }
    tracked_files = get_tracked_files(repo_root)
    for file_path in sorted(tracked_files):
        if not file_path.is_file():
            continue
        if should_skip(file_path, repo_root, config):
            continue
        category = categorize_file(file_path, repo_root, config)
        file_stats = analyze_file(file_path)
        categories[category].add_file(file_stats)
    return categories


def render_overview(categories: dict[str, CategoryStats]) -> None:
    """Render the overview metrics row."""
    main_cats = {k: v for k, v in categories.items() if k not in ("test_data", "plans")}
    code_stats = categories.get("code")
    test_stats = categories.get("tests")
    docs_stats = categories.get("docs")

    total_files = sum(len(cat.files) for cat in main_cats.values())
    total_lines = sum(cat.total_lines for cat in main_cats.values())
    total_comments = sum(cat.comment_lines for cat in main_cats.values())

    st.markdown("### Overview")
    cols = st.columns(7)

    cols[0].metric("Files", f"{total_files:,}")
    cols[1].metric("Total Lines", f"{total_lines:,}")
    cols[2].metric("Pure Code", f"{code_stats.code_lines:,}" if code_stats else "0")
    cols[3].metric("Comments", f"{total_comments:,}")

    code_comment_pct = (
        (code_stats.comment_lines / code_stats.code_lines * 100)
        if code_stats and code_stats.code_lines
        else 0
    )
    cols[4].metric("Comment %", f"{code_comment_pct:.1f}%")

    if code_stats and test_stats and code_stats.code_lines:
        ratio = test_stats.code_lines / code_stats.code_lines
        ratio_str = f"1:{ratio:.1f}" if ratio >= 1 else f"{1 / ratio:.1f}:1"
        delta_color = "normal" if ratio >= 0.8 else "off"
        cols[5].metric(
            "Test:Code",
            ratio_str,
            delta="Good" if ratio >= 0.8 else "Low",
            delta_color=delta_color,
        )

    if code_stats and docs_stats and code_stats.code_lines and docs_stats.code_lines:
        docs_ratio = code_stats.code_lines / docs_stats.code_lines
        docs_ratio_str = f"1:{docs_ratio:.0f}"
        docs_good = 3 <= docs_ratio <= 15
        delta_text = "Good" if docs_good else ("Low docs" if docs_ratio > 15 else "Heavy docs")
        cols[6].metric(
            "Docs:Code",
            docs_ratio_str,
            delta=delta_text,
            delta_color="normal" if docs_good else "off",
        )


def render_code_vs_tests(categories: dict[str, CategoryStats]) -> None:
    """Render Code vs Tests comparison section."""
    code_stats = categories.get("code")
    test_stats = categories.get("tests")

    st.markdown("### Code vs Tests Comparison")

    if not (code_stats and test_stats):
        st.info("No code or test files found.")
        return

    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        code_comment_pct = (
            (code_stats.comment_lines / code_stats.code_lines * 100) if code_stats.code_lines else 0
        )
        test_comment_pct = (
            (test_stats.comment_lines / test_stats.code_lines * 100) if test_stats.code_lines else 0
        )

        df = pd.DataFrame(
            {
                "Metric": [
                    "Files",
                    "Total Lines",
                    "Pure Code Lines",
                    "Comment Lines",
                    "Blank Lines",
                    "Comment %",
                ],
                "Code": [
                    f"{len(code_stats.files):,}",
                    f"{code_stats.total_lines:,}",
                    f"{code_stats.code_lines:,}",
                    f"{code_stats.comment_lines:,}",
                    f"{code_stats.blank_lines:,}",
                    f"{code_comment_pct:.1f}%",
                ],
                "Tests": [
                    f"{len(test_stats.files):,}",
                    f"{test_stats.total_lines:,}",
                    f"{test_stats.code_lines:,}",
                    f"{test_stats.comment_lines:,}",
                    f"{test_stats.blank_lines:,}",
                    f"{test_comment_pct:.1f}%",
                ],
            }
        )
        st.dataframe(df, use_container_width=True, hide_index=True)

    with col2:
        chart_data = pd.DataFrame(
            {
                "Metric": ["Pure Code", "Comments", "Blanks"],
                "Code": [
                    code_stats.code_lines,
                    code_stats.comment_lines,
                    code_stats.blank_lines,
                ],
                "Tests": [
                    test_stats.code_lines,
                    test_stats.comment_lines,
                    test_stats.blank_lines,
                ],
            }
        )
        st.bar_chart(chart_data.set_index("Metric"))

    with col3:
        ratio = test_stats.code_lines / code_stats.code_lines if code_stats.code_lines else 0
        ratio_str = f"1:{ratio:.1f}" if ratio >= 1 else f"{1 / ratio:.1f}:1"
        code_comment_pct = (
            (code_stats.comment_lines / code_stats.code_lines * 100) if code_stats.code_lines else 0
        )
        test_comment_pct = (
            (test_stats.comment_lines / test_stats.code_lines * 100) if test_stats.code_lines else 0
        )
        st.markdown(f"""
**Key Ratios**

| Metric | Value |
|--------|-------|
| Test:Code | **{ratio_str}** |
| Code Comment % | {code_comment_pct:.1f}% |
| Test Comment % | {test_comment_pct:.1f}% |
""")


def render_language_breakdown(categories: dict[str, CategoryStats]) -> None:
    """Render language breakdown with tabs for All Files and Code Only."""
    main_cats = {k: v for k, v in categories.items() if k not in ("test_data", "plans")}
    code_stats = categories.get("code")

    st.markdown("### Language Breakdown")

    tab1, tab2 = st.tabs(["All Files", "Code Only"])

    with tab1:
        lang_stats_all: dict[str, dict] = defaultdict(
            lambda: {"files": 0, "code": 0, "comments": 0}
        )
        for cat_stats in main_cats.values():
            for f in cat_stats.files:
                lang_stats_all[f.language]["files"] += 1
                lang_stats_all[f.language]["code"] += f.code_lines
                lang_stats_all[f.language]["comments"] += f.comment_lines

        sorted_langs = sorted(lang_stats_all.items(), key=lambda x: x[1]["code"], reverse=True)[:12]

        col1, col2 = st.columns([1, 1])
        with col1:
            lang_df = pd.DataFrame(
                [
                    {
                        "Language": lang,
                        "Files": stats["files"],
                        "Code Lines": stats["code"],
                        "Comments": stats["comments"],
                    }
                    for lang, stats in sorted_langs
                ]
            )
            st.dataframe(lang_df, use_container_width=True, hide_index=True)

        with col2:
            chart_df = pd.DataFrame(
                [{"Language": lang, "Lines": stats["code"]} for lang, stats in sorted_langs[:8]]
            )
            if not chart_df.empty:
                st.bar_chart(chart_df.set_index("Language"))

    with tab2:
        if code_stats and code_stats.files:
            lang_stats_code: dict[str, dict] = defaultdict(
                lambda: {"files": 0, "code": 0, "comments": 0}
            )
            for f in code_stats.files:
                lang_stats_code[f.language]["files"] += 1
                lang_stats_code[f.language]["code"] += f.code_lines
                lang_stats_code[f.language]["comments"] += f.comment_lines

            sorted_code_langs = sorted(
                lang_stats_code.items(), key=lambda x: x[1]["code"], reverse=True
            )[:12]

            col1, col2 = st.columns([1, 1])
            with col1:
                code_lang_df = pd.DataFrame(
                    [
                        {
                            "Language": lang,
                            "Files": stats["files"],
                            "Code Lines": stats["code"],
                            "Comments": stats["comments"],
                        }
                        for lang, stats in sorted_code_langs
                    ]
                )
                st.dataframe(code_lang_df, use_container_width=True, hide_index=True)

            with col2:
                chart_df = pd.DataFrame(
                    [
                        {"Language": lang, "Lines": stats["code"]}
                        for lang, stats in sorted_code_langs[:8]
                    ]
                )
                if not chart_df.empty:
                    st.bar_chart(chart_df.set_index("Language"))
        else:
            st.info("No code-only files found.")


def render_file_distribution(categories: dict[str, CategoryStats]) -> None:
    """Render file size distribution."""
    main_cats = {k: v for k, v in categories.items() if k not in ("test_data", "plans")}

    st.markdown("### File Size Distribution")

    all_files = []
    for cat_stats in main_cats.values():
        all_files.extend(cat_stats.files)

    buckets = {
        "1-50": 0,
        "51-100": 0,
        "101-200": 0,
        "201-500": 0,
        "501-1000": 0,
        "1000+": 0,
    }

    for f in all_files:
        lines = f.code_lines
        if lines <= 50:
            buckets["1-50"] += 1
        elif lines <= 100:
            buckets["51-100"] += 1
        elif lines <= 200:
            buckets["101-200"] += 1
        elif lines <= 500:
            buckets["201-500"] += 1
        elif lines <= 1000:
            buckets["501-1000"] += 1
        else:
            buckets["1000+"] += 1

    col1, col2 = st.columns([1, 2])

    with col1:
        dist_df = pd.DataFrame(
            [
                {
                    "Size (lines)": bucket,
                    "Count": count,
                    "Percent": f"{count / len(all_files) * 100:.1f}%" if all_files else "0%",
                }
                for bucket, count in buckets.items()
            ]
        )
        st.dataframe(dist_df, use_container_width=True, hide_index=True)

    with col2:
        chart_df = pd.DataFrame(
            [{"Size": bucket, "Files": count} for bucket, count in buckets.items()]
        )
        st.bar_chart(chart_df.set_index("Size"))


def render_attention_needed(categories: dict[str, CategoryStats], repo_root: Path) -> None:
    """Render large files and TODO/FIXME sections."""
    main_cats = {k: v for k, v in categories.items() if k not in ("test_data", "plans")}
    code_stats = categories.get("code")

    st.markdown("### Attention Needed")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Large Code Files (>500 lines)**")
        if code_stats:
            large_files = [f for f in code_stats.files if f.code_lines > 500]
            large_files.sort(key=lambda x: x.code_lines, reverse=True)
            if large_files:
                large_df = pd.DataFrame(
                    [
                        {
                            "File": _rel_path(f.path, repo_root),
                            "Lines": f.code_lines,
                            "Language": f.language,
                        }
                        for f in large_files[:10]
                    ]
                )
                st.dataframe(large_df, use_container_width=True, hide_index=True)
                st.caption(f"Found {len(large_files)} files over 500 lines - consider refactoring")
            else:
                st.success("All code files are under 500 lines")

    with col2:
        st.markdown("**Files with TODOs/FIXMEs**")
        todo_files = [
            f
            for cat_stats in main_cats.values()
            for f in cat_stats.files
            if f.todo_count + f.fixme_count > 0
        ]

        todo_files.sort(key=lambda x: x.todo_count + x.fixme_count, reverse=True)

        if todo_files:
            todo_df = pd.DataFrame(
                [
                    {
                        "File": _rel_path(f.path, repo_root),
                        "TODOs": f.todo_count,
                        "FIXMEs": f.fixme_count,
                        "Total": f.todo_count + f.fixme_count,
                    }
                    for f in todo_files[:10]
                ]
            )
            st.dataframe(todo_df, use_container_width=True, hide_index=True)
            total_todos = sum(f.todo_count for f in todo_files)
            total_fixmes = sum(f.fixme_count for f in todo_files)
            st.caption(
                f"Total: {total_todos} TODOs, {total_fixmes} FIXMEs across {len(todo_files)} files"
            )
        else:
            st.success("No TODOs or FIXMEs found")


def render_category_breakdown(categories: dict[str, CategoryStats]) -> None:
    """Render category breakdown table and chart."""
    plans_stats = categories.get("plans")
    test_data_stats = categories.get("test_data")

    st.markdown("### Category Breakdown")

    cat_data = []
    for cat_name in ["code", "tests", "docs", "scripts"]:
        cat = categories.get(cat_name)
        if cat and cat.files:
            cat_data.append(
                {
                    "Category": cat_name.capitalize(),
                    "Files": len(cat.files),
                    "Total Lines": cat.total_lines,
                    "Code Lines": cat.code_lines,
                    "Comments": cat.comment_lines,
                    "Blanks": cat.blank_lines,
                }
            )

    if plans_stats and plans_stats.files:
        cat_data.append(
            {
                "Category": "Plans (docs)",
                "Files": len(plans_stats.files),
                "Total Lines": plans_stats.total_lines,
                "Code Lines": plans_stats.code_lines,
                "Comments": "-",
                "Blanks": "-",
            }
        )

    if test_data_stats and test_data_stats.files:
        cat_data.append(
            {
                "Category": "Test Data (fixtures)",
                "Files": len(test_data_stats.files),
                "Total Lines": test_data_stats.total_lines,
                "Code Lines": test_data_stats.code_lines,
                "Comments": "-",
                "Blanks": "-",
            }
        )

    col1, col2 = st.columns([2, 1])
    with col1:
        st.dataframe(pd.DataFrame(cat_data), use_container_width=True, hide_index=True)

    with col2:
        pie_data = pd.DataFrame(
            [
                {"Category": cat_name.capitalize(), "Lines": categories[cat_name].code_lines}
                for cat_name in ["code", "tests", "docs", "scripts"]
                if categories.get(cat_name) and categories[cat_name].files
            ]
        )
        if not pie_data.empty:
            st.bar_chart(pie_data.set_index("Category"))


def _rel_path(file_path: str, repo_root: Path) -> str:
    """Convert absolute path to relative for display."""
    try:
        return str(Path(file_path).relative_to(repo_root))
    except ValueError:
        return Path(file_path).name


def main() -> None:
    args = parse_args()

    repo_root = Path(args.path).resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        st.error(f"Invalid path: {repo_root}")
        sys.exit(2)

    config_path = args.config

    st.set_page_config(
        page_title="Codebase Analysis",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    st.title("Codebase Analysis Dashboard")
    st.caption(f"`{repo_root.name}` — {repo_root}")

    with st.spinner("Analyzing codebase..."):
        categories = analyze_codebase(str(repo_root), config_path)

    render_overview(categories)
    st.divider()
    render_code_vs_tests(categories)
    st.divider()
    render_language_breakdown(categories)
    st.divider()
    render_file_distribution(categories)
    st.divider()
    render_attention_needed(categories, repo_root)
    st.divider()
    render_category_breakdown(categories)
    st.divider()
    st.caption("Create `.codebase-analysis.yaml` to customize patterns | Data cached for 60s")


if __name__ == "__main__":
    main()
