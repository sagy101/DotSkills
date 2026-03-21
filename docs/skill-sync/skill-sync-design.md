# Skill Sync — Design Document

> This document covers **why** this skill exists and the **key decisions** an implementer or reviewer needs to understand.

---

## Why This Skill Exists

Skills are developed in a central repo but consumed from IDE-specific directories (`~/.claude/skills/`, `~/.codeium/windsurf/skills/`, etc.). Without a sync tool, developers manually `cp -r` skill folders — missing files, forgetting IDEs, and losing hook configurations.

This skill gives **any SKILL.md-compatible agent** the ability to distribute skills from a source repo to all installed IDEs in one command, including IDE-specific configuration (Claude Code hooks, Windsurf allowlists).

---

## Capabilities

| Capability | Description |
|---|---|
| **IDE detection** | Scan the system for installed IDEs by checking parent directories |
| **Skill discovery** | Find all skill directories (containing SKILL.md) in a source repo |
| **Multi-IDE sync** | Copy skills to user-level and/or project-level directories for 6 IDEs |
| **Skillignore** | Exclude files matching `.skillignore` patterns during copy |
| **Dry run** | Preview what would be synced without copying |
| **Claude Code hooks** | Auto-install a PreToolUse hook that approves read-only skill commands |
| **Read command classification** | Maintain a JSON registry of read-only vs write command patterns |

---

## Key Design Decisions

**1. OS-agnostic with pathlib** — Uses `pathlib.Path` throughout instead of `os.path` string operations. Works on macOS, Linux, and Windows without platform-specific branches. `Path.home()` resolves `~` correctly on all platforms.

**2. Detection by parent directory existence** — Rather than checking for running processes or registry entries, detection checks if the IDE's parent config directory exists (e.g., `~/.codeium/windsurf/` for Windsurf). This is reliable even when the IDE isn't running and avoids fragile process-name matching.

**3. Full overwrite per skill, not incremental** — When syncing, the target skill directory is removed and replaced entirely (`shutil.rmtree` + `shutil.copytree`). This avoids stale files from deleted scripts accumulating across syncs. The tradeoff (losing any local modifications in the target) is acceptable because skills should be edited in the source repo, not in IDE directories.

**4. Skillignore for exclusion** — A `.skillignore` file (glob patterns, same syntax as `.gitignore` lines) controls what gets excluded from copies. This prevents venvs, `__pycache__`, test artifacts, and other development-only files from polluting IDE skill directories. `.git` is always excluded.

**5. Read-command auto-approval via PreToolUse hook** — Claude Code supports `PreToolUse` hooks that can auto-approve tool calls. The sync script installs a Bash hook that pattern-matches commands against a JSON registry of read-only skill commands. This eliminates approval fatigue for safe operations (fetching tickets, viewing logs, checking build status) while preserving approval gates for write operations (creating tickets, triggering builds, merging PRs).

**6. Single source of truth for read patterns** — The read-command registry lives in `.claude/hooks/read-commands.json` as a JSON array of `{skill, pattern}` objects. Both the Claude Code hook script and the Windsurf whitelist doc are derived from this file. Adding a new read command means editing one file.

**7. Additive hook injection with dedup** — When updating `settings.json`, the script never overwrites existing hooks. It reads the current file, checks if the PreToolUse entry already exists (by matching the command path string), and only appends if missing. This makes the operation idempotent and safe to run repeatedly.

