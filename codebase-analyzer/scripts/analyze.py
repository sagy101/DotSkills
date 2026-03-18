#!/usr/bin/env python3
"""
Codebase Analyzer — Core Analysis Engine & CLI Entry Point

A generic, configurable codebase analyzer that produces structured metrics.
Accepts any repository path and outputs in terminal, JSON, or markdown format.

Usage:
    python analyze.py --path /path/to/repo --output terminal --sections all
    python analyze.py --output json --sections summary,languages
    python analyze.py --output markdown
"""

import argparse
import fnmatch
import re
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:
    yaml = None

# ============================================================================
# Constants
# ============================================================================

ALL_SECTIONS = [
    "summary",
    "categories",
    "languages",
    "file-distribution",
    "large-files",
    "todos",
    "churn",
]

DEFAULT_CONFIG: dict[str, Any] = {
    "test_patterns": ["tests", "test", "e2e", "__tests__", "spec"],
    "test_file_patterns": ["*.test.*", "test_*.*", "*.spec.*", "*.stories.*"],
    "test_data_patterns": ["fixtures", "testdata", "__fixtures__", "mocks"],
    "script_patterns": ["scripts", "bin", "tools"],
    "plan_patterns": ["plans", "planning", "rfcs", "proposals", "adrs"],
    "doc_extensions": [".md", ".rst", ".txt"],
    "skip_extensions": [
        ".lock",
        ".svg",
        ".png",
        ".jpg",
        ".jpeg",
        ".ico",
        ".gif",
        ".pdf",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".webp",
        ".mp4",
        ".mp3",
    ],
    "skip_files": [
        "pnpm-lock.yaml",
        "package-lock.json",
        "yarn.lock",
        "uv.lock",
        ".DS_Store",
    ],
    "skip_dirs": [
        "node_modules",
        ".git",
        "dist",
        "build",
        "__pycache__",
        ".next",
        ".venv",
        "venv",
        ".codebase-analyzer-venv",
    ],
    "large_file_threshold": 500,
    "top_files_count": 10,
}

LANGUAGE_EXTENSIONS: dict[str, str] = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript (React)",
    ".js": "JavaScript",
    ".jsx": "JavaScript (React)",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".md": "Markdown",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sql": "SQL",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".dockerfile": "Dockerfile",
    ".mjs": "JavaScript (ESM)",
    ".mts": "TypeScript (ESM)",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".rb": "Ruby",
    ".php": "PHP",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C/C++ Header",
    ".cs": "C#",
    ".svelte": "Svelte",
    ".vue": "Vue",
    ".astro": "Astro",
    ".graphql": "GraphQL",
    ".gql": "GraphQL",
    ".proto": "Protocol Buffers",
}

COMMENT_PATTERNS: dict[str, tuple[str | None, tuple[str, ...]]] = {
    "Python": ("#", ('"""', "'''")),
    "TypeScript": ("//", ("/*",)),
    "TypeScript (React)": ("//", ("/*",)),
    "JavaScript": ("//", ("/*",)),
    "JavaScript (React)": ("//", ("/*",)),
    "JavaScript (ESM)": ("//", ("/*",)),
    "TypeScript (ESM)": ("//", ("/*",)),
    "Svelte": ("//", ("/*", "<!--")),
    "Vue": ("//", ("/*", "<!--")),
    "Astro": ("//", ("/*", "<!--")),
    "GraphQL": ("#", ()),
    "Protocol Buffers": ("//", ("/*",)),
    "Shell": ("#", ()),
    "YAML": ("#", ()),
    "TOML": ("#", ()),
    "CSS": (None, ("/*",)),
    "SCSS": ("//", ("/*",)),
    "Go": ("//", ("/*",)),
    "Rust": ("//", ("/*",)),
    "Java": ("//", ("/*",)),
    "Kotlin": ("//", ("/*",)),
    "Swift": ("//", ("/*",)),
    "Ruby": ("#", ("=begin",)),
    "PHP": ("//", ("/*",)),
    "C": ("//", ("/*",)),
    "C++": ("//", ("/*",)),
    "C/C++ Header": ("//", ("/*",)),
    "C#": ("//", ("/*",)),
}

