# Version Management

Detailed usage for `diff_versions.py` and `page_versions.py`.

## Diff page versions (`diff_versions.py`)

Compare two versions of the same Confluence page to see exactly what changed. Strips Confluence noise attributes (`ac:local-id`, `local-id`, `data-table-width`) for clean comparison.

```bash
# Diff version 56 against latest
<skill_dir>/.venv/bin/python <skill_dir>/scripts/diff_versions.py \
    --page 1079706804 --from-version 56

# Diff two specific versions
<skill_dir>/.venv/bin/python <skill_dir>/scripts/diff_versions.py \
    --page 1079706804 --from-version 56 --to-version 59

# Save report to file (avoids terminal truncation)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/diff_versions.py \
    --page 1079706804 --from-version 56 --output /tmp/diff.txt

# Verify specific sections survived edits
<skill_dir>/.venv/bin/python <skill_dir>/scripts/diff_versions.py \
    --page 1079706804 --from-version 56 \
    --check-sections "Problem Definition,Risk & Mitigation"
```

The diff report includes:
- Per-change type (replace/insert/delete) with old and new text
- Section integrity check (auto-detects headings if `--check-sections` is omitted)
- HTML size comparison

Exit code 1 if changes found (like the `diff` command), 0 if identical.

## Page version management (`page_versions.py`)

Browse version history, fetch content from a specific version, or revert to a previous version.

```bash
# List version history
<skill_dir>/.venv/bin/python <skill_dir>/scripts/page_versions.py \
    --page 1079706804 --list

# List more versions
<skill_dir>/.venv/bin/python <skill_dir>/scripts/page_versions.py \
    --page 1079706804 --list --limit 50

# Fetch a specific version's HTML
<skill_dir>/.venv/bin/python <skill_dir>/scripts/page_versions.py \
    --page 1079706804 --fetch 56 --output /tmp/page_v56.html

# Fetch the latest version's HTML
<skill_dir>/.venv/bin/python <skill_dir>/scripts/page_versions.py \
    --page 1079706804 --fetch latest --output /tmp/page_latest.html

# Fetch as plain text (HTML tags stripped)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/page_versions.py \
    --page 1079706804 --fetch 56 --output /tmp/page_v56.txt --text

# Revert to a previous version (dry run first)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/page_versions.py \
    --page 1079706804 --revert 56

# Execute the revert (requires --confirm)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/page_versions.py \
    --page 1079706804 --revert 56 --confirm
```

**Revert is a non-destructive operation** — it creates a new version with the old content. The reverted-from version remains in history. **Never revert without showing the dry-run plan first and getting explicit user approval.**
