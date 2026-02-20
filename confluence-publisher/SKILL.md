---
name: confluence-publisher
description: >
  Publish, sync, diff, delete, discover, and export markdown documentation to/from Confluence Cloud.
  Use when the user asks to publish, update, delete, preview, diff, or export markdown files
  to Confluence, or when they want to verify existing Confluence pages against local
  docs. Handles page creation, updates, deletion, cross-page link rewriting, Mermaid diagram
  rendering, hierarchy verification, diff/preview, and reverse export to markdown.
license: MIT
metadata:
  author: sagy101
  version: "2.0"
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

## Prerequisites

Before running any publish operation, ensure:

1. A **project config file** exists at `.confluence.json` in the project root (see [CONFIG.md](references/CONFIG.md) for format)
2. **Credentials** are available as environment variables (names configured in `.confluence.json`)
3. Python dependencies are installed: `pip install -r <skill_dir>/scripts/requirements.txt`

If `.confluence.json` does not exist, help the user create one by asking for:
- Confluence base URL (e.g. `https://mycompany.atlassian.net/wiki`)
- Space key
- Root page ID (the parent page under which all docs live)
- Which directory contains the markdown files (default: project root)
- Environment variable names for credentials (default: `CONFLUENCE_EMAIL`, `CONFLUENCE_TOKEN`)

## Configuration

The project must contain a `.confluence.json` file. See [references/CONFIG.md](references/CONFIG.md) for the full schema. Minimal example:

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

Verify Python 3.10+ is available and dependencies are installed:

```bash
python3 --version
python3 -c "import atlassian, markdown; print('OK')"
```

If Python is missing or dependencies are not installed, run the setup script:

```bash
python3 <skill_dir>/scripts/setup_env.py
```

This creates a virtual environment at `.confluence-venv/` and installs all dependencies. If it fails, tell the user exactly what is missing and how to install it (e.g. `brew install python3` on macOS, `apt install python3` on Linux).

After setup, all subsequent script commands should use the venv Python:

```bash
.confluence-venv/bin/python <skill_dir>/scripts/publish_page.py ...
```

### Check 2 — Configuration file

Look for `.confluence.json` in the project root. If missing, do NOT proceed — instead help the user create one interactively by asking for:
- Confluence base URL (e.g. `https://mycompany.atlassian.net/wiki`)
- Space key
- Root page ID
- Docs directory (default `.`)
- Credential env var names (defaults: `CONFLUENCE_EMAIL`, `CONFLUENCE_TOKEN`)
- Path to `.env` file if they use one

Write the file and confirm it with the user before proceeding.

### Check 3 — Credentials

Confirm the credential environment variables are set. Run:

```bash
python3 -c "import os; print('email:', 'SET' if os.environ.get('CONFLUENCE_EMAIL') else 'MISSING'); print('token:', 'SET' if os.environ.get('CONFLUENCE_TOKEN') else 'MISSING')"
```

Substitute the actual env var names from `.confluence.json`. If credentials load from an `.env` file, check that the file exists and contains the expected keys (without printing values). If anything is missing, tell the user which variable to set and where.

### Check 4 — Connectivity (optional)

If this is the first publish or the user reports auth issues, test the connection:

```bash
python3 <skill_dir>/scripts/validate_manifest.py --config .confluence.json
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
.confluence-venv/bin/python <skill_dir>/scripts/publish_page.py \
  --config .confluence.json \
  --file <relative_path> \
  --title "<title>" \
  --mode <create|update> \
  [--page-id <id>]        # for updates, from manifest \
  [--parent-id <id>]      # for creates, from manifest or root_page_id
```

The script automatically:
- Converts markdown to Confluence storage format
- Renders Mermaid diagrams to PNG and uploads as attachments
- Rewrites `.md` cross-links to Confluence page-link macros using the manifest
- Updates the manifest with the resulting page ID

### Step 5 — Verify (optional but recommended)

After publishing, offer to run verification:

```bash
# Validate manifest entries against disk and Confluence
python <skill_dir>/scripts/validate_manifest.py --config .confluence.json

# Show the full page tree on Confluence
python <skill_dir>/scripts/verify_hierarchy.py --config .confluence.json
```

## Other operations

### Discover existing pages

If the user already has pages on Confluence and wants to build a manifest from them:

```bash
python <skill_dir>/scripts/discover_pages.py --config .confluence.json
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
python <skill_dir>/scripts/diff_pages.py --config .confluence.json --file README.md

# Diff all manifest entries
python <skill_dir>/scripts/diff_pages.py --config .confluence.json --all

# Summary only (changed/unchanged counts, no full diff)
python <skill_dir>/scripts/diff_pages.py --config .confluence.json --all --summary
```

Present the diff output to the user before publishing so they can review what would change.

### Export from Confluence

Pull Confluence pages back into local markdown files (reverse sync). Useful for bootstrapping local docs from an existing Confluence space, or for recovering content.

