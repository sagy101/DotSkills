# Confluence Publisher Skill — Design Document

> This document covers **why** this skill exists and the **key decisions** an implementer or reviewer needs to understand.

---

## Why This Skill Exists

Documentation lives in two places: local markdown files (version-controlled, developer-friendly) and Confluence (stakeholder-friendly, searchable, permissioned). Keeping them in sync is tedious — manual copy-paste leads to drift, lost formatting, broken links, and stale diagrams.

This skill gives **any SKILL.md-compatible agent** the ability to publish, sync, diff, and manage Confluence pages directly from local markdown, treating the local repo as the source of truth.

---

## Capabilities

| Capability | Description |
|---|---|
| **Publish** | Push local markdown files to Confluence as pages, with automatic format conversion |
| **Update** | Sync changed files to existing Confluence pages via manifest mapping |
| **Delete** | Remove Confluence pages by manifest key or page ID (with approval gate) |
| **Diff / Preview** | Compare local markdown against live Confluence content without publishing |
| **Discover** | Walk an existing Confluence page tree and build a local manifest |
| **Export** | Pull Confluence pages back to local markdown (single page, manifest, or full tree) |
| **Surgical edit** | Targeted find/replace on Confluence storage HTML without overwriting the full page |
| **Version diff** | Compare two versions of the same Confluence page |
| **Version history** | Browse page versions, fetch content from a specific version |
| **Revert** | Restore a page to a previous version (non-destructive, creates new version) |
| **Cross-page links** | Automatic rewriting of `.md` links to Confluence page-link macros |
| **Mermaid diagrams** | Render ` ```mermaid ` blocks to PNG attachments with graceful fallback |
| **Attachments** | Upload file attachments alongside pages; `attachment:` link conversion |
| **Hierarchy verification** | Validate that the Confluence page tree matches the manifest structure |

---

## Key Design Decisions

**1. Local markdown as source of truth** — The repo owns the content. Confluence is a rendered view. Publish is a one-way push (local → Confluence), with export (Confluence → local) available for bootstrapping or recovery, not as a regular workflow.

**2. Manifest-driven state tracking** — `.confluence-manifest.json` maps local file paths to Confluence page IDs. This avoids title-based lookups (which break on renames), enables idempotent create-or-update logic, and lets the agent determine scope (what's new vs what's changed) without querying Confluence.

**3. Hierarchical publish order** — Parents are always published before children. This ensures parent page IDs exist when creating child pages. On failure, the skill stops immediately rather than creating orphaned children.

**4. Automatic transformation pipeline** — The publish script handles markdown → Confluence storage format, Mermaid → PNG attachments, cross-page link rewriting, and attachment link conversion in a single pass. The agent doesn't need to understand Confluence XHTML — it just points at a markdown file.

**5. Normalized diff for accurate comparison** — Diff doesn't compare raw markdown to raw HTML. Instead, both sides go through normalization: local markdown is converted through the publish pipeline, remote HTML is fetched, Mermaid image macros are replaced with placeholders, and both are converted to markdown via `markdownify`. This eliminates false positives from diagram re-renders and link rewrites.

**6. Surgical edit as a separate operation** — Full publish overwrites the entire page. For small targeted changes (fixing a typo, updating a date), surgical edit operates directly on Confluence storage HTML with find/replace, preserving manual formatting in untouched sections. This is critical when stakeholders have made formatting changes on Confluence that shouldn't be overwritten.

**7. Credentials via environment variables** — Never hardcoded, never logged. The config file (`.confluence.json`) stores only the *names* of the env vars, not the values. Pre-flight checks confirm they're set without printing them. Optional `.env` file support via the `env_file` config key (path-traversal protected — must resolve inside the project root). Environment variable names are validated against `[A-Za-z_][A-Za-z0-9_]*` to prevent shell injection in credential hints.

**8. Virtual environment isolation** — `confluence_setup_env.py` creates `.venv/` inside the skill directory (e.g., `confluence-publisher/.venv/`). The agent invokes scripts using the absolute path to the venv Python interpreter (e.g., `/path/to/confluence-publisher/.venv/bin/python`) — no shell activation required. This keeps the skill self-contained and works identically whether installed in the repo or synced to `~/.codeium/windsurf/skills/`.

**9. Config discovery with git root boundary** — `.confluence.json` is discovered by walking up from CWD, stopping at the nearest git root to avoid picking up configs from unrelated parent directories. Global config (`~/.confluence.json`) is merged underneath project-level config (project wins on conflict). An explicit `--config` flag overrides discovery entirely.

**10. Module structure** — `confluence_config.py` handles configuration loading, credential resolution, shell detection, and manifest I/O. `page_utils.py` contains page reference utilities (tiny link codec, page ID extraction, title resolution, child page pagination). All scripts share the same `--config` argument definition via `add_config_arg()` for consistency.

---

## Approval Gates

Every destructive or externally-visible action requires explicit user approval:

| Action | Approval Required | Mechanism |
|---|---|---|
| **Publish (create/update)** | Yes | Publish plan table shown first |
| **Delete pages** | Yes | Page list (title + ID) shown first |
| **Export (overwrite local)** | Yes | File list shown first |
| **Surgical edit (push)** | Yes | `--dry-run` diff shown first |
| **Revert** | Yes | Dry-run plan shown first |
| **Diff / preview** | No | Read-only, no side effects |
| **Discover / validate** | No | Read-only, no side effects |

---

## Cross-Page Link Rewriting

Markdown files reference each other with relative paths (`[Setup](./setup.md)`). Confluence doesn't understand these — it needs `<ac:link>` macros pointing to page titles.

The rewriting strategy:
1. During publish, scan for `.md` links in the content
2. Look up each target path in the manifest to find the Confluence page title
3. Replace with Confluence page-link macros
4. If a target isn't in the manifest (not yet published), leave the link as-is — best-effort, not a hard failure

This means publish order matters beyond just parent/child: ideally, referenced pages are published before pages that link to them, though the skill handles missing links gracefully.

---

## Mermaid Diagram Strategy

Mermaid diagrams in markdown (` ```mermaid ` blocks) can't render natively in Confluence. The strategy:

