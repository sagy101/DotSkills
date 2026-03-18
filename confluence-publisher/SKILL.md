---
name: confluence-publisher
description: >
  Publish, sync, diff, delete, discover, and export markdown documentation to/from Confluence Cloud
  (*.atlassian.net/wiki/*). Use when the user asks to publish, update, delete, preview, diff, or
  export markdown files to Confluence, or when they want to verify existing Confluence pages against
  local docs. Also supports surgical HTML edits (targeted find/replace without overwriting manual
  formatting), version comparison (diff two page versions), version history browsing, and page
  revert. Handles page creation, updates, deletion, cross-page link rewriting, Mermaid diagram
  rendering, hierarchy verification, diff/preview, and reverse export to markdown.
license: MIT
metadata:
  author: sagy101
  version: "3.0"
compatibility: >
  Requires Python 3.10+. Optional: Node.js + npx for Mermaid diagram rendering.
  Works with Confluence Cloud (Atlassian). Requires API token with page read/write permissions.
---

# Confluence Publisher

Publish a tree of markdown files to Confluence Cloud, maintaining hierarchy, cross-page links, and embedded diagrams.

## When to use this skill

Use this skill when the user wants to:
- Publish one or more markdown files to Confluence
- Update existing Confluence pages from local markdown
- Delete Confluence pages (by manifest file key or page ID)
- Verify that Confluence pages match local docs (hierarchy, titles, content)
- Discover existing Confluence pages and build a local manifest
- Validate that a manifest is consistent with both disk and Confluence
- Apply targeted edits to a Confluence page without overwriting manual formatting (surgical edit)
- Compare two versions of a Confluence page (version diff)
- Browse page version history or fetch content from a specific version
- Revert a page to a previous version

## Prerequisites

Before running any publish operation, ensure:

1. **Config**: `.confluence.json` in project root and/or `~/.confluence.json` for global defaults (see [CONFIG.md](references/CONFIG.md))
2. **Credentials**: `CONFLUENCE_EMAIL` and `CONFLUENCE_TOKEN` exported in shell profile (recommended) or in a `.env` file
3. **Python deps**: installed via `confluence_setup_env.py` (shared venv in skill dir)

Config is auto-discovered — scripts search CWD upward, then `~/.confluence.json`. If both exist, they are deep-merged (project-level wins). No `--config` flag needed.

If no config is found anywhere, help the user create one. For users with one Atlassian instance, a global `~/.confluence.json` covers the shared settings:

```json
{
  "confluence_url": "https://mycompany.atlassian.net/wiki",
  "credentials": { "username_env": "CONFLUENCE_EMAIL", "token_env": "CONFLUENCE_TOKEN" }
}
```

Then a minimal per-project `.confluence.json` only needs:
```json
{
  "space_key": "DOCS",
  "root_page_id": "123456"
}
```

If `.confluence.json` does not exist anywhere, help the user create one by asking for:
- Confluence base URL (e.g. `https://mycompany.atlassian.net/wiki`)
- Space key
- Root page ID (the parent page under which all docs live)
- Which directory contains the markdown files (default: project root)

## Configuration

Config is loaded from `.confluence.json` (project root) and/or `~/.confluence.json` (global). If both exist, they are deep-merged (project-level wins). See [references/CONFIG.md](references/CONFIG.md) for the full schema.

Full single-file example:

```json
{
  "confluence_url": "https://mycompany.atlassian.net/wiki",
  "space_key": "DOCS",
  "root_page_id": "123456",
  "docs_dir": ".",
  "credentials": {
    "username_env": "CONFLUENCE_EMAIL",
    "token_env": "CONFLUENCE_TOKEN"
  }
}
```

## Pre-flight checks

Before running ANY script, perform these checks proactively. Do not wait for a script to fail.

### Check 1 — Python environment

Verify Python 3.10+ is available:

```bash
python3 --version
```

Check if the shared virtual environment already exists and has dependencies installed:

```bash
<skill_dir>/.venv/bin/python -c "import atlassian, markdown; print('OK')"
```

If the venv does not exist or dependencies are missing, run the setup script:

```bash
python3 <skill_dir>/scripts/confluence_setup_env.py
```

This creates a shared virtual environment at `<skill_dir>/.venv/` (one venv for all projects). If it fails, tell the user exactly what is missing and how to install it (e.g. `brew install python3` on macOS, `apt install python3` on Linux).

After setup, all subsequent script commands must use the venv Python:

```bash
<skill_dir>/.venv/bin/python <skill_dir>/scripts/publish_page.py ...
```

### Check 2 — Configuration file

Scripts auto-discover config by searching CWD upward, then `~/.confluence.json`. No `--config` flag needed.

If no config is found anywhere, do NOT proceed — instead help the user create one. For users with one Atlassian instance, suggest a global `~/.confluence.json` with shared settings (URL, credentials) and a per-project `.confluence.json` with just `space_key` and `root_page_id`.

Write the file(s) and confirm with the user before proceeding.

### Check 3 — Credentials

Confirm the credential environment variables are set. Run:

```bash
python3 -c "import os; print('email:', 'SET' if os.environ.get('CONFLUENCE_EMAIL') else 'MISSING'); print('token:', 'SET' if os.environ.get('CONFLUENCE_TOKEN') else 'MISSING')"
```

Substitute the actual env var names from `.confluence.json`. Never print values. If missing, advise the user to set them globally in their shell profile (recommended):
- **zsh** (macOS default): `echo 'export CONFLUENCE_TOKEN="<value>"' >> ~/.zshrc && source ~/.zshrc`
- **bash**: `echo 'export CONFLUENCE_TOKEN="<value>"' >> ~/.bashrc && source ~/.bashrc`
- **fish**: `set -Ux CONFLUENCE_TOKEN '<value>'`

### Check 4 — Connectivity (optional)

If this is the first publish or the user reports auth issues, test the connection:

```bash
<skill_dir>/.venv/bin/python <skill_dir>/scripts/validate_manifest.py
```

A `401` means bad credentials. A `404` on the root page means wrong `root_page_id`.

## Workflow

Always follow this sequence. Never skip the pre-flight checks or the publish plan step.

### Step 1 — Validate configuration

Run pre-flight checks above. Confirm all required fields are present. Confirm the credential environment variables are set (do NOT print their values).

### Step 2 — Determine scope

Ask the user (or infer from their request) which files to publish:
- **All**: every `.md` file under `docs_dir`
- **Changed**: files modified since last publish (check git diff or timestamps)
- **Specific**: a list of files the user names

### Step 3 — Build the publish plan

For each file in scope, determine whether it is a **create** or **update** by checking the manifest (`.confluence-manifest.json`). If no manifest exists, treat all files as creates.

Present the plan to the user in this exact format (see [references/PUBLISH_PLAN_FORMAT.md](references/PUBLISH_PLAN_FORMAT.md)):

```
╔══════════════════════════════════════════════════════════════╗
║                   CONFLUENCE PUBLISH PLAN                    ║
╠══════════════════════════════════════════════════════════════╣
║ Target: https://mycompany.atlassian.net/wiki                 ║
║ Space:  DOCS                                                 ║
║ Root:   "My Project Docs" (id=123456)                        ║
╠══════════════════════════════════════════════════════════════╣
║ #  │ Action │ File                    │ Title                 ║
║────┼────────┼─────────────────────────┼───────────────────────║
║  1 │ UPDATE │ README.md               │ My Project Docs       ║
║  2 │ CREATE │ plan/README.md          │ Design & Plan         ║
║  3 │ UPDATE │ plan/architecture.md    │ Architecture          ║
╠══════════════════════════════════════════════════════════════╣
║ Creates: 1  │  Updates: 2  │  Skipped: 0  │  Total: 3        ║
╚══════════════════════════════════════════════════════════════╝
```

**Wait for explicit user approval before proceeding.** If the user asks to change titles, parent pages, or skip files, update the plan and present it again.

### Step 4 — Execute

Run the publish script for each file in hierarchical order (parents before children):

```bash
<skill_dir>/.venv/bin/python <skill_dir>/scripts/publish_page.py \
  --file <relative_path> \
  --title "<title>" \
  --mode <create|update> \
  [--page-id <id>]        # for updates, from manifest \
  [--parent-id <id>]      # for creates, from manifest or root_page_id \
  [--emoji <codepoint>]   # page icon emoji, e.g. 1f399 for 🎙️
```

The script automatically:
- Converts markdown to Confluence storage format
- Renders Mermaid diagrams to PNG and uploads as attachments
- Rewrites `.md` cross-links to Confluence page-link macros using the manifest
- Converts `attachment:` links to Confluence attachment macros
- Sets the page emoji icon (if `--emoji` is provided)
- Updates the manifest with the resulting page ID

### Step 5 — Verify (optional but recommended)

After publishing, offer to run verification:

```bash
# Validate manifest entries against disk and Confluence
<skill_dir>/.venv/bin/python <skill_dir>/scripts/validate_manifest.py

# Show the full page tree on Confluence
<skill_dir>/.venv/bin/python <skill_dir>/scripts/verify_hierarchy.py
```

## Other operations

### Discover existing pages

If the user already has pages on Confluence and wants to build a manifest from them:

```bash
<skill_dir>/.venv/bin/python <skill_dir>/scripts/discover_pages.py
```

This walks the Confluence tree under `root_page_id` and creates `.confluence-manifest.json`.

### Diff / Preview

Compare local markdown against what is currently on Confluence **without publishing**.

The diff normalizes both sides to the same representation before comparing:
1. Local markdown is transformed through the publish pipeline (mermaid blocks → placeholders, `.md` links → Confluence link macros) to produce Confluence storage HTML
2. Remote Confluence page storage HTML is fetched and mermaid image macros are replaced with matching placeholders
3. Both HTML strings are converted to markdown via `markdownify`
4. A unified diff is produced from the two normalized markdown strings

This eliminates false positives from mermaid diagrams and cross-page links. Minor whitespace differences may still appear due to round-trip formatting.

```bash
# Diff a single file
<skill_dir>/.venv/bin/python <skill_dir>/scripts/diff_pages.py --file README.md

# Diff all manifest entries
<skill_dir>/.venv/bin/python <skill_dir>/scripts/diff_pages.py --all

# Summary only (changed/unchanged counts, no full diff)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/diff_pages.py --all --summary

# Save diff output to file (avoids terminal truncation for large pages)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/diff_pages.py --file README.md --output /tmp/diff-report.txt
```

**Note:** The diff script exits with code 1 if any changes or new pages are detected, and code 0 if everything is unchanged. This is informational (like the `diff` command), not an error — do not treat exit code 1 as a failure.

**Output truncation:** For large pages, the diff output may exceed the terminal/tool output limit and get truncated. Use `--output /tmp/diff-report.txt` to save to a file, then read it with your file-reading tool.

Present the diff output to the user before publishing so they can review what would change.

### Export from Confluence

Pull Confluence pages back into local markdown files (reverse sync). Useful for bootstrapping local docs from an existing Confluence space, or for recovering content.

```bash
# Export a single page by ID, URL, or tiny link
<skill_dir>/.venv/bin/python <skill_dir>/scripts/export_pages.py \
    --page https://mycompany.atlassian.net/wiki/spaces/DOCS/pages/123456/My+Page

# Export using a Confluence tiny link (/wiki/x/...)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/export_pages.py \
    --page https://mycompany.atlassian.net/wiki/x/sYjwQ

# Export a single page to a specific file
<skill_dir>/.venv/bin/python <skill_dir>/scripts/export_pages.py --page 123456 -o docs/setup.md

# Export all manifest entries (overwrites local files)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/export_pages.py --manifest

# Export full tree under root_page_id (discovers and exports everything)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/export_pages.py --tree

# Dry run — show what would be exported without writing files
<skill_dir>/.venv/bin/python <skill_dir>/scripts/export_pages.py --tree --dry-run
```

When exporting the full tree, the script also updates the manifest with discovered pages.

**Always confirm with the user before running `--manifest` or `--tree` exports**, as they overwrite local files.

### Attachments

The publish script supports uploading file attachments alongside a page:

```bash
<skill_dir>/.venv/bin/python <skill_dir>/scripts/publish_page.py \
    --file docs/setup.md --title "Setup Guide" --mode update --page-id 123456 \
    --attachments "docs/images/diagram.png,docs/files/schema.pdf"
```

Attachment paths are relative to `docs_dir`. Multiple files are comma-separated. If an attachment file is not found, a warning is printed but the page publish still succeeds.

Mermaid diagram PNGs are uploaded automatically — no need to list them in `--attachments`.

### Attachment links in markdown

To link to an uploaded attachment from within the page content, use the `attachment:` URL scheme:

```markdown
[My Presentation.pdf](attachment:My Presentation.pdf)
[Architecture Diagram](attachment:arch-overview.png)
```

During publish, these are automatically converted to Confluence `<ac:link><ri:attachment …/></ac:link>` macros that link directly to the attachment on the page.

The filename in `attachment:` must exactly match the filename used in `--attachments` (or the name of a previously uploaded attachment on the page).

### Delete pages

Remove Confluence pages and their manifest entries. Supports deletion by manifest file key or direct page ID.

```bash
# Delete by manifest file path
<skill_dir>/.venv/bin/python <skill_dir>/scripts/delete_page.py --file plan/old-design.md

# Delete multiple files
<skill_dir>/.venv/bin/python <skill_dir>/scripts/delete_page.py \
    --file "plan/old-design.md,plan/deprecated.md"

# Delete by page ID (not in manifest)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/delete_page.py --page-id 123456

# Dry run — show what would be deleted without deleting
<skill_dir>/.venv/bin/python <skill_dir>/scripts/delete_page.py --file plan/old-design.md --dry-run
```

**Never run delete without explicit user approval.** Before executing, list every page that will be deleted (title and ID) and wait for the user to confirm. Deletion is irreversible unless the page is recovered from Confluence trash. When in doubt, use `--dry-run` first.

### Validate only

```bash
<skill_dir>/.venv/bin/python <skill_dir>/scripts/validate_manifest.py
```

### Verify hierarchy only

```bash
<skill_dir>/.venv/bin/python <skill_dir>/scripts/verify_hierarchy.py
```

## Important rules

1. **Never publish or delete without showing the plan first and getting explicit user approval.** Deletion is destructive and irreversible (except via Confluence trash recovery).
2. **Never print or log credentials.** Only confirm that the environment variables are set.
3. **Publish parents before children** so that parent IDs are available for child creation.
4. The manifest file (`.confluence-manifest.json`) is auto-maintained by scripts. Do not edit it manually.
5. If a page create fails, stop and report the error — do not continue with children of that page.
6. Cross-page links are best-effort: if a target page is not in the manifest, the link is left as-is.
7. **Always use `--dry-run` before surgical edits.** Review the semantic diff and section integrity check before pushing.
8. **Never revert a page without showing the dry-run plan first** and getting explicit user approval. Revert creates a new version — the old version remains in history.
9. When using surgical edit, prefer `--check-sections` to verify critical content survived the edit.
10. **Never use `grep` or `cat` on fetched Confluence HTML files** — they are single-line files that will truncate in the terminal and produce unreadable output. Instead, save to a file with `--output` and read it using your IDE's file-reading tool, or write a small Python script to extract the specific section you need (e.g., find a table between two headings).

## Markdown transformation details

The publish script performs these transformations automatically:

- **Markdown → Confluence storage format**: Headings, tables, lists, inline code, bold/italic all convert to Confluence XHTML
- **Code blocks → Confluence code macros**: Fenced code blocks with language tags become `<ac:structured-macro ac:name="code">` with proper language highlighting
- **Mermaid diagrams → PNG attachments**: ` ```mermaid ` blocks are rendered to PNG via `mmdc` (Mermaid CLI), uploaded as page attachments, and replaced with `<ac:image>` macros. If Node.js/npx is unavailable, diagrams fall back to plain code blocks (no failure)
- **Cross-page links → Confluence page links**: Links like `[Setup Guide](./setup.md)` are resolved via the manifest and rewritten to `<ac:link>` macros pointing to the correct Confluence page by title. Unresolvable links (target not in manifest) are left as-is
- **Attachment links → Confluence attachment macros**: Links using the `attachment:` scheme (e.g. `[Slides](attachment:slides.pdf)`) are converted to `<ac:link><ri:attachment …/></ac:link>` macros

### Surgical edit

Apply targeted find/replace edits to a Confluence page's storage HTML without overwriting the entire page. Preserves manual formatting in untouched sections. **No markdown conversion** — operates directly on Confluence storage HTML.

```bash
# Inline single replacement
<skill_dir>/.venv/bin/python <skill_dir>/scripts/surgical_edit.py \
    --page 1079706804 --find "old text" --replace "new text"

# Replace all occurrences (default: first only)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/surgical_edit.py \
    --page 1079706804 --find "old" --replace "new" --replace-all

# Apply multiple replacements from a JSON file
<skill_dir>/.venv/bin/python <skill_dir>/scripts/surgical_edit.py \
    --page 1079706804 --replacements edits.json

# Dry run — show diff without pushing changes
<skill_dir>/.venv/bin/python <skill_dir>/scripts/surgical_edit.py \
    --page 1079706804 --replacements edits.json --dry-run

# Save diff report to file and verify sections survived
<skill_dir>/.venv/bin/python <skill_dir>/scripts/surgical_edit.py \
    --page 1079706804 --replacements edits.json \
    --output /tmp/report.txt \
    --check-sections "Problem Definition,Solution Architecture"
```

Replacements JSON format:
```json
[
    {"find": "old text 1", "replace": "new text 1"},
    {"find": "old text 2", "replace": "new text 2", "replace_all": true}
]
```

The `--page` argument accepts a numeric page ID, a full Confluence URL, or a tiny link.

**Always use `--dry-run` first** to verify the replacements before pushing. The script shows a semantic diff report and section integrity check.

#### Large structural changes (tables, sections)

For complex edits like adding a table column or restructuring a section, use `replace_element.py`:

```bash
# Extract: save the table after "Implementation Phases" to a file
<skill_dir>/.venv/bin/python <skill_dir>/scripts/replace_element.py \
    --page 1079706804 --heading "Implementation Phases" --element table \
    --output /tmp/table.html

# (modify /tmp/table.html → /tmp/table-new.html)

# Preview changes (always dry-run first)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/replace_element.py \
    --page 1079706804 --old /tmp/table.html --new /tmp/table-new.html --dry-run

# Apply after user approval
<skill_dir>/.venv/bin/python <skill_dir>/scripts/replace_element.py \
    --page 1079706804 --old /tmp/table.html --new /tmp/table-new.html \
    --message "Updated Implementation Phases table"
```

Supported `--element` types: `table`, `ul`, `ol`, `div`, `section` (heading + content until next same-level heading). Use `--nth 2` for the 2nd occurrence after the heading. Preserve existing `ac:local-id` attributes on unchanged elements; new elements don't need them.

### Diff page versions

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

### Page version management

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

## Future capabilities

These operations can be added to this skill in the future:

| Capability | Description |
|---|---|
| **Bulk rename** | Rename Confluence pages when local titles change |
| **Labels/tags** | Auto-apply Confluence labels based on directory structure or markdown frontmatter |
| **Page permissions** | Set view/edit restrictions on published pages |
| **Content appearance** | Set page width (full-width vs default) via content properties |

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `python3: command not found` | Python not installed | macOS: `brew install python3` / Linux: `apt install python3` |
| `ModuleNotFoundError: atlassian` | Dependencies not installed | Run `python3 <skill_dir>/scripts/confluence_setup_env.py` |
| `401 Unauthorized` | Bad credentials | Verify env vars are set and token has page write access |
| `404 Page not found` | Wrong page ID in manifest | Run `discover_pages.py` to rebuild manifest |
| `Title conflict` | Page title already exists in space | Use a unique title or update the existing page |
| Mermaid diagrams not rendering | Node.js/npx not installed | Install Node.js or diagrams will fall back to code blocks |