MULTILINE_END_MAP: dict[str, str] = {
    "/*": "*/",
    '"""': '"""',
    "'''": "'''",
    "=begin": "=end",
}


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class FileStats:
    """Statistics for a single file."""

    path: str
    total_lines: int = 0
    code_lines: int = 0
    comment_lines: int = 0
    blank_lines: int = 0
    language: str = "Other"
    todo_count: int = 0
    fixme_count: int = 0


@dataclass
class CategoryStats:
    """Aggregated statistics for a category."""

    files: list[FileStats] = field(default_factory=list)
    total_lines: int = 0
    code_lines: int = 0
    comment_lines: int = 0
    blank_lines: int = 0
    todo_count: int = 0
    fixme_count: int = 0

    def add_file(self, file_stats: FileStats) -> None:
        self.files.append(file_stats)
        self.total_lines += file_stats.total_lines
        self.code_lines += file_stats.code_lines
        self.comment_lines += file_stats.comment_lines
        self.blank_lines += file_stats.blank_lines
        self.todo_count += file_stats.todo_count
        self.fixme_count += file_stats.fixme_count


@dataclass
class AnalysisResult:
    """Complete analysis result."""

    repo_root: Path
    categories: dict[str, CategoryStats]
    config: dict[str, Any]
    most_changed: list[tuple[str, int]] = field(default_factory=list)
    analysis_time: float = 0.0


# ============================================================================
# Configuration
# ============================================================================


def load_config(repo_root: Path, config_path: Path | None = None) -> dict[str, Any]:
    """Load configuration from YAML file or use defaults.

    If config_path is explicitly provided but does not exist, raises FileNotFoundError.
    If config_path is None, falls back to <repo_root>/.codebase-analysis.yaml (optional).
    """
    config = DEFAULT_CONFIG.copy()
    explicit = config_path is not None

    if config_path is None:
        config_path = repo_root / ".codebase-analysis.yaml"

    if not config_path.exists():
        if explicit:
            raise FileNotFoundError(
                f"Config file not found: {config_path}\n"
                f"Verify the --config path is correct, or omit --config to use built-in defaults."
            )
        return config

    try:
        if yaml is None:
            raise ImportError("PyYAML is not installed. Install it to load custom configuration.")

        with open(config_path) as f:
            user_config = yaml.safe_load(f) or {}
    except ImportError as exc:
        print(
            f"ERROR: {exc}\n"
            f"Fix: Run 'python3 <skill_dir>/scripts/analyzer_setup_env.py' to install dependencies.",
            file=sys.stderr,
        )
        sys.exit(1)
    except yaml.YAMLError as exc:
        raise ValueError(
            f"Invalid YAML in config file '{config_path}':\n{exc}\n"
            f"Fix the YAML syntax or delete the file to use built-in defaults."
        ) from exc

    if not isinstance(user_config, dict):
        raise ValueError(
            f"Config file '{config_path}' must contain a YAML mapping (key: value pairs), "
            f"got {type(user_config).__name__}.\n"
            f"See references/CONFIG.md for the expected format."
        )

    config.update(user_config)
    _validate_config(config, config_path)
    return config


def _validate_list_config(config: dict[str, Any], config_path: Path) -> None:
    """Validate list-type config keys."""
    list_keys = [
        "test_patterns",
        "test_file_patterns",
        "test_data_patterns",
        "script_patterns",
        "plan_patterns",
        "doc_extensions",
        "skip_extensions",
        "skip_files",
        "skip_dirs",
    ]
    for key in list_keys:
        value = config.get(key)
        if value is None:
            config[key] = []
            continue
        if not isinstance(value, list):
            print(
                f"WARNING: Config key '{key}' in '{config_path}' should be a list, "
                f"got {type(value).__name__}. Using default or empty list.",
                file=sys.stderr,
            )
            if key in DEFAULT_CONFIG and isinstance(DEFAULT_CONFIG[key], list):
                config[key] = DEFAULT_CONFIG[key]
            else:
                config[key] = []


def _validate_int_config(config: dict[str, Any], config_path: Path) -> None:
    """Validate integer-type config keys."""
    int_keys = ["large_file_threshold", "top_files_count"]
    for key in int_keys:
        value = config.get(key)
        if value is not None and not isinstance(value, int):
            try:
                config[key] = int(value)
            except (ValueError, TypeError):
                print(
                    f"WARNING: Config key '{key}' in '{config_path}' should be an integer, "
                    f"got {type(value).__name__}: {value!r}. Using default.",
                    file=sys.stderr,
                )
                config[key] = DEFAULT_CONFIG.get(key, 0)