1. Detect Mermaid code blocks during publish
2. Render to PNG via `mmdc` (Mermaid CLI, requires Node.js/npx)
3. Upload PNG as a page attachment
4. Replace the code block with a Confluence `<ac:image>` macro pointing to the attachment
5. **Graceful fallback**: if Node.js isn't available, the diagram is left as a code block — no publish failure

During diff, Mermaid image macros on the remote side are replaced with placeholders matching the local Mermaid blocks, preventing false positives from re-renders.

---

## Risks at a Glance

| Risk | Severity | Mitigation |
|---|---|---|
| Overwriting stakeholder edits | High | Surgical edit for targeted changes; diff/preview before publish |
| Credential leakage | High | Env var indirection; never print values; pre-flight confirms set-not-content |
| Broken cross-page links | Medium | Manifest-based rewriting; best-effort on missing targets |
| Orphaned child pages | Medium | Hierarchical publish order; stop on parent failure |
| Accidental deletion | High | Dry-run default; explicit approval gate; pages recoverable from Confluence trash |
| Stale manifest | Medium | `validate_manifest.py` checks consistency; `discover_pages.py` rebuilds from Confluence |
| Mermaid render differences | Low | Normalized diff with placeholders; fallback to code blocks |

---

## References

- **Confluence REST API v2** — Storage format, page CRUD, attachments, content properties
- **markdownify** — HTML-to-markdown conversion for normalized diffs
- **mermaid-cli (mmdc)** — Mermaid diagram rendering to PNG

## Status

**Stable (v3.1)** — Full publish pipeline, surgical edit, version management, diff/export, and discovery operations implemented.
