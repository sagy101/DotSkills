# Codebase Analyzer — Design Document

> This document covers **architecture**, **capabilities**, and **key design decisions** for the codebase-analyzer skill.

---

## Why This Skill Exists

AI agents frequently need to understand codebase size, structure, and health metrics before making decisions — but manually counting lines, identifying test ratios, or finding TODOs across hundreds of files is tedious and error-prone. This skill provides a single command that produces structured, actionable metrics for any codebase.

Unlike language-specific tools (e.g. `cloc`, `scc`), this analyzer is:
1. **Category-aware** — classifies files into code, tests, test data, docs, plans, and scripts based on configurable patterns
2. **Agent-friendly** — outputs in terminal, JSON, Markdown, or interactive web dashboard
3. **Zero-config by default** — works on any codebase out of the box, with optional YAML customization

---

## Capabilities

| Capability | Description |
|---|---|
| **Line counting** | Total, code, comment, and blank lines per file with language-aware comment detection |
| **Category classification** | Files classified as code, tests, test data, docs, plans, or scripts via configurable patterns |
| **Language detection** | Extension-based + shebang fallback for 30+ languages with per-language comment parsing |
| **Test:Code ratio** | Ratio of test code lines to production code lines — a proxy for test coverage |
| **File size distribution** | Bucketed histogram (0-50, 51-100, ..., 1000+ lines) to spot structural patterns |
| **Large file detection** | Flags code files exceeding a configurable threshold (default: 500 lines) |
| **TODO/FIXME tracking** | Counts and ranks files by annotation density |
| **Git churn** | Most frequently changed files from recent history — identifies hotspots |
| **Multi-format output** | Terminal (Rich), JSON, Markdown, or Streamlit web dashboard |
| **YAML configuration** | Optional per-repo config for patterns, thresholds, and skip rules |

---

## Architecture

```
User/Agent
    │
    ▼
analyze.py ──────────── CLI entry point: argparse, path validation, section selection
    │
    ├── load_config() ──── Config discovery (.codebase-analysis.yaml or defaults)
    │                       YAML parsing, validation, type coercion
    │
    ├── get_tracked_files() ── File discovery (git ls-files or directory walk fallback)
    │
    ├── categorize_file() ──── Pattern-based classification (code/tests/docs/scripts/plans)
    │
    ├── analyze_file() ──────── Per-file analysis: line counting, comment detection,
    │                            TODO/FIXME extraction, language detection
    │
    ├── get_most_changed_files() ── Git churn (top N files by commit count)
    │
    └── Output formatters:
        ├── report_terminal.py ── Rich tables and panels
        ├── report_json.py ────── Structured JSON to stdout
        ├── report_markdown.py ── Markdown tables to stdout
        └── report_web.py ─────── Streamlit dashboard (charts, tables, metrics)

analyzer_preflight.py ─── Single-pass pre-flight checks (Python, venv, deps, git, scripts, path)
analyzer_setup_env.py ──── Environment setup (venv creation, dependency installation)
```

### Data Flow

```
1. CLI args parsed → repo_root, config_path, output format, sections
2. Config loaded (YAML file or built-in defaults)
3. Files discovered (git ls-files or rglob fallback)
4. Each file: skip check → categorize → analyze (line-level stats)
5. Results aggregated into AnalysisResult dataclass
6. Formatter renders output in chosen format
```

---

## Key Design Decisions

**1. Category-first classification** — Files are classified by directory patterns and file name globs, not by content. This is fast (no file reads needed for classification) and matches how developers organize code. The priority order is: plans > docs > test data > tests (directory) > tests (file pattern) > scripts > code.

**2. Comment detection with multiline support** — Each language has defined single-line and multiline comment patterns. The analyzer tracks multiline block state across lines, handling nested scenarios (code before/after block markers). This gives accurate code-vs-comment splits without AST parsing.

**3. Git-first file discovery with fallback** — `git ls-files` respects `.gitignore` and includes both tracked and untracked files. If git is unavailable, the analyzer falls back to `rglob("*")` with skip patterns from config. This means the skill works in non-git directories.

**4. Shared metric helpers** — Functions like `compute_summary()`, `compute_language_breakdown()`, `compute_file_distribution()` are defined once in `analyze.py` and used by all formatters. This ensures consistent metrics across output formats.

**5. Web dashboard as a separate process** — `--output web` launches Streamlit as a subprocess via `streamlit run report_web.py`. This keeps the core analysis pure Python with no web framework dependency for non-web users. The web script imports the same analysis functions and adds visualization.

**6. Config replaces, not merges** — User config values replace defaults for the same key entirely. For list fields like `skip_dirs`, the user's list replaces the default list. This avoids surprising merge behavior and makes config explicit.

**7. Binary file detection** — Files are checked for null bytes in the first 1024 bytes before text analysis. This prevents wasting time parsing large binary files that slipped past extension filters.

---

## File Structure

```
codebase-analyzer/
├── SKILL.md                         # Agent-facing: workflow, operations, rules
├── assets/
│   └── default-config.yaml          # Copy-paste config template
├── references/
│   ├── CONFIG.md                    # Full config schema reference
│   └── REPORT_FORMAT.md            # Output format details and metric interpretation
├── scripts/
│   ├── analyze.py                   # Core engine + CLI entry point
│   ├── analyzer_preflight.py        # Single-pass pre-flight checks
│   ├── analyzer_setup_env.py        # Venv setup (idempotent)
│   ├── report_terminal.py           # Rich terminal formatter
│   ├── report_json.py               # JSON formatter
│   ├── report_markdown.py           # Markdown formatter
│   ├── report_web.py                # Streamlit web dashboard
│   └── requirements.txt             # Python dependencies
└── .codebase-analyzer-venv/         # Created by setup script (gitignored)
```

---

## Dependencies

| Package | Purpose | Required for |
|---|---|---|
| **PyYAML** | Config file parsing | All output formats |
| **Rich** | Terminal tables, panels, colors | `--output terminal` |
| **Streamlit** | Web dashboard framework | `--output web` |
| **pandas** | DataFrame operations for dashboard tables/charts | `--output web` |

All dependencies are installed into an isolated venv by `analyzer_setup_env.py`. The JSON and Markdown formatters use only stdlib — they work even without `rich` installed.

---

## Output Formats

| Format | Best for | Dependencies | Sections selectable? |
|---|---|---|---|
| `terminal` | Interactive console use | Rich | Yes |
| `json` | CI pipelines, programmatic use | (stdlib only) | Yes |
| `markdown` | PRs, docs, wikis | (stdlib only) | Yes |
| `web` | Visual exploration, presentations | Streamlit, pandas | No (all shown) |

---

## Requirements

- Python 3.10+
- Dependencies installed via `analyzer_setup_env.py` (Rich, PyYAML, Streamlit, pandas)
- Optional: git (for churn metrics and `.gitignore`-aware file discovery)

---

## Quick Test

```bash
# Setup
python3 codebase-analyzer/scripts/analyzer_setup_env.py

# Terminal output
codebase-analyzer/.codebase-analyzer-venv/bin/python codebase-analyzer/scripts/analyze.py --path . --output terminal

# Web dashboard
codebase-analyzer/.codebase-analyzer-venv/bin/python codebase-analyzer/scripts/analyze.py --path . --output web

# JSON export
codebase-analyzer/.codebase-analyzer-venv/bin/python codebase-analyzer/scripts/analyze.py --path . --output json > analysis.json
```