**8. Shell operator rejection in the hook** — The hook script rejects any command containing shell operators (`;`, `&&`, `||`, `|`, `` ` ``, `$(`) before pattern matching. This prevents injection attacks where a whitelisted read command is chained with a dangerous write command.

**9. Flag-anywhere matching for subcommand patterns** — Some scripts use flags to distinguish read from write operations (e.g., `page_versions.py --list` vs `page_versions.py --revert`). The hook matches the distinguishing flag anywhere in the command string, not at a fixed position, to handle arbitrary flag ordering by the agent.

---

## Architecture

```
skill-sync/
├── SKILL.md                     # Agent-facing instructions
├── scripts/
│   └── sync.py                  # Main sync script (detection, copy, hooks)

.claude/hooks/                   # Hook files (copied to targets during sync)
├── approve-read-commands.sh     # PreToolUse hook: auto-approve read commands
└── read-commands.json           # Registry of read-only command patterns

docs/
├── skill-sync/
│   └── skill-sync-design.md     # This document
└── windsurf-read-whitelist.md   # Windsurf-format whitelist (derived from JSON)
```

**sync.py modules:**
- `discover_skills()` — finds skill directories in source
- `detect_ides()` — resolves IDE paths for user/project level
- `sync_skills()` — copies skills to all targets
- `update_read_approvals()` — dispatcher that calls all IDE-specific handlers
- `update_claude_hooks()` — installs PreToolUse hook and updates settings.json
- `update_gemini_approval()` — generates TOML policy file with regex rules
- `update_windsurf_approval()` — merges command prefixes into Windsurf settings
- `_print_cursor_info()` / `_print_codex_info()` — guidance for unsupported IDEs
- `main()` — CLI entry point with argparse

---

## Approval Gates

| Action | Approval Required | Mechanism |
|---|---|---|
| **Detect IDEs** | No | Read-only scan of filesystem |
| **Dry run** | No | Preview only, no writes |
| **Sync skills** | Yes | Agent shows dry-run output, waits for user approval |
| **Install Claude hooks** | Automatic (part of sync) | Runs after skill sync when Claude is a target |

---

## Deep Dives

### Read Command Auto-Approval Flow

When Claude Code is about to execute a Bash tool call, the PreToolUse hook fires:

1. **stdin** — Claude Code passes `{"tool_input": {"command": "..."}}` as JSON
2. **Extract** — `jq` pulls `tool_input.command`
3. **Safety check** — Reject if command contains shell operators (`;`, `&&`, `|`, etc.)
4. **Pattern match** — Load patterns from `read-commands.json`, convert glob `*` to regex `.*`
5. **Flag matching** — For patterns with embedded flags (e.g., `--list`), match the flag anywhere in the command
6. **No-args fallback** — For patterns ending with ` *`, also match the bare command with no arguments
7. **Decision** — Match → `{"decision": "approve"}` + exit 0. No match → exit 1 (normal approval flow)

### Command Classification Criteria

Commands are classified based on their side effects:

| Classification | Criteria | Examples |
|---|---|---|
| **READ** | No external state changes; only retrieves data | `fetch_tickets.py`, `get_status.py`, `pr_list.py` |
| **WRITE** | Creates, updates, or deletes external resources | `create_ticket.py`, `trigger_build.py`, `pr_merge.py` |

Some scripts serve both roles depending on subcommand or flags:

| Script | READ flags/subcommands | WRITE flags/subcommands |
|---|---|---|
| `eks_ops.py` | `pods`, `logs` | `exec`, `restart` |
| `page_versions.py` | `--list`, `--fetch` | `--revert` |
| `run_codex.py` | `--mode read-only`, `--status` | `--mode write` |
| `pr_comment**s**.py` (plural) | All (view only) | — |
| `pr_comment.py` (singular) | — | All (add/edit/delete/resolve) |

Setup scripts (`jira_setup_env.py`, `confluence_setup_env.py`, `analyzer_setup_env.py`) are classified as READ because they only set up the local development environment (create venvs, install packages) with no external side effects.

### IDE-Specific Auto-Approval Mechanisms

The read-command registry in `read-commands.json` can be adapted to other IDEs:

| IDE | Mechanism | Status | Approach |
|---|---|---|---|
| **Claude Code** | `PreToolUse` hook in `settings.json` | Implemented | Shell script with pattern matching |
| **Gemini CLI** | TOML policy files in `.gemini/policies/` | Implemented | Generate `[[rule]]` entries with `commandRegex` and `decision = "allow"` |
| **Windsurf** | `cascadeCommandsAllowList` in user settings | Implemented | Merge command prefixes into OS-specific `settings.json` |
| **Codex CLI** | `approval_policy` in `.codex/config.toml` | Info only | Policy is coarse-grained (not per-command); prints setup guidance |
| **Cursor** | SQLite `state.vscdb` allowlist | Info only | Requires SQLite manipulation while IDE may hold lock; prints guidance |
| **Antigravity** | Allow list in VS Code-style settings | Not supported | Buggy; documented issues with allowlist enforcement |

**Gemini CLI** generates a dedicated TOML policy file (`dotskills-read-commands.toml`) with regex rules. Content comparison provides idempotency — re-running sync only rewrites the file if patterns changed.

**Windsurf** merges command prefixes into the user-level `settings.json` (`cascadeCommandsAllowList`). Flag-based dual-mode patterns (e.g., `page_versions.py --list`) are skipped because Windsurf's prefix matching cannot distinguish flag positions. A note directs users to the manual whitelist doc for these patterns.

**Cursor and Codex** lack clean per-command allowlist mechanisms, so sync prints informational messages with the closest available workaround.

---

## Guardrails

| Guardrail | Enforced By | Default |
|---|---|---|
| Shell operator rejection | Hook script (`approve-read-commands.sh`) | Always on — rejects `;`, `&&`, `\|\|`, `\|`, `` ` ``, `$()`, newlines |
| Write commands never auto-approved | Pattern list (`read-commands.json`) | Only explicitly listed read patterns match |
| Existing hooks preserved | `_update_settings_json()` in sync.py | Additive merge, never overwrites |
| Dedup prevents duplicate entries | All IDE handlers | Claude: checks command path; Gemini: content comparison; Windsurf: set difference |
| Flag-based patterns skipped for prefix IDEs | `_patterns_to_windsurf_prefixes()` | Windsurf skips dual-mode flag patterns that can't be safely prefix-matched |

---

## Risks at a Glance

| Risk | Severity | Mitigation |
|---|---|---|
| Read pattern matches a write command | Critical | 338-test suite covering all skills, flag orders, interpreters, injection attempts; patterns use script names + subcommands, not just prefixes |
| Shell injection bypasses hook | High | Pre-match rejection of all shell operators + newlines; full-string anchored regex matching |
| settings.json corruption during merge | Medium | JSON read → modify → write; dedup prevents bloat; corrupt JSON handled gracefully |
| Dual-mode conflict (read+write flags) | Medium | Script-level flag validation rejects conflicting args; prefix IDEs skip flag-based patterns entirely |
| New skill adds commands not in registry | Low | Tests validate consistency between JSON and whitelist MD; new skills need explicit registry updates |
| Hook script missing `jq` dependency | Low | `jq` is pre-installed on most dev machines; hook exits 1 (falls through to manual approval) if missing |

---

## References

- **Claude Code Hooks** — [PreToolUse hook specification](https://docs.anthropic.com/en/docs/claude-code/hooks) for auto-approving tool calls
- **Agent Skills Open Standard** — [agentskills.io/specification](https://agentskills.io/specification) for SKILL.md format
- **Gemini CLI Policy Engine** — [Policy TOML format](https://github.com/google-gemini/gemini-cli/blob/main/docs/reference/policy-engine.md) for future Gemini integration
- **Windsurf Terminal Docs** — [cascadeCommandsAllowList](https://docs.windsurf.com/windsurf/terminal) for Windsurf integration

## Status

**Stable (v2.0)** — Sync script with auto-approval for 3 IDEs (Claude Code, Gemini CLI, Windsurf) plus guidance for 2 more (Cursor, Codex). 338 tests covering all 12 skills: read/write classification, flag ordering variations, interpreter variants, path variants, injection attacks (shell operators, newlines, backticks, subshells), dual-mode conflict scenarios, substring false positives, and IDE-specific integration (TOML generation, settings merge, idempotency).
