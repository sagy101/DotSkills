---
name: codebase-analyzer
description: >
  Analyze any codebase to produce structured metrics: line counts by category (code, tests, docs,
  scripts, plans), language breakdown, comment analysis, test:code ratio, file-size distribution,
  TODO/FIXME tracking, and git churn hotspots. Use when the user asks to analyze a codebase,
  get code statistics, understand project structure or size, check test coverage ratios,
  find TODOs, see language breakdown, identify large files, or review git churn.
  Outputs in terminal (Rich), JSON, Markdown, or interactive web dashboard (Streamlit) format.
  Configurable via YAML.
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

If no config file exists, **ask the user if they would like to create one before running the analysis**. To help them decide:
1. Quickly inspect the codebase structure (top-level directories, common file types, presence of test/script/doc directories)
2. Suggest a tailored `.codebase-analysis.yaml` based on what you find — for example, if the repo has a `src/` directory with tests in `__tests__/`, or uses non-standard script directories, reflect that in the suggestion
3. Present the suggested config to the user and let them accept, modify, or skip it
4. If they skip, proceed with built-in defaults

To provide a starting config template, copy the default:

```bash
cp <skill_dir>/assets/default-config.yaml <repo_root>/.codebase-analysis.yaml
```

## Pre-flight checks

Before running ANY operation, run the preflight script once. It validates the entire environment in a single pass and reports a clear summary.

```bash
python3 <skill_dir>/scripts/analyzer_preflight.py
```

Optionally, pass `--path` to also validate the target repository:

```bash
python3 <skill_dir>/scripts/analyzer_preflight.py --path <repo_root>
```

The script checks:
1. **Python 3.10+** is available
2. **Virtual environment** exists at `<skill_dir>/.codebase-analyzer-venv/`
3. **Core dependencies** (PyYAML, Rich) are importable
4. **Web dependencies** (Streamlit, pandas) are importable
5. **git** is available (optional — always passes, reports status)
6. **Skill scripts** are all present
7. **Target path** exists and is a directory (only when `--path` is provided)
8. **Config file** presence in the target repo (optional — always passes, reports status)

If the venv does not exist or dependencies are missing, run the setup script:

```bash
python3 <skill_dir>/scripts/analyzer_setup_env.py
```

After setup, all subsequent script commands must use the venv Python:

```bash
<skill_dir>/.codebase-analyzer-venv/bin/python <skill_dir>/scripts/analyze.py --path . --output terminal
```

## Workflow

### Step 1 — Run pre-flight checks

Run the preflight script and read the output. If any required check fails, resolve it before proceeding.

```bash
python3 <skill_dir>/scripts/analyzer_preflight.py --path <repo_root>
```

### Step 2 — Ask about configuration

Check if a `.codebase-analysis.yaml` already exists in the repo root.

- **If it exists**, inform the user and proceed with it.
- **If it does not exist**, ask the user whether they want to create a custom config before running:
  1. Inspect the codebase: list top-level directories, identify test directories, script directories, doc files, and any non-standard project conventions
  2. Generate a suggested `.codebase-analysis.yaml` tailored to the codebase and present it to the user
  3. If the user accepts (with or without edits), write the config file to `<repo_root>/.codebase-analysis.yaml`
  4. If the user declines, proceed with built-in defaults

### Step 3 — Ask about output format

Ask the user which output format they prefer:
- **terminal** — Rich-formatted tables printed to the console (best for interactive use)
- **json** — structured JSON to stdout (best for CI pipelines or programmatic consumption)
- **markdown** — Markdown report to stdout (best for docs, PRs, or saving to a file)
- **web** — interactive Streamlit dashboard in the browser with charts, tables, and visual metrics

Also ask:
- **Which path** to analyze (default: current working directory)
- **Which sections** to include (default: all, not applicable for `web`). Available sections: `summary`, `categories`, `languages`, `file-distribution`, `large-files`, `todos`, `churn`

### Step 4 — Run analysis

```bash
<skill_dir>/.codebase-analyzer-venv/bin/python <skill_dir>/scripts/analyze.py \
  --path <repo_root> \
  --output <terminal|json|markdown|web> \
  --sections <comma-separated-list-or-all>
```

