# Codex CLI `exec` Flag Reference (v0.106.0+)

Documentation of the raw Codex CLI flags, subcommands, sandbox modes, and configuration options. This is a developer/maintainer reference for understanding the internals — the wrapper script (`run_codex.py`) abstracts these away so agents never need to use them directly.

## Core Command

```bash
codex exec [OPTIONS] [PROMPT]
# or via stdin:
echo "prompt text" | codex exec [OPTIONS]
# or read from stdin explicitly:
codex exec -    # reads prompt from stdin
```

## Subcommands

| Subcommand | Purpose | Example |
|---|---|---|
| *(none)* | Run a task non-interactively | `codex exec "fix the bug in auth.ts"` |
| `resume` | Continue a previous session | `codex exec resume --last "now fix the tests"` |
| `review` | Run a code review against the repo | `codex exec review --uncommitted` |

## Complete Flag Reference

| Flag | Short | Purpose | Notes |
|---|---|---|---|
| `--full-auto` | | `on-request` approvals + `workspace-write` sandbox | Wrapper sets this for `--mode write` |
| `--ephemeral` | | Don't persist session rollout files to disk | Wrapper sets this by default (omitted with `--persist`) |
| `--output-last-message <FILE>` | `-o` | Write final agent message to file | Wrapper always sets this |
| `--json` | | JSONL streaming output to stdout | Not used by wrapper (prefers `-o`) |
| `--model <MODEL>` | `-m` | Override model | Passed through by wrapper |
| `--cd <DIR>` | `-C` | Set working directory | Blocked by wrapper (use `--collision medium` for worktrees) |
| `--sandbox <MODE>` | `-s` | Sandbox policy: `read-only`, `workspace-write`, `danger-full-access` | Wrapper sets via `--mode`; `-s` blocked |
| `--skip-git-repo-check` | | Allow running outside a Git repository | Passed through by wrapper |
| `--output-schema <FILE>` | | Path to JSON Schema for structured final response | Passed through by wrapper |
| `--add-dir <DIR>` | | Additional writable directories alongside workspace | Blocked by wrapper |
| `--config <key=value>` | `-c` | Override config.toml values (parsed as TOML) | Passed through (except sandbox overrides, which are blocked) |
| `--profile <NAME>` | `-p` | Use a named configuration profile | Passed through by wrapper |
| `--image <FILE>` | `-i` | Attach image(s) to the prompt | Passed through by wrapper |
| `--enable <FEATURE>` | | Enable a feature flag | Passed through by wrapper |
| `--disable <FEATURE>` | | Disable a feature flag | Passed through by wrapper |
| `--progress-cursor` | | Force cursor-based progress updates | Passed through by wrapper |
| `--color <COLOR>` | | Output color: `always`, `never`, `auto` | Wrapper always sets `--color never` |
| `--dangerously-bypass-approvals-and-sandbox` | | Skip ALL safety checks | Blocked by wrapper |
| `--oss` | | Use open-source model provider | Passed through by wrapper |
| `--local-provider <PROVIDER>` | | Specify local provider (`lmstudio` or `ollama`) | Passed through by wrapper |

## `codex exec review` Flags

| Flag | Purpose |
|---|---|
| `--uncommitted` | Review staged, unstaged, and untracked changes |
| `--base <BRANCH>` | Review changes against a given base branch |
| `--commit <SHA>` | Review changes introduced by a specific commit |
| `--title <TITLE>` | Optional commit title for the review summary |
| `-m <MODEL>` | Override model for the review |
| `--ephemeral` | Don't persist session files |
| `-o <FILE>` | Write review output to file |
| `--json` | JSONL output |

## `codex exec resume` Flags

| Flag | Purpose |
|---|---|
| `--last` | Resume the most recent session (no ID needed) |
| `--all` | Show all sessions (disables cwd filtering) |
| `[SESSION_ID]` | Resume a specific session by UUID or thread name |
| `[PROMPT]` | Follow-up prompt to send after resuming |

## Sandbox Modes

| Mode | Allows | Use For |
|---|---|---|
| `read-only` (default) | Read files, run safe commands | Analysis, review, search |
| `workspace-write` | + Write within workspace | Implementation, refactoring |
| `danger-full-access` | + Network, full disk | Blocked by wrapper |

### Capabilities by Sandbox Mode

| Capability | read-only | workspace-write | danger-full-access |
|---|---|---|---|
| Read files | Yes | Yes | Yes |
| Run safe bash (ls, cat, grep, rg, git log, etc.) | Yes | Yes | Yes |
| Run builds/tests (npm test, make, etc.) | No | Yes | Yes |
| Write/edit files | No | Yes (workspace only) | Yes (anywhere) |
| Run destructive commands (rm, git reset, etc.) | No | No | Yes |
| Web search | If `web_search_request=true` | Same | Same |
| Network access (curl, npm install, etc.) | No | No | Yes |

## Web Search

Enabled per-spawn via `-c` config override:
```bash
codex exec -c web_search_request=true --ephemeral -o result.txt "research React 19 changes"
```

The wrapper translates `--web-search` to `-c web_search_request=true` automatically.

- **Good for**: researching external APIs, checking latest docs, finding CVEs, migration guides
- **Avoid for**: code review, implementation, refactoring — web search adds ~5x latency

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | General error (auth, rate limit, config, model error) |
| 2 | CLI argument/usage error (invalid flag, bad value) |
| 101 | Rust panic / runtime crash — do not retry |
| 124 | Timeout |
| 127 | CLI not found |
| 137 | SIGKILL (OOM or forced kill) |
| 143 / -15 | SIGTERM (terminated, may have partial result) |

## Configuration (`~/.codex/config.toml`)

| Key | Values | Notes |
|---|---|---|
| `model_reasoning_effort` | `minimal`, `low`, `medium`, `high`, `xhigh` | `xhigh` requires v0.106.0+ |
| `approval_policy` | `on-request`, `never` | `on-failure` is deprecated |
| `sandbox_mode` | `read-only`, `workspace-write`, `danger-full-access` | CLI flag overrides config |
| `profile` | Named profiles under `[profiles.<name>]` | Different settings per task type |
| `features.multi_agent` | boolean | Enables multi-agent mode |
| `agents.max_depth`, `agents.max_threads` | integer | Controls for spawned agent limits |
| `developer_instructions` | string | Custom instructions in system prompt |
| `web_search_request` | boolean | Enable web search capability |

## Wrapper Flag Mapping

How the wrapper (`run_codex.py`) translates its high-level flags to raw codex flags:

| Wrapper Flag | Codex Flags Set |
|---|---|
| `--mode read-only` | `--sandbox read-only` |
| `--mode write` | `--full-auto --sandbox workspace-write` |
| *(default)* | `--ephemeral` |
| `--persist` | *(omits `--ephemeral`)* |
| `--web-search` | `-c web_search_request=true` |
| `--collision medium` | `--cd <worktree-dir>` |
| *(always)* | `-o <result-file> --color never` |