```bash
# Export a single page by ID or URL
python <skill_dir>/scripts/export_pages.py --config .confluence.json \
    --page https://mycompany.atlassian.net/wiki/spaces/DOCS/pages/123456/My+Page

# Export a single page to a specific file
python <skill_dir>/scripts/export_pages.py --config .confluence.json --page 123456 -o docs/setup.md

# Export all manifest entries (overwrites local files)
python <skill_dir>/scripts/export_pages.py --config .confluence.json --manifest

# Export full tree under root_page_id (discovers and exports everything)
python <skill_dir>/scripts/export_pages.py --config .confluence.json --tree

# Dry run — show what would be exported without writing files
python <skill_dir>/scripts/export_pages.py --config .confluence.json --tree --dry-run
```

When exporting the full tree, the script also updates the manifest with discovered pages.

**Always confirm with the user before running `--manifest` or `--tree` exports**, as they overwrite local files.

### Attachments

The publish script supports uploading file attachments alongside a page:

```bash
python <skill_dir>/scripts/publish_page.py --config .confluence.json \
    --file docs/setup.md --title "Setup Guide" --mode update --page-id 123456 \
    --attachments "docs/images/diagram.png,docs/files/schema.pdf"
```

Attachment paths are relative to `docs_dir`. Multiple files are comma-separated. If an attachment file is not found, a warning is printed but the page publish still succeeds.

Mermaid diagram PNGs are uploaded automatically — no need to list them in `--attachments`.

### Delete pages

Remove Confluence pages and their manifest entries. Supports deletion by manifest file key or direct page ID.

```bash
# Delete by manifest file path
python <skill_dir>/scripts/delete_page.py --config .confluence.json --file plan/old-design.md

# Delete multiple files
python <skill_dir>/scripts/delete_page.py --config .confluence.json \
    --file "plan/old-design.md,plan/deprecated.md"

# Delete by page ID (not in manifest)
python <skill_dir>/scripts/delete_page.py --config .confluence.json --page-id 123456

# Dry run — show what would be deleted without deleting
python <skill_dir>/scripts/delete_page.py --config .confluence.json --file plan/old-design.md --dry-run
```

**Never run delete without explicit user approval.** Before executing, list every page that will be deleted (title and ID) and wait for the user to confirm. Deletion is irreversible unless the page is recovered from Confluence trash. When in doubt, use `--dry-run` first.

### Validate only

```bash
python <skill_dir>/scripts/validate_manifest.py --config .confluence.json
```

### Verify hierarchy only

```bash
python <skill_dir>/scripts/verify_hierarchy.py --config .confluence.json
```

## Important rules

1. **Never publish or delete without showing the plan first and getting explicit user approval.** Deletion is destructive and irreversible (except via Confluence trash recovery).
2. **Never print or log credentials.** Only confirm that the environment variables are set.
3. **Publish parents before children** so that parent IDs are available for child creation.
4. The manifest file (`.confluence-manifest.json`) is auto-maintained by scripts. Do not edit it manually.
5. If a page create fails, stop and report the error — do not continue with children of that page.
6. Cross-page links are best-effort: if a target page is not in the manifest, the link is left as-is.

## Markdown transformation details

The publish script performs these transformations automatically:

- **Markdown → Confluence storage format**: Headings, tables, lists, inline code, bold/italic all convert to Confluence XHTML
- **Code blocks → Confluence code macros**: Fenced code blocks with language tags become `<ac:structured-macro ac:name="code">` with proper language highlighting
- **Mermaid diagrams → PNG attachments**: ` ```mermaid ` blocks are rendered to PNG via `mmdc` (Mermaid CLI), uploaded as page attachments, and replaced with `<ac:image>` macros. If Node.js/npx is unavailable, diagrams fall back to plain code blocks (no failure)
- **Cross-page links → Confluence page links**: Links like `[Setup Guide](./setup.md)` are resolved via the manifest and rewritten to `<ac:link>` macros pointing to the correct Confluence page by title. Unresolvable links (target not in manifest) are left as-is

## Future capabilities

These operations can be added to this skill in the future:

| Capability | Description |
|---|---|
| **Bulk rename** | Rename Confluence pages when local titles change |
| **Labels/tags** | Auto-apply Confluence labels based on directory structure or markdown frontmatter |
| **Page permissions** | Set view/edit restrictions on published pages |

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `python3: command not found` | Python not installed | macOS: `brew install python3` / Linux: `apt install python3` |
| `ModuleNotFoundError: atlassian` | Dependencies not installed | Run `python3 <skill_dir>/scripts/setup_env.py` |
| `401 Unauthorized` | Bad credentials | Verify env vars are set and token has page write access |
| `404 Page not found` | Wrong page ID in manifest | Run `discover_pages.py` to rebuild manifest |
| `Title conflict` | Page title already exists in space | Use a unique title or update the existing page |
| Mermaid diagrams not rendering | Node.js/npx not installed | Install Node.js or diagrams will fall back to code blocks |
