# Report Format Reference

The analyzer supports three output formats, selectable via `--output`.

## Output formats

### Terminal (`--output terminal`)

Rich, colored tables rendered in the terminal using the Rich library. Best for interactive use.

### JSON (`--output json`)

Structured JSON to stdout. Useful for piping to other tools, CI/CD integration, or programmatic consumption by agents.

Example (summary section):

```json
{
  "repo": "/path/to/repo",
  "summary": {
    "total_files": 142,
    "total_lines": 28450,
    "total_code": 19200,
    "total_comments": 3100,
    "total_blank": 6150,
    "total_todos": 12,
    "total_fixmes": 3,
    "test_code_ratio": 0.65,
    "comment_pct": 16.1,
    "analysis_time": 1.23
  }
}
```

### Markdown (`--output markdown`)

Markdown tables suitable for embedding in pull requests, documentation pages, or wikis.

## Sections

Use `--sections` to select specific report sections (comma-separated) or `all` for everything.

| Section | Description |
|---|---|
| `summary` | Top-level metrics: files, lines, code, comments, TODOs, test:code ratio |
| `categories` | Breakdown by category (code, tests, docs, scripts, test_data, plans) with code-vs-tests comparison |
| `languages` | Language breakdown by file count, code lines, and comment lines |
| `file-distribution` | File size distribution in buckets (0-50, 51-100, ..., 1000+) |
| `large-files` | Code files exceeding the configured threshold |
| `todos` | Files with the most TODO/FIXME annotations |
| `churn` | Most frequently changed files (from recent git history) |

## Interpreting key metrics

### Test:Code Ratio

The ratio of test code lines to production code lines.

| Ratio | Assessment |
|---|---|
| >= 0.80 | Good — tests are well-represented |
| 0.50 – 0.79 | Fair — some coverage gaps likely |
| < 0.50 | Low — testing may be insufficient |

### Comment Percentage

Comment lines as a percentage of code lines (across the whole codebase).

| Range | Assessment |
|---|---|
| 10% – 25% | Healthy range for most projects |
| < 5% | May lack documentation |
| > 40% | Possibly over-commented or contains large docstrings |

### Large File Threshold

Files with more code lines than `large_file_threshold` (default: 500) are flagged. Large files often indicate candidates for refactoring or splitting.

### Git Churn

Files with the most commits in the last 500 commits. High-churn files may indicate:
- Hotspots that need refactoring
- Core files under active development
- Configuration files that change often (usually benign)