def _validate_config(config: dict[str, Any], config_path: Path) -> None:
    """Validate config types and coerce if possible."""
    _validate_list_config(config, config_path)
    _validate_int_config(config, config_path)


# ============================================================================
# File Discovery & Classification
# ============================================================================


def get_tracked_files(repo_root: Path) -> set[Path]:
    """Get all files to analyze. Uses git ls-files (tracked + untracked) if available."""
    try:
        # Tracked files
        cmd_tracked = ["git", "ls-files"]
        result_tracked = subprocess.run(
            cmd_tracked,
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )

        # Untracked files (respecting .gitignore)
        cmd_untracked = ["git", "ls-files", "--others", "--exclude-standard"]
        result_untracked = subprocess.run(
            cmd_untracked,
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )

        files = set()
        for out in [result_tracked.stdout, result_untracked.stdout]:
            for line in out.strip().split("\n"):
                if line:
                    files.add(repo_root / line)

        return files

    except (subprocess.CalledProcessError, FileNotFoundError):
        # Not a git repo or git not installed — walk the directory
        print(
            "NOTE: git not found or not a git repo. Using fallback directory walker.\n"
            "      Files ignored by .gitignore may be included unless explicitly skipped in config.",
            file=sys.stderr,
        )
        return {p for p in repo_root.rglob("*") if p.is_file()}


def should_skip(file_path: Path, repo_root: Path, config: dict[str, Any]) -> bool:
    """Check if a file should be excluded from analysis."""
    try:
        rel_path = file_path.relative_to(repo_root)
    except ValueError:
        return True
    parts = rel_path.parts
    suffix = file_path.suffix.lower()

    if suffix in config["skip_extensions"]:
        return True
    if file_path.name in config["skip_files"]:
        return True
    return any(d in parts for d in config["skip_dirs"])


def detect_language(file_path: Path) -> str:
    """Determine language from file extension or shebang."""
    if file_path.name == "Dockerfile":
        return "Dockerfile"

    lang = LANGUAGE_EXTENSIONS.get(file_path.suffix.lower())
    if lang:
        return lang

    # Check shebang for files without extension or with unknown extension
    try:
        # Read only the first line
        with file_path.open("r", encoding="utf-8", errors="ignore") as f:
            first_line = f.readline().strip()
            if first_line.startswith("#!"):
                lower_line = first_line.lower()
                if "python" in lower_line:
                    return "Python"
                if "node" in lower_line:
                    return "JavaScript"
                if "bash" in lower_line or "sh" in lower_line:
                    return "Shell"
                if "ruby" in lower_line:
                    return "Ruby"
                if "perl" in lower_line:
                    return "Perl"
                if "php" in lower_line:
                    return "PHP"
    except Exception:
        pass

    return "Other"


def categorize_file(file_path: Path, repo_root: Path, config: dict[str, Any]) -> str:
    """Categorize a file into code, tests, test_data, docs, plans, or scripts."""
    try:
        rel_path = file_path.relative_to(repo_root)
    except ValueError:
        return "code"

    parts = rel_path.parts
    name = file_path.name
    suffix = file_path.suffix.lower()

    # 1. Plans (highest priority, includes docs/diagrams in plan dirs)
    if any(p in parts for p in config.get("plan_patterns", [])):
        return "plans"

    # 2. Documentation
    if suffix in config["doc_extensions"]:
        return "docs"

    # 3. Test Data
    if any(p in parts for p in config["test_data_patterns"]):
        return "test_data"

    # 4. Tests (directory)
    if any(p in parts for p in config["test_patterns"]):
        return "tests"

    # 5. Tests (file patterns)
    for pattern in config["test_file_patterns"]:
        if fnmatch.fnmatch(name, pattern):
            return "tests"

    # 6. Scripts
    if any(p in parts for p in config["script_patterns"]):
        return "scripts"

    return "code"


# ============================================================================
# File Analysis
# ============================================================================


