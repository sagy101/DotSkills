# Configuration Reference

The codebase analyzer uses a YAML configuration file to customize analysis behavior. All settings are optional — sensible defaults are built in.

## Config file location

By default, the analyzer looks for `.codebase-analysis.yaml` in the repository root. Override with `--config <path>`.

## Full schema

```yaml
# Directories that indicate test code
test_patterns:
  - tests
  - test
  - e2e
  - __tests__
  - spec

# File name globs that indicate test files (regardless of directory)
test_file_patterns:
  - "*.test.*"
  - "test_*.*"
  - "*.spec.*"
  - "*.stories.*"

# Directories containing test fixtures / test data
test_data_patterns:
  - fixtures
  - testdata
  - __fixtures__
  - mocks

# Directories containing scripts / tooling
script_patterns:
  - scripts
  - bin
  - tools

# Directories containing plans / proposals / RFCs
plan_patterns:
  - plans
  - planning
  - rfcs
  - proposals
  - adrs

# File extensions treated as documentation
doc_extensions:
  - .md
  - .rst
  - .txt

# File extensions to skip entirely (binary / non-code assets)
skip_extensions:
  - .lock
  - .svg
  - .png
  - .jpg
  - .jpeg
  - .ico
  - .gif
  - .pdf
  - .woff
  - .woff2
  - .ttf
  - .eot
  - .webp
  - .mp4
  - .mp3

# Specific filenames to skip
skip_files:
  - pnpm-lock.yaml
  - package-lock.json
  - yarn.lock
  - uv.lock
  - .DS_Store

# Directories to skip entirely
skip_dirs:
  - node_modules
  - .git
  - dist
  - build
  - __pycache__
  - .next
  - .venv
  - venv
  - .codebase-analyzer-venv

# Files with more code lines than this are flagged as "large"
large_file_threshold: 500

# Number of top files to show in TODO and churn sections
top_files_count: 10
```

## Merging behavior

User config values **replace** defaults for the same key (they are not merged). For list fields like `skip_dirs`, your config replaces the entire default list. Include all entries you need.

## Minimal example

To only customize the large-file threshold and add a skip directory:

```yaml
large_file_threshold: 300
skip_dirs:
  - node_modules
  - .git
  - dist
  - build
  - __pycache__
  - .next
  - .venv
  - venv
  - .myproject-cache
```
