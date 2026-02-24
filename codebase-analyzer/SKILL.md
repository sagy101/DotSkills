---
name: codebase-analyzer
description: >
  Analyze any codebase to produce structured metrics: line counts by category (code, tests, docs,
  scripts, plans), language breakdown, comment analysis, test:code ratio, file-size distribution,
  TODO/FIXME tracking, and git churn hotspots. Use when the user asks to analyze a codebase,
  get code statistics, understand project structure or size, check test coverage ratios,
  find TODOs, see language breakdown, identify large files, or review git churn.
  Outputs in terminal (Rich), JSON, or Markdown format. Configurable via YAML.
license: MIT
metadata:
  author: sagy101
  version: "1.0"
compatibility: >
  Requires Python 3.10+. Optional: git (for churn metrics and git-tracked file discovery).
  Works on any codebase — no external services or credentials required.
---

# Codebase Analyzer

Analyze any codebase and produce structured metrics with configurable patterns and multiple output formats.

## When to use this skill

Use this skill when the user wants to:
- Analyze a codebase for size, structure, and quality metrics
- Get line counts broken down by category (code, tests, docs, scripts, plans)
- See a language breakdown with code and comment lines per language
- Check the test:code ratio
- Find TODO and FIXME annotations across the codebase
- Identify large files that may need refactoring
- Review git churn hotspots (most frequently changed files)
- Export analysis results as JSON or Markdown for docs, PRs, or CI pipelines

## Prerequisites

Before running any analysis, ensure:

1. **Python 3.10+** is available
2. Dependencies are installed via the setup script
3. (Optional) **git** is installed if the user wants churn metrics or git-tracked file discovery

No external services, API tokens, or credentials are required. This skill is entirely local and read-only.

## Configuration

Configuration is **optional**. The analyzer works out of the box with sensible defaults. To customize, create a `.codebase-analysis.yaml` file in the repository root. See [references/CONFIG.md](references/CONFIG.md) for the full schema.

If no config file exists, do NOT prompt the user to create one — just proceed with defaults. Only mention the config file if the user wants to customize patterns.

To provide a starting config template, copy the default:

```bash
cp <skill_dir>/assets/default-config.yaml <repo_root>/.codebase-analysis.yaml
```

## Pre-flight checks

Before running ANY script, perform these checks proactively.

### Check 1 — Python environment

Verify Python 3.10+ is available:

```bash
python3 --version
```

Check if the virtual environment already exists and has dependencies installed:

```bash
<skill_dir>/.codebase-analyzer-venv/bin/python -c "import yaml, rich; print('OK')"
```

If the venv does not exist or dependencies are missing, run the setup script:

```bash
python3 <skill_dir>/scripts/setup_env.py
```

This creates a virtual environment at `.codebase-analyzer-venv/` and installs all dependencies. If it fails, tell the user exactly what is missing and how to install it (e.g. `brew install python3` on macOS, `apt install python3` on Linux).

After setup, all subsequent script commands must use the venv Python:

```bash
<skill_dir>/.codebase-analyzer-venv/bin/python <skill_dir>/scripts/analyze.py --path . --output terminal
```

### Check 2 — Git availability (optional)

If the user wants churn metrics, verify git is available:

```bash
git --version
```

If git is not available, the analyzer still works — it walks the directory tree instead of using `git ls-files`, and churn metrics are silently skipped.

## Workflow

### Step 1 — Run pre-flight checks

Verify the Python environment is ready. Set up the venv if needed.

### Step 2 — Determine scope

Infer from the user's request:
- **Which path** to analyze (default: current working directory)
- **Which output format** they want: `terminal` (default), `json`, or `markdown`
- **Which sections** to include (default: all). Available sections: `summary`, `categories`, `languages`, `file-distribution`, `large-files`, `todos`, `churn`

### Step 3 — Run analysis

```bash
<skill_dir>/.codebase-analyzer-venv/bin/python <skill_dir>/scripts/analyze.py \
  --path <repo_root> \
  --output <terminal|json|markdown> \
  --sections <comma-separated-list-or-all>
```

Optional flags:
- `--config <path>` — path to a custom config file (default: `<repo_root>/.codebase-analysis.yaml`)

### Step 4 — Present results

- For **terminal** output, the script renders directly to the console
- For **json** output, capture stdout and present the structured data to the user, or pipe it to a file
- For **markdown** output, capture stdout and present it or write to a file for documentation

### Step 5 — Offer follow-up actions

