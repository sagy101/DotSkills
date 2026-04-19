# Jira Manager Skill — Design Document

> This document covers **why** this skill exists and the **key decisions** an implementer or reviewer needs to understand.

---

## Why This Skill Exists

Managing Jira tickets from an AI coding agent is common but fragile: agents hallucinate field names, guess at valid statuses, miss required fields, and produce broken markup. Most integrations are hardcoded to one project's workflow.

This skill gives **any SKILL.md-compatible agent** reliable Jira CRUD by combining **field discovery** (learn the project's actual schema) with **generic flags** (`--set`, `--filter`) that work across any Jira Cloud instance. The agent doesn't need to know the project's custom fields upfront — it discovers them.

---

## Capabilities

| Capability | Description |
|---|---|
| **Create tickets** | Single or bulk creation from markdown/JSON source files with dependency ordering |
| **Update tickets** | Modify fields, status, sprint, priority, assignee, parent, attachments, comments, and issue links on existing issues |
| **Bulk update** | Update multiple tickets by explicit list, board, JQL, or field filter |
| **Fetch tickets** | Query by key, JQL, field filter, parent, or Agile board (table/detail/JSON output) |
| **Project listing** | List projects visible to the authenticated Jira user |
| **Delete tickets** | Remove issues with dry-run preview and confirmation gate |
| **Diff** | Compare local ticket definitions against live Jira state |
| **Validate estimates** | Check that sub-ticket story point sums match parent estimates |
| **Field discovery** | Auto-discover statuses, priorities, components, versions, sprints, and custom fields |
| **Status transitions** | Move issues through workflow states via Jira's transition engine |
| **Markup conversion** | Automatic Markdown ↔ Jira wiki markup conversion for descriptions |
| **Image auto-attachment** | Local images in descriptions (`![alt](path)`) are extracted, rewritten to basenames for Jira wiki markup, and uploaded as attachments |
| **Mermaid rendering** | ` ```mermaid ` code blocks are rendered to PNG via mmdc, attached to the issue, and embedded as `!filename.png!` |
| **Link rewriting** | Convert relative markdown links to git browse URLs in ticket descriptions |
| **Comments** | Add comments to issues via `--comment` flag during update |
| **Comment management** | List, add, edit, and delete comments with dedicated issue comment commands |
| **Issue links** | Create typed links between issues (Blocks, Duplicate, Relates, etc.) via `--link` flag |
| **Remote links** | Fetch remote issue links for detail/JSON issue output when requested |
| **Board/sprint ops** | List Agile boards, fetch board issues, move issues between sprints |

---

## Key Design Decisions

**1. Discovery-first architecture** — Before creating or updating tickets, the agent runs `discover_fields.py --all --apply` to learn the project's statuses, priorities, components, versions, sprints, and custom fields. This populates `field_catalog` in `.jira.json`, which all other scripts reference. No hardcoded field IDs or status names.

**2. Generic `--set` and `--filter` flags** — Named flags cover common fields (`--status`, `--priority`, `--sprint`, `--parent`), but any field can be set or filtered via `--set "field=value"` and `--filter field=value`. This means the skill works with custom fields (story points, team, environment, etc.) without needing per-field flag definitions. The `parent` field is auto-wrapped as `{"key": "..."}` whether set via `--parent` or `--set "parent=KEY"`.

**3. Manifest-driven idempotency** — `.jira-manifest.json` maps local definitions (markdown sections or JSON entries) to Jira issue keys. Bulk create skips already-created tickets. Diff compares local definitions against live Jira state. This prevents duplicate creation on retry and enables incremental sync.

**4. Dependency-ordered creation** — Epics before stories, stories before subtasks. This mirrors Jira's hierarchy constraints: a subtask can't be created without a parent key, and a story's epic link needs the epic to exist. On failure, the skill stops immediately rather than creating orphaned issues.

**5. Status transitions via the Jira workflow engine** — Updating status isn't a simple field write — Jira requires finding the correct transition ID. The skill queries available transitions for the issue and matches by target status name. If no direct transition exists (e.g., can't go from "To Do" to "Done" without passing through "In Progress"), the error message says so rather than silently failing.

**6. Markdown ↔ Jira markup conversion** — Jira Cloud's REST API accepts Jira wiki markup, not markdown. The skill auto-converts descriptions during create/update (markdown → Jira markup) and during fetch/diff (Jira markup → markdown). `--no-convert` skips this for users who write Jira markup directly.

**6a. Image auto-attachment** — During create/update, `extract_local_images()` scans the raw markdown description for `![alt](local_path)` references (HTTP/HTTPS URLs are left as-is). Local paths are resolved relative to the description file's directory (or CWD for inline `--description`), rewritten to basenames so Jira's `!filename.png!` syntax matches the attachment, and the original files are uploaded via the attachments API after issue creation/update. Duplicate basenames are de-duplicated with `_N` suffixes. Missing files generate warnings but don’t block creation.

**6b. Mermaid diagram rendering** — Before image extraction, ` ```mermaid ` code blocks are detected via regex and rendered to PNG using `mmdc` (Mermaid CLI) or `npx @mermaid-js/mermaid-cli`. Rendered PNGs are placed in a temp directory and injected back into the markdown as absolute-path image references, which the downstream image extraction pipeline then picks up for basename rewriting and auto-attachment. If `mmdc`/`npx` is not available, blocks are left as code with a warning. Scale is 2x with transparent background.

**7. Link rewriting for traceability** — `--rewrite-links` converts relative markdown links in descriptions to full git browse URLs (e.g., `./src/auth.ts` → `https://github.com/org/repo/blob/main/src/auth.ts`). This gives Jira readers clickable links to source code without requiring Jira-GitHub integrations.

**8. Credentials via environment variables** — `.jira.json` stores env var *names*, not values. Pre-flight confirms they're set without printing them. Optional `.env` file support via the `env_file` config key (path-traversal protected — must resolve inside the project root). Environment variable names are validated against `[A-Za-z_][A-Za-z0-9_]*` to prevent shell injection in credential hints. Shell-specific hints are generated for zsh, bash, fish, PowerShell, and cmd.

**9. Dynamically discovered issue link types** — Link types (Blocks, Duplicate, Cloners, Relates, etc.) are fetched at runtime from `GET /rest/api/2/issueLinkType`, not hardcoded. The `--link` flag accepts the link type name, its inward label (e.g., "is blocked by"), or its outward label (e.g., "blocks") and resolves against the live list. Direction is automatically swapped when an inward label is used: `--link "is blocked by:API-456"` creates the link with API-456 as the blocker.

**10. Virtual environment isolation** — `jira_setup_env.py` creates `.venv/` inside the skill directory (e.g., `jira-manager/.venv/`). The agent invokes scripts using the absolute path to the venv Python interpreter (e.g., `/path/to/jira-manager/.venv/bin/python`) — no shell activation required. This keeps the skill self-contained and works identically whether installed in the repo or synced to `~/.codeium/windsurf/skills/`.

**11. Required field pre-validation via create_meta** — `discover_fields.py --apply` now always fetches Jira's `createmeta` (required fields per issue type) and persists it in `.jira.json`. Before any create API call, `create_ticket.py` and `bulk_create.py` validate that all required fields are present and exit with actionable `--set` hints if any are missing. This catches errors like "QBR is mandatory for Epics" before hitting the API.

**18. Actionable auto-diagnosis on create errors** — When `create_ticket.py` gets a 400 error, it checks each candidate field against the issue type's create screen (via `createmeta`). Fields that are on the screen with allowed values are marked **★ Recommended** and shown first. Fields not on the screen are flagged as "not on create screen, likely not settable" and shown last. This prevents the agent from trying non-settable fields before the actionable ones.

**19. Hierarchy-aware parent updates** — `update_ticket.py --parent` auto-wraps the key as `{"key": "..."}` for the API. When a parent update fails with a hierarchy error, the script fetches both issue types' hierarchy levels via the v3 `createmeta` endpoint, identifies the gap (e.g., Initiative level 3 → Epic level 1 skips Feature level 2), and suggests the intermediate type to create. The full project hierarchy is printed for reference.

**20. Assignee resolution with fuzzy suggestions** — `--assignee` accepts a display name (e.g., `"Dor Melamed"`), which is resolved to a Jira Cloud `accountId` via the `/rest/api/2/user/search` endpoint. Exact match is case-insensitive. If no exact match is found, the top 3 closest display names (via `difflib.get_close_matches`) are printed as suggestions and the assignee field is **not set** — allowing the agent to self-correct. Raw `accountId` values are passed through directly. Falls back to `{"name": ...}` for Jira Server or when no client is available.

**12. CLI flag normalization for LLM agents** — `jira_config_loader.py` calls `_normalize_argv()` at import time, patching `sys.argv` in-place before argparse ever sees it. Since every script imports `jira_config_loader`, normalization is automatic — no per-script wiring needed. Converts single-dash long flags (`-format`) to double-dash (`--format`). Short flags like `-v` are untouched.

**13. Config discovery with git root boundary** — `.jira.json` is discovered by walking up from CWD, stopping at the nearest git root to avoid picking up configs from unrelated parent directories. Global config (`~/.jira.json`) is merged underneath project-level config (project wins on conflict). An explicit `--config` flag overrides discovery entirely.

**14. Field search (`--search`)** — `discover_fields.py --search "QBR"` searches all Jira fields by name substring (case-insensitive) and prints field IDs, custom/system status, and schema types. This prevents agents from writing raw `curl` commands to find project-specific custom fields.

**15. Per-issue-type field listing (`--fields-for-type`)** — `discover_fields.py --fields-for-type epic` fetches all available fields for a given issue type via the per-type createmeta endpoint, marks required fields, and prints allowed values for dropdown fields. This directly addresses the scenario where an agent needs to know what values are valid for a field like "QBR Theme" on an Epic.

**16. Module structure** — `jira_config_loader.py` handles configuration loading, credential resolution, shell detection, and manifest I/O. All scripts share the same `--config` argument definition via `add_config_arg()` for consistency.

**17. Preflight script** — `jira_preflight.py` validates the full environment (Python version, venv, config, credentials, API connectivity, field discovery status) in a single call. The SKILL.md delegates all pre-session validation to this script rather than listing inline checks, matching the pattern used by bitbucket-manager, confluence-publisher, and jenkins-manager.

---

## Approval Gates

| Action | Approval Required | Mechanism |
|---|---|---|
| **Create (single or bulk)** | Yes | Plan shown with issue types, summaries, parents |
| **Update (single or bulk)** | Yes | Fields-to-change shown per ticket |
| **Delete** | Yes | `--dry-run` first, then `--confirm` to execute |
| **Status transition** | Yes (via update approval) | Target status shown in update plan |
| **Bulk update (board/JQL)** | Yes | Matched tickets and changes shown first; `--confirm` required |
| **Fetch / diff / validate** | No | Read-only, no side effects |
| **Discover fields** | No | Read-only (writes only to local `.jira.json` with `--apply`) |

---

## Bulk Update Scoping

Bulk updates can target tickets by four methods, each with different risk profiles:

| Method | Flag | Risk | Notes |
|---|---|---|---|
| **Explicit list** | `--tickets "PROJ-1,PROJ-2"` | Low | Exact tickets, no surprises |
| **Board (active sprint)** | `--board-id 123` | Medium | Scoped to active sprint by default |
| **Board (all)** | `--board-id 123 --board-all` | High | Includes backlog, closed, past sprints |
| **Filter** | `--filter status="In Progress"` | Medium | Builds JQL from field=value pairs |
| **Raw JQL** | `--jql "..."` | High | Arbitrary query, could match many issues |

All bulk updates default to **dry-run preview** and require `--confirm` to execute. The preview shows every matched ticket and the changes that would be applied.

---

## Field Discovery Flow

```
1. Agent runs: discover_fields.py --all --apply
2. Script queries Jira REST API for:
   - Issue types (story, bug, subtask, epic, etc.)
   - Statuses and their transition mappings
   - Priorities
   - Resolutions
   - Components
   - Fix versions
   - Sprints (via Agile API)
   - Custom fields (with --verbose)
   - Required fields per issue type (create_meta)
3. Results saved to field_catalog and create_meta in .jira.json
4. All subsequent scripts reference field_catalog for:
   - Validating --status values against available transitions
   - Resolving --priority to Jira's priority IDs
   - Mapping --sprint names to sprint IDs (Agile API)
   - Resolving --set field names to Jira field IDs
5. Create scripts reference create_meta to pre-validate required fields
```

If `field_catalog` is empty or stale, scripts may fail with "field not configured" — the fix is always to re-run discovery with `--apply`.

---

## Risks at a Glance

| Risk | Severity | Mitigation |
|---|---|---|
| Credential leakage | High | Env var indirection; never print values |
| Bulk update hitting wrong tickets | High | Dry-run default; `--confirm` gate; preview shows matched tickets |
| Creating duplicates on retry | Medium | Manifest-based skip; idempotent bulk create |
| Orphaned subtasks | Medium | Dependency-ordered creation; stop on parent failure |
| Invalid status transitions | Medium | Transition query + clear error messages |
| Stale field catalog | Medium | Pre-flight check triggers re-discovery |
| Hierarchy mismatch when re-parenting | Medium | Auto-diagnosis prints both levels + intermediate types needed |
| Agent ignoring auto-diagnosis hints | Medium | Actionable matches (★ Recommended) sorted first; non-settable fields flagged |
| Agent abandoning scripts for inline code | High | SKILL.md rules #1-2 mandate script usage; troubleshooting table documents common mistakes |
| Agent using wrong flag syntax (`-flag` vs `--flag`) | Medium | `normalize_args()` auto-corrects single-dash long flags |
| Wrong assignee name (typo, wrong case) | Medium | Fuzzy matching suggests top 3 closest names; assignee not set until corrected |
| Markup conversion artifacts | Low | `--no-convert` escape hatch; round-trip tested |
| Missing local images in description | Low | Warning printed; attachment upload errors handled gracefully |
| mmdc not installed for mermaid | Low | Blocks left as code with warning; no data loss |
| Raw JQL matching too broadly | High | Dry-run preview; `--confirm` required; max-results cap with warning |

---

## References

- **Jira Cloud REST API v2** — Issue CRUD, transitions, field metadata, search (JQL)
- **Jira Agile REST API v1.0** — Boards, sprints, sprint issue management
- **Jira wiki markup** — Confluence-style markup used in issue descriptions

## Status

**Stable (v2.1)** — Full CRUD, bulk operations, Agile board/sprint support, field discovery, diff/validate, markup conversion, image auto-attachment, mermaid diagram rendering, comments, issue links, parent re-parenting with hierarchy diagnosis, and actionable auto-diagnosis implemented.