Optional flags:
- `--config <path>` — path to a custom config file (default: `<repo_root>/.codebase-analysis.yaml`)

**Note:** When `--output web` is used, the script launches a Streamlit server and opens the dashboard in the browser. The `--sections` flag is ignored for web output (all sections are always shown). The command is **non-blocking** — the server runs until the user stops it (Ctrl+C).

### Step 5 — Present results

- For **terminal** output, the script renders directly to the console
- For **json** output, capture stdout and present the structured data to the user, or pipe it to a file
- For **markdown** output, capture stdout and present it or write to a file for documentation
- For **web** output, the dashboard is already open in the browser — no further action needed

### Step 6 — Offer follow-up actions

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

### Web dashboard (interactive browser UI)

```bash
<skill_dir>/.codebase-analyzer-venv/bin/python <skill_dir>/scripts/analyze.py \
  --path <repo_root> --output web
```

This launches a Streamlit server and opens an interactive dashboard in the browser with:
- Overview metrics (files, lines, code, comments, test:code ratio, docs:code ratio)
- Code vs Tests comparison with charts
- Language breakdown with tabs (All Files / Code Only)
- File size distribution histogram
- Large files and TODO/FIXME tracking
- Category breakdown (code, tests, docs, scripts, plans, test data)

The dashboard caches analysis results for 60 seconds. Stop the server with Ctrl+C.

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
| `ERROR: PyYAML is not installed` | Dependencies not installed | Run `python3 <skill_dir>/scripts/analyzer_setup_env.py` then use the venv Python |
| `ERROR: Rich library is not installed` | Dependencies not installed | Run `python3 <skill_dir>/scripts/analyzer_setup_env.py`, or use `--output json` / `--output markdown` which need no extra deps |
| `ERROR: Streamlit is not installed` | Dependencies not installed | Run `python3 <skill_dir>/scripts/analyzer_setup_env.py` to install all dependencies including Streamlit |
| `ERROR: Path does not exist` | Invalid `--path` argument | Verify the path exists |
| `ERROR: ... is a file, not a directory` | `--path` points to a file | Provide a directory path |
| `ERROR: Config file not found` | `--config` points to missing file | Fix the path or omit `--config` to use defaults |
| `ERROR: Invalid YAML in config file` | Syntax error in `.codebase-analysis.yaml` | Fix the YAML syntax or delete the file to use defaults |
| `ERROR: ... must contain a YAML mapping` | Config file has wrong structure | Config must be `key: value` pairs — see references/CONFIG.md |
| `WARNING: Config key '...' should be a list` | Config has wrong type for a pattern key | Use list syntax: `key: ["val1", "val2"]` |
| `WARNING: No files were analyzed` | All files skipped or directory empty | Check skip patterns in config; verify the directory has source files |
| No churn data | Not a git repo or git not installed | Expected behavior — churn requires git history |

## Troubleshooting

| Problem | Fix |
|---|---|
| `python3: command not found` | macOS: `brew install python3` / Linux: `apt install python3` |
| Venv not found | Run `python3 <skill_dir>/scripts/analyzer_setup_env.py` to create it |
| Missing dependencies after setup | Delete the venv directory and re-run the setup script |
| `--output web` shows blank page | Ensure Streamlit is installed: check preflight output for web dependencies |
| No churn data in results | Expected if not a git repo or git is not installed |
| All files skipped / 0 files analyzed | Check `skip_dirs`, `skip_extensions`, `skip_files` in config; verify target directory has source files |
| Config changes not reflected | The web dashboard caches results for 60 seconds; wait or restart the server |

## Future capabilities

| Capability | Description |
|---|---|
| **Snapshot comparison** | Diff two analysis runs to track codebase evolution over time |
| **CI integration** | Exit with non-zero code if metrics exceed configurable thresholds |
| **Custom language mappings** | Allow users to define additional file extension → language mappings in config |
| ~~**Web dashboard**~~ | **Implemented** — use `--output web` to launch the Streamlit dashboard |