def _check_multiline_end(stripped: str, multiline_end: str) -> tuple[str, bool, str | None]:
    """Check if multiline block ends on this line."""
    if multiline_end in stripped:
        end_idx = stripped.index(multiline_end)
        after = stripped[end_idx + len(multiline_end) :].strip()
        if after:
            return "code", False, multiline_end
        return "comment", False, multiline_end
    return "comment", True, multiline_end


def _check_multiline_start(
    stripped: str, start: str, end: str | None
) -> tuple[str, bool, str | None]:
    """Check if multiline block starts on this line."""
    start_idx = stripped.index(start)
    rest = stripped[start_idx + len(start) :]

    if end and end in rest:
        # Closes on same line
        has_code_before = start_idx > 0
        end_idx = rest.index(end)
        after = rest[end_idx + len(end) :].strip()
        if has_code_before or after:
            return "code", False, None
        return "comment", False, None

    # Opens new block
    if start_idx > 0:
        return "code", True, end
    return "comment", True, end


def _classify_line(
    stripped: str,
    single_comment: str | None,
    multi_starts: tuple[str, ...],
    in_multiline: bool,
    multiline_end: str | None,
) -> tuple[str, bool, str | None]:
    """Classify a single stripped line. Returns (kind, in_multiline, multiline_end)."""
    if not stripped:
        return "blank", in_multiline, multiline_end

    if in_multiline:
        if multiline_end:
            return _check_multiline_end(stripped, multiline_end)
        return "comment", True, None

    for start in multi_starts:
        if start in stripped:
            return _check_multiline_start(stripped, start, MULTILINE_END_MAP.get(start))

    if single_comment and stripped.startswith(single_comment):
        return "comment", False, multiline_end

    return "code", False, multiline_end


def is_binary_file(file_path: Path) -> bool:
    """Check if a file is binary by looking for null bytes in the first 1024 bytes."""
    try:
        with file_path.open("rb") as f:
            chunk = f.read(1024)
            return b"\x00" in chunk
    except Exception:
        return True  # Treat read errors as binary/unreadable


def analyze_file(file_path: Path) -> FileStats:
    """Analyze a single file for line-level statistics."""
    # Check for binary content first to avoid processing large binary files as text
    if is_binary_file(file_path):
        return FileStats(path=str(file_path), language="Other", total_lines=0)

    stats = FileStats(path=str(file_path), language=detect_language(file_path))

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return stats

    # Use splitlines() to avoid phantom empty lines from trailing newlines
    lines = content.splitlines()
    stats.total_lines = len(lines)

    # If file is empty, splitlines() returns [], which is correct (0 lines)
    if not lines:
        return stats

    stats.todo_count = len(re.findall(r"\bTODO\b", content, re.IGNORECASE))
    stats.fixme_count = len(re.findall(r"\bFIXME\b", content, re.IGNORECASE))

    single_comment, multi_starts = COMMENT_PATTERNS.get(stats.language, (None, ()))
    in_multiline = False
    multiline_end: str | None = None

    for line in lines:
        kind, in_multiline, multiline_end = _classify_line(
            line.strip(), single_comment, multi_starts, in_multiline, multiline_end
        )
        if kind == "blank":
            stats.blank_lines += 1
        elif kind == "comment":
            stats.comment_lines += 1
        else:
            stats.code_lines += 1

    return stats


# ============================================================================
# Git Metrics
# ============================================================================