After analysis, suggest relevant next steps:
- If test:code ratio is low: suggest areas that need more tests
- If there are many TODOs/FIXMEs: offer to list them with file locations
- If large files are found: suggest candidates for refactoring
- If the user wants to save results: offer JSON or Markdown export
- If the user wants to customize patterns: help create a `.codebase-analysis.yaml`

## Operations

### Full analysis (all sections)

```bash
<skill_dir>/.codebase-analyzer-venv/bin/python <skill_dir>/scripts/analyze.py \
  --path <repo_root> --output terminal
```

### Specific sections only

```bash
<skill_dir>/.codebase-analyzer-venv/bin/python <skill_dir>/scripts/analyze.py \
  --path <repo_root> --output terminal --sections summary,languages,todos
```

### JSON export (for CI or programmatic use)

```bash
<skill_dir>/.codebase-analyzer-venv/bin/python <skill_dir>/scripts/analyze.py \
  --path <repo_root> --output json > analysis.json
```

### Markdown report (for docs or PRs)

```bash
<skill_dir>/.codebase-analyzer-venv/bin/python <skill_dir>/scripts/analyze.py \
  --path <repo_root> --output markdown > ANALYSIS.md
```

### Custom config

```bash
<skill_dir>/.codebase-analyzer-venv/bin/python <skill_dir>/scripts/analyze.py \
  --path <repo_root> --config custom-config.yaml --output terminal
```

## Available sections

| Section | What it shows |
|---|---|
| `summary` | Total files, lines, code, comments, blanks, TODOs, FIXMEs, test:code ratio |
| `categories` | Code vs tests comparison table + all categories breakdown |
| `languages` | Language breakdown by file count, code lines, and comment lines |
| `file-distribution` | File size distribution in buckets (1-50, 51-100, ..., 1000+ lines) |
| `large-files` | Code files exceeding the configured threshold (default: 500 lines) |
| `todos` | Files with the most TODO/FIXME annotations |
| `churn` | Most frequently changed files from recent git history |

## Important rules

1. **This skill is read-only.** It never modifies user code, config files, or repository state.
2. **No credentials or external services required.** Everything runs locally.
3. **Config is optional.** Never block on missing config — defaults work for any codebase.
4. **Git is optional.** If unavailable, directory walking is used and churn is skipped silently.
5. **Present results clearly.** Use the output format the user prefers. Default to terminal for interactive use.

## Output format details

See [references/REPORT_FORMAT.md](references/REPORT_FORMAT.md) for sample outputs, section descriptions, and guidance on interpreting key metrics (test:code ratio thresholds, comment percentage guidelines, churn interpretation).

## Error handling

The scripts print descriptive error messages to stderr with fix instructions. Exit codes: 0 = success, 1 = dependency error, 2 = config/path error.

| Error | Cause | Fix |
|---|---|---|
| `python3: command not found` | Python not installed | macOS: `brew install python3` / Linux: `apt install python3` |
| `ERROR: PyYAML is not installed` | Dependencies not installed | Run `python3 <skill_dir>/scripts/setup_env.py` then use the venv Python |
| `ERROR: Rich library is not installed` | Dependencies not installed | Run `python3 <skill_dir>/scripts/setup_env.py`, or use `--output json` / `--output markdown` which need no extra deps |
| `ERROR: Path does not exist` | Invalid `--path` argument | Verify the path exists |
| `ERROR: ... is a file, not a directory` | `--path` points to a file | Provide a directory path |
| `ERROR: Config file not found` | `--config` points to missing file | Fix the path or omit `--config` to use defaults |
| `ERROR: Invalid YAML in config file` | Syntax error in `.codebase-analysis.yaml` | Fix the YAML syntax or delete the file to use defaults |
| `ERROR: ... must contain a YAML mapping` | Config file has wrong structure | Config must be `key: value` pairs — see references/CONFIG.md |
| `WARNING: Config key '...' should be a list` | Config has wrong type for a pattern key | Use list syntax: `key: ["val1", "val2"]` |
| `WARNING: No files were analyzed` | All files skipped or directory empty | Check skip patterns in config; verify the directory has source files |
| No churn data | Not a git repo or git not installed | Expected behavior — churn requires git history |

## Future capabilities

| Capability | Description |
|---|---|
| **Snapshot comparison** | Diff two analysis runs to track codebase evolution over time |
| **CI integration** | Exit with non-zero code if metrics exceed configurable thresholds |
| **Custom language mappings** | Allow users to define additional file extension → language mappings in config |
| **Web dashboard** | Optional Streamlit-based visual dashboard for interactive exploration |