def is_git_repo(repo_root: Path) -> bool:
    """Check if the path is inside a git repository."""
    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=repo_root,
            capture_output=True,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_most_changed_files(
    repo_root: Path, tracked_files: set[Path], limit: int = 10
) -> list[tuple[str, int]]:
    """Get files with the most commits (high churn). Only includes currently tracked files."""
    if not is_git_repo(repo_root):
        return []
    try:
        result = subprocess.run(
            ["git", "log", "--format=", "--name-only", "-n", "500"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        file_counts: dict[str, int] = defaultdict(int)
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                # Only include if file still exists and is tracked
                full_path = repo_root / line.strip()
                if full_path in tracked_files:
                    file_counts[line.strip()] += 1
        sorted_files = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)
        return sorted_files[:limit]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


# ============================================================================
# Main Analysis
# ============================================================================

CATEGORY_NAMES = ["code", "tests", "test_data", "docs", "plans", "scripts"]


def run_analysis(
    repo_root: Path,
    config_path: Path | None = None,
    progress_callback: Any = None,
    sections: list[str] | None = None,
) -> AnalysisResult:
    """Perform full codebase analysis and return structured results."""
    start_time = time.time()
    sections = sections or ALL_SECTIONS

    config = load_config(repo_root, config_path)
    categories: dict[str, CategoryStats] = {name: CategoryStats() for name in CATEGORY_NAMES}

    tracked_files = get_tracked_files(repo_root)

    if progress_callback:
        progress_callback(f"Analyzing {len(tracked_files)} files...")

    for file_path in sorted(tracked_files):
        if not file_path.is_file():
            continue
        if should_skip(file_path, repo_root, config):
            continue

        category = categorize_file(file_path, repo_root, config)
        file_stats = analyze_file(file_path)
        categories[category].add_file(file_stats)

    total_analyzed = sum(len(cat.files) for cat in categories.values())
    if total_analyzed == 0:
        print(
            "WARNING: No files were analyzed. Possible causes:\n"
            "  - The directory is empty or contains only binary/skipped files\n"
            "  - All files are excluded by skip_extensions, skip_files, or skip_dirs in config\n"
            "  - If not a git repo, ensure the directory contains source files\n"
            f"  Scanned directory: {repo_root}\n"
            f"  Files discovered: {len(tracked_files)}",
            file=sys.stderr,
        )

    most_changed = []
    if "churn" in sections:
        most_changed = get_most_changed_files(
            repo_root, tracked_files, config.get("top_files_count", 10)
        )

    return AnalysisResult(
        repo_root=repo_root,
        categories=categories,
        config=config,
        most_changed=most_changed,
        analysis_time=time.time() - start_time,
    )


# ============================================================================
# Shared Metric Helpers (used by all formatters)
# ============================================================================


def compute_summary(result: AnalysisResult) -> dict[str, Any]:
    """Compute top-level summary metrics from an AnalysisResult."""
    cats = result.categories
    # Include all categories in the summary totals to match file system reality
    all_cats = cats.values()

    total_files = sum(len(c.files) for c in all_cats)
    total_lines = sum(c.total_lines for c in all_cats)
    total_code = sum(c.code_lines for c in all_cats)
    total_comments = sum(c.comment_lines for c in all_cats)
    total_blank = sum(c.blank_lines for c in all_cats)
    total_todos = sum(c.todo_count for c in all_cats)
    total_fixmes = sum(c.fixme_count for c in all_cats)

    code_stats = cats.get("code")
    test_stats = cats.get("tests")

    test_code_ratio = None
    if code_stats and test_stats and code_stats.code_lines > 0:
        test_code_ratio = test_stats.code_lines / code_stats.code_lines

    comment_pct = (total_comments / total_code * 100) if total_code > 0 else 0.0

    return {
        "total_files": total_files,
        "total_lines": total_lines,
        "total_code": total_code,
        "total_comments": total_comments,
        "total_blank": total_blank,
        "total_todos": total_todos,
        "total_fixmes": total_fixmes,
        "test_code_ratio": test_code_ratio,
        "comment_pct": comment_pct,
        "analysis_time": result.analysis_time,
    }


def compute_language_breakdown(
    result: AnalysisResult,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Compute language breakdown, optionally filtered to a single category."""
    lang_stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {"files": 0, "code": 0, "comments": 0}
    )
    cats_to_check = (
        [result.categories[category]]
        if category and category in result.categories
        else list(result.categories.values())
    )
    for cat in cats_to_check:
        for f in cat.files:
            lang_stats[f.language]["files"] += 1
            lang_stats[f.language]["code"] += f.code_lines
            lang_stats[f.language]["comments"] += f.comment_lines

    return [
        {"language": lang, **stats}
        for lang, stats in sorted(lang_stats.items(), key=lambda x: x[1]["code"], reverse=True)
    ]


def compute_file_distribution(result: AnalysisResult) -> dict[str, int]:
    """Compute file-size distribution buckets."""
    buckets = {"0-50": 0, "51-100": 0, "101-200": 0, "201-500": 0, "501-1000": 0, "1000+": 0}
    for cat_name, cat in result.categories.items():
        if cat_name == "test_data":
            continue
        for f in cat.files:
            lines = f.total_lines
            if lines <= 50:
                buckets["0-50"] += 1
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
    return buckets


def compute_large_files(result: AnalysisResult) -> list[dict[str, Any]]:
    """Find code files exceeding the configured threshold."""
    threshold = result.config.get("large_file_threshold", 500)
    code_stats = result.categories.get("code")
    if not code_stats:
        return []
    large = [f for f in code_stats.files if f.code_lines > threshold]
    large.sort(key=lambda x: x.code_lines, reverse=True)

    # Use relative path if possible for display
    def _fmt_path(p: str) -> str:
        try:
            return str(Path(p).relative_to(result.repo_root))
        except ValueError:
            return p

    return [
        {"file": _fmt_path(f.path), "lines": f.code_lines, "language": f.language} for f in large
    ]


def compute_todo_files(result: AnalysisResult) -> list[dict[str, Any]]:
    """Find files with TODOs/FIXMEs, sorted by count."""
    all_files = []
    for cat_name, cat in result.categories.items():
        if cat_name == "test_data":
            continue
        all_files.extend(cat.files)
    todo_files = [f for f in all_files if f.todo_count + f.fixme_count > 0]
    todo_files.sort(key=lambda x: x.todo_count + x.fixme_count, reverse=True)

    # Use relative path if possible for display
    def _fmt_path(p: str) -> str:
        try:
            return str(Path(p).relative_to(result.repo_root))
        except ValueError:
            return p

    return [
        {"file": _fmt_path(f.path), "todos": f.todo_count, "fixmes": f.fixme_count}
        for f in todo_files[: result.config.get("top_files_count", 10)]
    ]


# ============================================================================
# CLI
# ============================================================================


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze a codebase and produce structured metrics."
    )
    parser.add_argument(
        "--path",
        default=".",
        help="Path to the repository root (default: current directory)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to .codebase-analysis.yaml (default: <path>/.codebase-analysis.yaml)",
    )
    parser.add_argument(
        "--output",
        choices=["terminal", "json", "markdown"],
        default="terminal",
        help="Output format (default: terminal)",
    )
    parser.add_argument(
        "--sections",
        default="all",
        help=(
            "Comma-separated list of sections to include: "
            + ", ".join(ALL_SECTIONS)
            + ", or 'all' (default: all)"
        ),
    )
    return parser.parse_args()


def resolve_sections(sections_arg: str) -> list[str]:
    """Parse the --sections argument into a list of section names."""
    if sections_arg.strip().lower() == "all":
        return list(ALL_SECTIONS)
    requested = [s.strip().lower() for s in sections_arg.split(",")]
    valid = [s for s in requested if s in ALL_SECTIONS]
    if not valid:
        print(f"WARNING: No valid sections in '{sections_arg}'. Using all.", file=sys.stderr)
        return list(ALL_SECTIONS)
    return valid


def main() -> None:
    args = parse_args()

    repo_root = Path(args.path).resolve()
    if not repo_root.exists():
        print(
            f"ERROR: Path does not exist: '{repo_root}'\n"
            f"Provide a valid directory path with --path.",
            file=sys.stderr,
        )
        sys.exit(2)
    if not repo_root.is_dir():
        print(
            f"ERROR: '{repo_root}' is a file, not a directory.\n"
            f"Provide a directory path with --path (e.g. --path .).",
            file=sys.stderr,
        )
        sys.exit(2)

    config_path = Path(args.config).resolve() if args.config else None
    sections = resolve_sections(args.sections)

    try:
        result = run_analysis(repo_root, config_path, sections=sections)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)

    if args.output == "terminal":
        try:
            from report_terminal import render_terminal
        except ImportError:
            print(
                "ERROR: Rich library is not installed (required for terminal output).\n"
                "Fix: Run 'python3 <skill_dir>/scripts/analyzer_setup_env.py' to install dependencies,\n"
                "or use --output json or --output markdown which have no extra dependencies.",
                file=sys.stderr,
            )
            sys.exit(1)
        render_terminal(result, sections)
    elif args.output == "json":
        from report_json import render_json

        render_json(result, sections)
    elif args.output == "markdown":
        from report_markdown import render_markdown

        render_markdown(result, sections)


if __name__ == "__main__":
    main()
