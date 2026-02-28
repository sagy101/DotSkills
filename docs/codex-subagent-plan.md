# Codex CLI Sub-Agent Skill — Comprehensive Plan

> **Codex CLI version**: 0.106.0 (`codex-cli 0.106.0` via `npm i -g @openai/codex`)  
> **Default model**: `gpt-5.3-codex` (configurable via `-m` or `config.toml`)  
> **Last updated**: 2025-02-28

## 1. Overview

An Agent Skill that enables any SKILL.md-compatible host agent (Windsurf, Claude Code, Cursor, Codex, Gemini CLI, etc.) to delegate coding tasks to OpenAI's Codex CLI (`codex exec`) as a sub-agent. This gives the host agent sub-agent capabilities similar to how Claude Code uses its Task tool and how Codex uses `spawn_agent` — running independent AI agents that work on focused tasks and return results.

### Why This Matters
- **Not all agents have built-in sub-agent support** — this skill adds it via Codex CLI
- **MCP may be disabled** by the org — this skill bridges the gap without MCP
- **Sub-agents unlock**: parallel work, fresh context exploration, code review, second opinions, and delegated implementation

### How It Works (High Level)
1. The host agent detects a task suitable for delegation
2. Constructs a focused prompt with relevant context
3. Runs `codex exec` non-interactively via its shell execution capability
4. Monitors progress, collects results
5. Incorporates Codex's output back into its workflow

### What is the "Host Agent"?

**You — the AI coding agent reading this skill right now — are the host agent.** Whether you are Windsurf/Cascade, Claude Code, Cursor, Codex, Gemini CLI, or any other SKILL.md-compatible agent, this skill is talking to you. When this document says "the host agent should...", it means **you** should.

### Required Capabilities
This skill requires three abstract capabilities. Below are concrete tool examples for each agent:

| Capability | What It Means | Windsurf/Cascade | Claude Code | Cursor | Codex CLI |
|---|---|---|---|---|---|
| **Shell execution** | Run a shell command, either blocking (wait for result) or non-blocking (run in background) | `run_command` tool with `Blocking=true/false` and `WaitMsBeforeAsync` | `Bash` tool (blocking by default; use `&` for background) | `run_command` tool | `exec` tool / bash |
| **File reading** | Read a file's contents by path | `read_file` tool (supports `offset`/`limit` for large files) | `Read` tool (supports line ranges) | `read_file` tool | `cat` via bash |
| **Async monitoring** | Check if a background command has finished, get its output | `command_status` tool (by command ID, supports `WaitDurationSeconds`) | Re-run `Bash` with `ps` or check output file | `command_status` tool | `wait` tool (blocks until agent finishes) |

**Additional capabilities** (not required, but the host agent should use them when available instead of delegating):

| Capability | What It Means | Windsurf/Cascade | Claude Code | Cursor |
|---|---|---|---|---|
| **Code search** | Search codebase by semantic query or pattern | `code_search` (Fast Context), `grep_search` | `Grep` tool, `Glob` tool | `grep_search`, `find_by_name` |
| **Web search** | Search the internet for information | `search_web` tool, `read_url_content` | `WebSearch` tool, `WebFetch` | `search_web` tool |
| **File listing** | List directory contents, find files | `list_dir`, `find_by_name` | `LS` tool, `Glob` tool | `list_dir`, `find_by_name` |

> **Key principle**: If you (the host agent) have a built-in tool that can accomplish the task, **use it directly** instead of delegating to a sub-agent. Only delegate when fresh context, parallelism, or isolation adds value. See Tool Priority in Section 7.

### Glossary of Terms
This skill introduces several terms. To avoid ambiguity, each is defined precisely here and used consistently throughout the plan.

| Term | Definition |
|---|---|
| **Host Agent** | The AI coding agent reading and executing this skill — you. Examples: Windsurf/Cascade, Claude Code, Cursor, Codex, Gemini CLI. When this document says "the host agent should…", it means **you** should. |
| **Sub-Agent** | An independent Codex CLI process spawned by the host agent to perform a focused task. It starts with a fresh context, runs in its own sandbox, and returns a result via an output file. It has no access to the host agent's conversation history. |
| **Delegation** | The act of the host agent assigning a task to a sub-agent instead of doing it directly. Delegation has overhead (~5-50K tokens) and latency (1-10 min), so it should only be used when the benefits (fresh context, parallelism, isolation) outweigh the costs. |
| **Spawn** | A single invocation of the wrapper script (`run_codex.sh`) that creates one sub-agent. "Per-spawn" means "per invocation" — each spawn is independent with its own temp dir, output file, and optional git worktree. |
| **Wrapper Script** (`run_codex.sh`) | A bash script that sits between the host agent and `codex exec`. It is the **only interface** the host agent should use. It enforces safety policy, adds default flags, manages temp files, handles git worktrees, and provides clear error messages. The host agent must NEVER call `codex` directly — always use the wrapper. |
| **Collision Confidence** | The host agent's assessment of how likely a write delegation will conflict with its own pending or planned edits. Three levels: **High** (>80% no conflict — delegate directly), **Medium** (40-80% — delegate via git worktree for safe isolation), **Low** (<40% — do NOT delegate writes; do it yourself or delegate as read-only). See P6 for assessment criteria. |
| **Model Strictness** | A user-configurable setting that controls how aggressively the host agent routes tasks to cheaper/faster models. Three levels: **Conservative** (always best model), **Balanced** (default — downgrade when >80% confident task is simple), **Aggressive** (always try cheapest first, upgrade on failure). Configured via `CODEX_SUBAGENT_MODEL_STRICTNESS` env var. |
| **Super-Review** | A review pattern where the host agent runs its own review AND launches multiple specialized Codex reviews in parallel, then synthesizes all findings into one cohesive result. See Section 9. |
| **Fresh Context** | A sub-agent starts with zero knowledge of the host agent's conversation, prior decisions, or accumulated state. This is both a cost (context must be passed in the prompt) and a benefit (no accumulated bias, no context window bloat). |
| **Tool Priority** | The order in which the host agent should consider tools: (1) built-in tools, (2) MCP servers/integrations, (3) sub-agent delegation. The host agent must always check if its own tools can handle the task before delegating. |
| **Adaptive Polling** | The strategy of varying the poll interval based on estimated task complexity. Simple tasks: 10-30s. Standard tasks: 30-60s. Complex tasks: 60-180s. This avoids wasting tool calls on long tasks while staying responsive on short ones. |
| **Trusted Workspace** | The assumption that the skill runs in the user's own codebase (not a malicious or untrusted repo). This downgrades prompt injection risk from HIGH to LOW and simplifies several security mitigations. |
| **Pre-flight Checks** | A set of validation steps the host agent runs before the first delegation in a session: codex installed? correct version? authenticated? git repo? model strictness configured? |
| **Operation** | A numbered workflow pattern for a specific type of delegation. Op 1: Implementation, Op 2: Analysis/Review, Op 2b: Dedicated Code Review, Op 3: Super-Review, Op 4: Structured Output, Op 5: Resume/Multi-Turn. |
| **Mode** | The wrapper's `--mode` flag. Two values: `read-only` (sub-agent can only read files and run safe commands) or `write` (sub-agent can also write files within the workspace). |
| **Persist** | The wrapper's `--persist` flag. When set, the wrapper omits `--ephemeral` so the Codex session is saved to disk. Required if the host agent plans to use `--resume` later for multi-turn delegation (Op 5). Without `--persist`, sessions are ephemeral and cannot be resumed. |
| **Review Prompt** | A `.md` file containing a focused review system prompt (~500-2000 tokens). The wrapper's `--review-prompt <filepath>` flag reads the file and prepends it to stdin automatically — the full prompt never passes through the host agent's context. Review prompt files can come from the companion `review-prompts` skill, user-custom files, or any other source. The host agent only needs the short description (from the review skill's SKILL.md) to pick the right one. |

---

## 2. Research Sources

### Primary Sources (Code Read)
| Source | What We Extracted |
|---|---|
| `shinpr/sub-agents-skills` | SKILL.md structure, `run_subagent.py`, JSONL stream processing, prompt formatting pattern |
| `Piebald-AI/claude-code-system-prompts` | Task tool definition, Explore agent prompt, subagent guidance, task management patterns |
| `openai/codex` (Rust source) | System prompt (276 lines), orchestrator template, multi-agent collab template, JSONL event processor (881 lines) |

### Secondary Sources (Web)
| Source | Key Insight |
|---|---|
| Codex CLI docs (developers.openai.com) | Complete `codex exec` flag reference |
| openclaw/skills codex-sub-agents | CLI backend patterns, direct exec vs subagent delegation |
| dev.to token waste article | Each CLI invocation costs ~5-50K tokens in system overhead; mitigation strategies |

---

## 3. How Real Sub-Agents Work (Reference Architecture)

### Claude Code's Task Tool
- Parent sends **prompt** + **description** to sub-agent
- Sub-agent gets its own **restricted tool set** (e.g., Explore agent disallows Edit/Write)
- Sub-agent runs independently, returns **summarized output** to the main conversation
- Parent incorporates or re-summarizes for user (sub-agent output not directly visible)
- Supports **foreground** (blocking) and **background** (concurrent) modes
- Sub-agents start **fresh** — no shared context with parent
- Can be **resumed** by agent ID for follow-up work
- Key quote from Claude Code system prompt: *"Subagents are valuable for parallelizing independent queries or for protecting the main context window from excessive results"*

### Codex's Multi-Agent System (Orchestrator Mode)
- Orchestrator spawns agents via `spawn_agent` with a prompt
- Coordinates via `wait` / `send_input` / `close_agent`
- Agents share the same workspace but have independent contexts
- Each agent warned: *"they are not alone in the environment so they should not impact/revert the work of others"*
- Sub-agents have access to the same tool set — must explicitly restrict if needed
- `timeout_ms` parameter is critical — must be "wisely scaled"

### The shinpr/sub-agents-skills Pattern
- SKILL.md tells the host agent how to invoke `run_subagent.py`
- Script reads `.agents/*.md` definitions (YAML frontmatter specifies which CLI)
- Builds structured prompt: `[System Context]\n{agent_body}\n\n[User Prompt]\n{task}`
- For Codex: runs `codex exec --json <prompt>`, streams JSONL
- Parses events: `thread.started` → `item.completed` (type: `agent_message`) → `turn.completed`
- Returns structured JSON: `{result, exit_code, status, cli}`
- Default timeout: 600s (10 min)

---

## 4. Codex CLI `exec` Reference (v0.106.0)

### Core Command
```bash
codex exec [OPTIONS] [PROMPT]
# or via stdin:
echo "prompt text" | codex exec [OPTIONS]
# or read from stdin explicitly:
codex exec -    # reads prompt from stdin
```

### Subcommands
| Subcommand | Purpose | Example |
|---|---|---|
| *(none)* | Run a task non-interactively | `codex exec "fix the bug in auth.ts"` |
| `resume` | Continue a previous session | `codex exec resume --last "now fix the tests"` |
| `review` | Run a code review against the repo | `codex exec review --uncommitted` |

### Complete Flag Reference (from `codex exec --help` v0.106.0)
| Flag | Short | Purpose | When to Use |
|---|---|---|---|
| `--full-auto` | | Low-friction mode: `on-request` approvals + `workspace-write` sandbox | Write/implement tasks |
| `--ephemeral` | | Don't persist session rollout files to disk | Always for sub-agent cleanup |
| `--output-last-message <FILE>` | `-o` | Write final agent message to file | Always (reliable output capture) |
| `--json` | | JSONL streaming output to stdout | Only if parsing events (prefer `-o`) |
| `--model <MODEL>` | `-m` | Override model | When specific model needed |
| `--cd <DIR>` | `-C` | Set working directory | When task targets specific directory |
| `--sandbox <MODE>` | `-s` | Sandbox policy: `read-only`, `workspace-write`, `danger-full-access` | Always consider explicitly |
| `--skip-git-repo-check` | | Allow running outside a Git repository | Fallback for non-repo dirs |
| `--output-schema <FILE>` | | Path to JSON Schema for structured final response | When structured data needed |
| `--add-dir <DIR>` | | Additional writable directories alongside workspace | Multi-repo tasks |
| `--config <key=value>` | `-c` | Override config.toml values (parsed as TOML) | Runtime config overrides |
| `--profile <NAME>` | `-p` | Use a named configuration profile | Different settings per task type |
| `--image <FILE>` | `-i` | Attach image(s) to the prompt | Visual context (screenshots, diagrams) |
| `--enable <FEATURE>` | | Enable a feature flag (`-c features.<name>=true`) | Opt-in features |
| `--disable <FEATURE>` | | Disable a feature flag | Opt-out features |
| `--progress-cursor` | | Force cursor-based progress updates | When capturing progress |
| `--color <COLOR>` | | Output color: `always`, `never`, `auto` | Script/CI environments |
| `--dangerously-bypass-approvals-and-sandbox` | | Skip ALL safety checks. **EXTREMELY DANGEROUS.** | Only in externally sandboxed envs |
| `--oss` | | Use open-source model provider | Local models via Ollama/LMStudio |
| `--local-provider <PROVIDER>` | | Specify local provider (`lmstudio` or `ollama`) | With `--oss` |

### `codex exec review` Flags (v0.106.0)
A dedicated code review subcommand with specialized options:
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

### `codex exec resume` Flags (v0.106.0)
| Flag | Purpose |
|---|---|
| `--last` | Resume the most recent session (no ID needed) |
| `--all` | Show all sessions (disables cwd filtering) |
| `[SESSION_ID]` | Resume a specific session by UUID or thread name |
| `[PROMPT]` | Follow-up prompt to send after resuming |

### Sandbox Modes
| Mode | Allows | Use For |
|---|---|---|
| `read-only` (default) | Read files, run safe commands | Analysis, review, search |
| `workspace-write` | + Write within workspace | Implementation, refactoring |
| `danger-full-access` | + Network, full disk | Package install, API calls (RARE) |

### Sub-Agent Capabilities by Sandbox Mode
When Codex runs as a sub-agent, it has these capabilities:

| Capability | read-only | workspace-write | danger-full-access |
|---|---|---|---|
| **Read files** | Yes | Yes | Yes |
| **Run safe bash** (ls, cat, grep, rg, git log, etc.) | Yes | Yes | Yes |
| **Run builds/tests** (npm test, make, etc.) | No | Yes | Yes |
| **Write/edit files** | No | Yes (workspace only) | Yes (anywhere) |
| **Run destructive commands** (rm, git reset, etc.) | No | No | Yes |
| **Web search** | If `web_search_request=true` in config | Same | Same |
| **Network access** (curl, npm install, etc.) | No | No | Yes |

**Web search** can be enabled **per spawn** via the `-c` config override flag:
```
# Enable web search for a specific sub-agent spawn:
codex exec -c web_search_request=true --ephemeral -o result.txt "research latest React 19 breaking changes"

# Default (no web search):
codex exec --ephemeral -o result.txt "review this code for bugs"
```

The host agent should decide per-task whether web search is helpful:
- **Enable** for: researching external APIs, checking latest docs, finding CVEs, migration guides
- **Disable** (default) for: code review, implementation, refactoring, debugging — web search adds latency (~5x slower) and tokens

The wrapper script (`run_codex.sh`) does NOT enable web search by default. The host agent must explicitly pass `--web-search` when it determines web context would help. (The wrapper translates this to `-c web_search_request=true`.)

Note: `--full-auto` is a convenience alias that sets both `--sandbox workspace-write` and approval policy to `on-request`.

### JSONL Event Types (when using `--json`)
From official docs and verified against Codex source (`event_processor_with_jsonl_output.rs`):
```
thread.started       → Session initialized (includes thread_id)
turn.started         → Agent begins a turn
item.started         → Tool/command begins (command_execution, mcp_tool_call, etc.)
item.updated         → Intermediate update (e.g., plan/todo list changes)
item.completed       → Item finished: agent_message, command_execution, mcp_tool_call,
                        custom_tool_call, web_search_call, todo_list, task, plan,
                        user_message, reasoning
turn.completed       → Agent finished turn (includes usage: input_tokens,
                        cached_input_tokens, output_tokens)
turn.failed          → Turn ended with critical error
error                → Error event
```

Sample JSONL stream:
```json
{"type":"thread.started","thread_id":"0199a213-81c0-7800-8aa1-bbab2a035a53"}
{"type":"turn.started"}
{"type":"item.started","item":{"id":"item_1","type":"command_execution","command":"bash -lc ls","status":"in_progress"}}
{"type":"item.completed","item":{"id":"item_3","type":"agent_message","text":"Repo contains docs, sdk, and examples."}}
{"type":"turn.completed","usage":{"input_tokens":24763,"cached_input_tokens":24448,"output_tokens":122}}
```

### Exit Codes
| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | General error (auth, rate limit, config, model error) |
| 124 | Timeout |
| 127 | CLI not found |
| 2 | CLI argument/usage error (invalid flag, bad value) |
| 143 / -15 | SIGTERM (terminated, may have partial result) |

Note: Exit codes 124, 127, 143 are shell/wrapper-level conventions, not Codex-specific guarantees.

### Config Notes (`~/.codex/config.toml`)
- `model_reasoning_effort`: `minimal | low | medium | high | xhigh` (xhigh requires v0.106.0+)
- `approval_policy`: `on-failure` is **deprecated** → use `on-request` (interactive) or `never` (non-interactive/CI)
- `sandbox_mode`: persisted default; CLI flag `-s` overrides
- `profile`: named config profiles under `[profiles.<name>]` for different task types
- `features.multi_agent`: enables multi-agent/collaboration mode
- `agents.max_depth`, `agents.max_threads`: controls for spawned agent limits
- `developer_instructions`: custom instructions injected into system prompt
- `instructions`: user-level custom instructions

---

## 5. Pitfalls & Mitigations

### P1: Long-Running Command Constraints (CRITICAL)
**Problem**: Codex exec can run for minutes. Blocking the host agent freezes user interaction. Non-blocking requires polling.
**Mitigation**:
- Run `codex exec` as a **non-blocking/async** shell command to avoid freezing the user
- Use a short initial wait (~3s) to catch quick failures (e.g., bad flags, auth errors)
- Poll command status at adaptive intervals (see P12 for cadence)
- Use `-o <path>` so final output is a simple file read
- Tell the user "Delegated to Codex, waiting..." with periodic updates

### P2: Output Parsing Complexity (HIGH)
**Problem**: `--json` JSONL stream is complex (multiple event types, 881 lines of parsing code in Codex source). `command_status` has limited output buffer.
**Mitigation**:
- **Don't parse JSONL**. Use `-o <path>` flag — Codex writes final message to a file
- Read result via `read_file` — simple, reliable, no parsing needed
- Only use `--json` if we need intermediate progress events (future enhancement)

### P3: Token/Cost Waste (HIGH)
**Problem**: Each `codex exec` invocation loads full system prompt + workspace context (~5-50K tokens per turn, per dev.to article).
**Mitigation**:
- Use `--ephemeral` to avoid disk waste
- Keep prompts focused and scoped
- Use `--cd` to limit workspace scope
- Avoid delegating trivially small tasks (overhead > value)
- Consider `codex exec resume --last` for multi-turn to amortize setup cost
- For analysis-only tasks, use `--sandbox read-only` (lighter overhead)

### P4: Sandbox & Permissions (HIGH)
**Problem**: Default sandbox is read-only. Codex can't write files without `--full-auto` or `--sandbox workspace-write`.
**Mitigation**:
- SKILL.md decision tree:
  - Read-only tasks (review, search, analyze) → default sandbox
  - Write tasks (implement, refactor, fix) → `--full-auto`
  - Never use `danger-full-access` without explicit user consent
- Pre-flight check: warn user about permission level

### P5: Context Passing — The Sub-Agent Starts Fresh (MEDIUM-HIGH)
**Problem**: Codex sub-agent has no knowledge of the host agent's conversation history, prior decisions, or current state.
**Mitigation**:
- The host agent must construct a rich prompt including:
  1. **Goal**: What to accomplish
  2. **Context**: Relevant background, prior decisions, constraints
  3. **Files**: Specific paths to focus on (Codex will read them itself)
  4. **Constraints**: What NOT to do, style requirements, boundaries
  5. **Output format**: What to return (summary, diff, analysis, etc.)
- See Section 8 for prompt templates

### P6: File Conflicts — Collision Confidence Framework (MEDIUM-HIGH)
**Problem**: Codex may edit files that the host agent has modified or is about to modify.

**Solution**: Before every write delegation, the host agent must assess **collision confidence** — how confident it is that the sub-agent's work will NOT collide with its own.

#### Collision Confidence Levels

| Level | Definition | Examples | Action |
|---|---|---|---|
| **High** (>80%) | Files are clearly distinct; sub-agent works in a completely different area | Host editing `src/auth/`, delegating work in `src/payments/`; delegating new test file creation; delegating docs generation | **Delegate directly** — no worktree needed |
| **Medium** (40-80%) | Some overlap possible but not certain; files are related but probably distinct | Host editing `src/api/routes.ts`, delegating refactor of `src/api/middleware.ts`; both touch shared types | **Delegate via git worktree** — isolate sub-agent, review diff, merge after |
| **Low** (<40%) | High chance of collision; files are tightly coupled or the same | Host and sub-agent both need to edit `src/api/routes.ts`; shared state files; interleaved logic | **Do NOT delegate write task** — do it yourself, or delegate as read-only analysis instead |

#### Best Practices for Assessing Collision Confidence
- **Check your recent edits**: What files have you modified in this conversation? Those are high-risk.
- **Check your planned edits**: What files will you need to modify next? Those are high-risk too.
- **Check import chains**: If the sub-agent's target files import from your files (or vice versa), risk is medium.
- **Shared types/interfaces**: If both sides use the same types file, risk is medium.
- **Different directories**: Usually high confidence, unless they share a common module.
- **Read-only tasks**: Always high confidence (no conflict possible).

#### Git Worktree Workflow (when confidence is Medium)
The wrapper script (`run_codex.sh`) handles worktree setup/teardown automatically when passed `--collision medium`:

1. **Setup**: `git worktree add /tmp/codex-wt-{uuid} -b codex-work-{uuid}` — creates isolated working directory
2. **Sub-agent runs**: `codex exec --cd /tmp/codex-wt-{uuid} ...` — all changes happen in the worktree
3. **Review**: Host agent runs `git diff main..codex-work-{uuid}` to see what changed
4. **Merge**: If approved, `git merge codex-work-{uuid}` brings changes into the main working tree
5. **Cleanup**: `git worktree remove /tmp/codex-wt-{uuid}` and `git branch -d codex-work-{uuid}`

The host agent sees the diff before anything touches its working tree. Easy rollback = just don't merge.

**Fallback**: Before delegation, always save pending changes. After delegation, always re-read modified files and review via `git diff`.

### P7: Git Repository Requirement (MEDIUM)
**Problem**: `codex exec` requires being inside a git repo.
**Mitigation**: Pre-flight check for `.git/`; use `--skip-git-repo-check` as fallback.

### P8: Authentication (MEDIUM)
**Problem**: Codex needs auth via `codex login` or `CODEX_API_KEY` env var.
**Mitigation**: Pre-flight check: `codex login status`.

### P9: Model Selection (LOW-MEDIUM)
**Problem**: Codex defaults to config model. Different tasks may benefit from different models.
**Mitigation**: Expose `-m <model>` as optional. Suggest cheaper/faster models for simple tasks.

### P10: Error Recovery (MEDIUM)
**Problem**: Codex can fail: auth errors, rate limits, model unavailable, timeout.
**Mitigation**: 
- Parse exit code from `command_status`
- Read `-o` output file (may contain partial results)
- Error decision table in SKILL.md:
  - Exit 0: success → read output
  - Exit 1 + "rate limit": wait and retry
  - Exit 1 + "auth": prompt user to run `codex login`
  - Exit 124: timeout → retry with simpler prompt or longer timeout
  - Exit 127: codex not installed → abort with install instructions

### P11: Prompt Injection via Workspace Files (LOW — assuming trusted workspace)
**Problem**: Codex reads AGENTS.md and workspace files — a malicious repo could steer sub-agent behavior via supply-chain injection.
**Note**: This skill assumes it runs in a **trusted workspace** (user's own code, known origin). In this context, prompt injection risk is low.
**Mitigation** (for untrusted workspaces, if ever needed):
- Default-deny delegation on untrusted/newly-cloned repos
- For isolated tasks, use `--cd /tmp/isolated-dir` with `--add-dir` for specific paths
- Treat Codex output as **untrusted text** — never auto-execute suggested commands

### P12: No Streaming Feedback to User (LOW)
**Problem**: Unlike Claude Code's real-time sub-agent progress, user sees nothing until Codex finishes.
**Mitigation**: The host agent tells the user "Delegated to Codex, working on X..." and polls command status for updates.

**Adaptive polling cadence** (the host agent should estimate task complexity):
| Task Complexity | Examples | Poll Interval | Max Wait |
|---|---|---|---|
| Simple (search, explain) | grep, summarize, list | 10-30s | 5 min |
| Standard (review, analyze) | code review, data flow | 30-60s | 10 min |
| Complex (implement, refactor) | new feature, large refactor | 60-180s | 20 min |
| Extended (migration, full analysis) | framework upgrade, full codebase | 120-300s | 40 min |

The host agent should state its estimate: "This looks like a ~3min task, I'll check back shortly."

Define explicit states: `queued → running → completed/failed/cancelled` with elapsed time in updates.

### P13: Command Injection in Prompt Passing (CRITICAL — from gaps review G1)
**Problem**: Prompt text interpolated directly into shell commands can cause command injection via special characters, quotes, or shell metacharacters.
**Mitigation**:
- **Always use stdin/heredoc** for prompt passing, never inline shell arguments for dynamic prompts
- Pattern: `echo "$PROMPT" | ./scripts/run_codex.sh --mode read-only -`
- Or write prompt to temp file first: `./scripts/run_codex.sh --mode read-only - < /tmp/prompt.txt`
- Shell-escape all dynamic arguments (file paths, model names)
- The SKILL.md must instruct the host agent to pass the prompt via stdin, not as a quoted shell argument
- Note: The wrapper script enforces this pattern — all wrapper examples use stdin piping

### P14: Secret/Sensitive Data Leakage (CRITICAL — from gaps review G2, security review S6)
**Problem**: Rich context prompts may accidentally include API keys, tokens, passwords, or sensitive file contents.
**Mitigation**:
- **Denylist paths**: never include `.env`, `*.pem`, `*.key`, `credentials.*`, `secrets.*` in prompts
- **Denylist patterns**: redact strings matching API key patterns before sending
- **Prompt hygiene**: include only file paths (let Codex read them) rather than pasting file contents
- **Output scanning**: check Codex output for leaked secrets before presenting to user
- Pre-delegation check: warn if target files match sensitive patterns

### P15: Insecure Temp File Handling (HIGH — from gaps review G3, security review S4)
**Problem**: Predictable `/tmp/codex-result-{timestamp}.txt` paths are readable by other users, may leak sensitive output, and are vulnerable to symlink attacks.
**Mitigation**:
- Use `mktemp -d` for secure temp directories with `0700` permissions
- Use random filenames (UUID), not timestamps
- **Guaranteed cleanup**: delete output files after ingestion on all paths (success, failure, cancel)
- Consider workspace-local temp dir (`.codex-tmp/`) if the host agent's environment blocks `/tmp` access
- Note: The wrapper script handles all temp file management automatically (`mktemp -d`, `chmod 700`, cleanup via trap). The host agent does not need to manage temp files directly.

### P16: Missing Cancel/Abort Workflow (HIGH — from gaps review G6, practical review P9)
**Problem**: No mechanism for user to cancel a long-running delegated task, and no handling for orphaned processes after IDE restart.
**Mitigation**:
- Track PID/command-id for each delegation
- On user cancel: terminate the codex process, clean up temp files, report partial results if available
- On IDE restart: detect orphaned codex processes, offer to kill or wait
- The skill should instruct the host agent to check for stale temp files on startup

### P17: Version Compatibility Gate (HIGH — from gaps review G7)
**Problem**: Plan depends on v0.106.0+ flags (`--ephemeral`, `--output-schema`, `--add-dir`, `exec review`, `exec resume`). Older versions will fail silently or with confusing errors.
**Mitigation**:
- Pre-flight: parse `codex --version` output, require minimum version
- If below minimum: warn user and provide upgrade command (`npm i -g @openai/codex`)
- Graceful degradation: if specific flag unavailable, fall back to basic `codex exec` without it

### P18: Ephemeral vs Resume Contradiction (MEDIUM — from own review W5)
**Problem**: `--ephemeral` prevents session persistence, making `codex exec resume` impossible after an ephemeral run.
**Mitigation**:
- Default to `--ephemeral` for one-shot delegations (reviews, analysis, implementation)
- Omit `--ephemeral` when multi-turn conversation with the sub-agent is planned
- Document explicitly: "If you plan to `resume`, do NOT use `--ephemeral`"

### P19: Output Trust Boundary (HIGH — from security review S2)
**Problem**: Codex output may contain socially-engineered instructions or code that, if auto-executed, could be harmful.
**Mitigation**:
- **Never auto-execute** commands or code suggested by Codex output
- Treat all Codex output as untrusted text requiring human or host agent validation
- For write tasks: always `git diff` review before incorporating changes
- For code suggestions: validate via tests before accepting

### P20: Cost/Quota Controls (MEDIUM-HIGH — from security review S5, gaps review G9)
**Problem**: Super-review fan-out + retries can burn API quota quickly. No hard limits on concurrency.
**Mitigation**:
- Hard cap: max 6 parallel Codex instances per super-review
- Hard cap: max 2 retries per delegation
- Timeout tiers (5/10/20/40 min) naturally bound cost for any recursive sub-agent spawning
- Per-task token budget awareness: use `-c model_reasoning_effort="medium"` for simple tasks

---

## 5b. Guardrails

Runtime protections enforced by the wrapper script and/or the host agent to prevent misuse, runaway costs, and silent failures.

### Wrapper-Enforced (Script Level)

| Guardrail | Mechanism | Default | Override |
|---|---|---|---|
| **Dangerous sandbox block** | Rejects `--sandbox danger*`, `-s`, `--dangerously-bypass*`, `-c sandbox*` at argument level. Mode always sets explicit `--sandbox` flag (never relies on user config). | Always on | Cannot be overridden |
| **Timeout** | Kills codex process after `--timeout` seconds. Host agent selects from 4 tiers based on task complexity. | 600s (10 min) | `--timeout 300\|600\|1200\|2400` |
| **Prompt size warning** | Warns to stderr if combined prompt (review-prompt file + stdin) exceeds threshold | 50K chars | `MAX_PROMPT_CHARS` in script |
| **Version gate** | Exits if codex CLI version < `MIN_VERSION` | v0.106.0 | `MIN_VERSION` in script |
| **Review prompt validation** | Exits with helpful error if `--review-prompt` file doesn't exist | Always on | — |
| **Misused flag detection** | Rejects raw flags (`--ephemeral`, `--full-auto`, `-o`, `--sandbox`) with explanation of correct wrapper flag | Always on | — |

#### Timeout Tiers
The host agent selects the timeout based on estimated task complexity:

| Tier | Timeout | When to Use |
|---|---|---|
| **Short** | 5 min (300s) | Simple searches, explanations, single-file reviews |
| **Standard** | 10 min (600s) | Code reviews, analysis, standard implementation |
| **Long** | 20 min (1200s) | Large refactors, multi-file implementation, complex debugging |
| **Extended** | 40 min (2400s) | Major migrations, full-codebase analysis, massive test generation |

**Resume on timeout**: If a task times out, the host agent should:
1. Inform the user: "Sub-agent timed out after Xmin. Resuming with a longer timeout."
2. Re-launch with `--persist` + the next tier up (e.g., 10min → 20min, 20min → 40min)
3. If it times out again at the highest tier (40min), something is likely wrong — report to user and do not retry.

### Host-Agent-Enforced (SKILL.md Instructions)

| Guardrail | Mechanism | Default |
|---|---|---|
| **Max parallel spawns** | Host agent must not launch more than N sub-agents concurrently | 6 |
| **Max retries** | Host agent retries a failed delegation at most N times | 2 |
| **Result validation** | Before reading output, host agent checks: file exists? non-empty? size < 1MB? If empty or missing, treat as failure. | Always |
| **Collision confidence gate** | Host agent must assess collision confidence before write delegations. Low confidence → do NOT delegate writes. | Always |
| **Output trust boundary** | Never auto-execute commands or code from sub-agent output. Always validate via git diff or tests. | Always |

> **Note on recursive spawning**: If the sub-agent (Codex CLI) has its own sub-agent capabilities or skills installed, it is free to use them. The timeout guardrail naturally bounds any recursive cost — the entire sub-agent process is killed when the timeout expires, regardless of what it spawned internally. The host agent does not need to block recursion explicitly.

---

## 6. Skill Architecture

### File Structure
```
codex-subagent/
├── SKILL.md                          # Main skill definition
├── scripts/
│   └── run_codex.sh                  # Safety wrapper: blocks dangerous flags, manages temp files
├── references/
│   ├── CODEX_FLAGS.md                # Complete flag reference for codex exec v0.106.0+
│   ├── PROMPT_PATTERNS.md            # How to construct effective sub-agent prompts
│   ├── PROMPT_ENGINEERING.md         # OpenAI/Codex prompt engineering best practices
│   └── OUTPUT_FORMAT.md              # How to interpret codex output
└── assets/
    └── output-schema-review.json     # JSON schema for structured review responses

# Companion skill (separate, recommended):
review-prompts/
├── SKILL.md                          # Describes available review types + how to get prompt paths
└── prompts/
    ├── code-review.md                # General code quality, logic, style, bugs
    ├── security.md                   # OWASP, injection, auth, secrets, crypto
    ├── plan-review.md                # Structure, logic, completeness, consistency
    ├── architecture.md               # SOLID, coupling, cohesion, extensibility
    ├── performance.md                # N+1, complexity, hot paths, memory
    ├── testing.md                    # Coverage, edge cases, mocking, flaky tests
    ├── typescript.md                 # TS-specific patterns and anti-patterns
    └── python.md                     # Python-specific idioms and patterns
```

### Wrapper Script: `scripts/run_codex.sh`
A bash wrapper that the host agent calls **instead of `codex` directly**. It reduces the host agent's burden by handling boilerplate, enforcing policy, and managing git worktrees — so the agent only needs to focus on the prompt and task type.

> **Important**: The host agent should run the wrapper as a **non-blocking/background** command and poll for completion. The wrapper itself runs `codex` synchronously — this is by design. The host agent's async monitoring capability handles the background execution.

#### What the wrapper does (so the host agent doesn't have to):

| Responsibility | Without Wrapper | With Wrapper |
|---|---|---|
| **Safety enforcement** | Agent must remember not to use dangerous flags | Script blocks them at argument level — impossible to bypass |
| **Default flags** | Agent must add `--ephemeral -o <path>` every time | Script adds them automatically; agent just passes prompt + mode |
| **Temp file handling** | Agent must `mktemp -d`, set permissions, clean up | Script creates secure temp dir, returns path, cleans up on exit |
| **Version gate** | Agent must check version before each run | Script checks once and exits with clear error |
| **Git worktrees** | Agent must create worktree, pass `--cd`, merge, cleanup | Script handles full lifecycle based on `--collision` flag |
| **Web search** | Agent must remember `-c web_search_request=true` syntax | Agent just passes `--web-search` and script translates |

#### Interface

```bash
# Basic usage — agent provides mode and prompt via stdin:
echo "<PROMPT>" | ./scripts/run_codex.sh --mode read-only -

# Write task with high collision confidence (direct):
echo "<PROMPT>" | ./scripts/run_codex.sh --mode write --collision high -

# Write task with medium collision confidence (auto git worktree):
echo "<PROMPT>" | ./scripts/run_codex.sh --mode write --collision medium -

# Enable web search for this spawn:
echo "<PROMPT>" | ./scripts/run_codex.sh --mode read-only --web-search -

# Review with a review prompt file (wrapper loads + prepends it automatically):
echo "<file paths and focus areas>" | ./scripts/run_codex.sh --mode read-only --review-prompt /path/to/review-prompts/prompts/security.md -

# Resume a previous session:
echo "<FOLLOW-UP>" | ./scripts/run_codex.sh --resume -
```

**Wrapper flags** (the ONLY flags the host agent should use):
| Flag | Required | Values | Default | Purpose |
|---|---|---|---|---|
| `--mode` | Yes (unless `--resume`) | `read-only`, `write` | `read-only` | Sets sandbox level |
| `--collision` | Only for `--mode write` | `high`, `medium` | `high` | Controls git worktree isolation |
| `--web-search` | No | *(flag, no value)* | off | Enables web search for this spawn |
| `--review-prompt` | No | file path to a `.md` review prompt | none | Reads the file and prepends it to stdin before passing to codex. Works with any `.md` file — from the companion `review-prompts` skill, user-custom prompts, or any other source |
| `--timeout` | No | `300`, `600`, `1200`, `2400` | `600` (10 min) | Max time before killing the codex process. Host agent selects tier based on task complexity (see Guardrails) |
| `--resume` | No | *(flag, no value)* | off | Resume last session instead of new spawn |
| `--persist` | No | *(flag, no value)* | off | Keep session on disk (required if you plan to `--resume` later) |
| `-` | Yes | *(literal dash)* | — | Read prompt from stdin (must be last argument) |

The host agent must NOT pass raw `codex exec` flags like `--ephemeral`, `-o`, `--full-auto`, or `--sandbox` — the wrapper handles these automatically. Any unrecognized flags are passed through to `codex exec`, but the wrapper will warn about commonly misused ones.

#### Output

The script writes the output file path to **stdout** (one line) so the host agent knows where to read the result:
```
/tmp/codex-abc123/result.txt
```
On worktree mode, it also prints the worktree branch name for merge:
```
/tmp/codex-abc123/result.txt
WORKTREE_BRANCH=codex-work-abc123
```

#### Full Script

```bash
#!/bin/bash
set -euo pipefail

# ========== CONFIGURATION ==========
MIN_VERSION="0.106.0"
MODE="read-only"        # read-only | write
COLLISION="high"         # high | medium (low = don't call this script)
WEB_SEARCH=false
REVIEW_PROMPT=""        # filepath to a .md review prompt (optional)
MAX_TIMEOUT=600          # 10 min default; override with --timeout
RESUME=false
PERSIST=false
PASSTHROUGH_ARGS=()
MAX_PROMPT_CHARS=50000   # guardrail: warn if prompt exceeds ~50K chars

# ========== PARSE ARGUMENTS ==========
while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)        MODE="$2"; shift 2 ;;
    --collision)   COLLISION="$2"; shift 2 ;;
    --web-search)  WEB_SEARCH=true; shift ;;
    --review-prompt) REVIEW_PROMPT="$2"; shift 2 ;;
    --timeout)     MAX_TIMEOUT="$2"; shift 2 ;;
    --resume)      RESUME=true; shift ;;
    --persist)     PERSIST=true; shift ;;
    # --- SAFETY: block dangerous flags (long AND short forms) ---
    --sandbox=danger-full-access|--sandbox=danger*|--dangerously-bypass*)
      echo "BLOCKED: flag '$1' is not permitted by skill policy" >&2
      exit 2 ;;
    -s)
      echo "BLOCKED: -s (--sandbox) is controlled by --mode flag. Use --mode read-only or --mode write." >&2
      echo "Direct sandbox flags are not permitted — the wrapper sets the correct sandbox automatically." >&2
      exit 2 ;;
    # --- HELPFUL ERRORS: catch common mistakes ---
    --ephemeral)
      echo "ERROR: --ephemeral is added automatically by the wrapper. Do not pass it." >&2
      echo "USAGE: echo \"<prompt>\" | ./scripts/run_codex.sh --mode read-only -" >&2
      exit 2 ;;
    --full-auto)
      echo "ERROR: --full-auto is added automatically when --mode write is used." >&2
      echo "USAGE: echo \"<prompt>\" | ./scripts/run_codex.sh --mode write -" >&2
      exit 2 ;;
    -o|--output-last-message)
      echo "ERROR: -o is added automatically by the wrapper. Output path is printed to stdout." >&2
      echo "USAGE: echo \"<prompt>\" | ./scripts/run_codex.sh --mode read-only -" >&2
      exit 2 ;;
    --sandbox|--sandbox=*)
      echo "ERROR: --sandbox is controlled by --mode flag. Use --mode read-only or --mode write." >&2
      exit 2 ;;
    -c)
      # Block sandbox overrides via -c flag (prevents policy bypass)
      if echo "$2" | grep -qi '^sandbox'; then
        echo "BLOCKED: sandbox cannot be overridden via -c. Use --mode read-only or --mode write." >&2
        exit 2
      fi
      PASSTHROUGH_ARGS+=("$1" "$2"); shift 2 ;;
    -)  # Stdin marker — stop parsing, remaining input comes from pipe
      shift; break ;;
    *)             PASSTHROUGH_ARGS+=("$1"); shift ;;
  esac
done

# ========== INPUT VALIDATION ==========
# Validate timeout tier (guardrail: only approved values)
case "$MAX_TIMEOUT" in
  300|600|1200|2400) ;;
  *) echo "ERROR: --timeout must be 300, 600, 1200, or 2400 (seconds). Got: $MAX_TIMEOUT" >&2; exit 2 ;;
esac
# Validate collision value (only for write mode)
if [ "$MODE" = "write" ]; then
  case "$COLLISION" in
    high|medium) ;;
    *) echo "ERROR: --collision must be 'high' or 'medium'. Got: $COLLISION" >&2
       echo "Low confidence = do NOT delegate writes. Use --mode read-only instead." >&2
       exit 2 ;;
  esac
fi

# ========== VERSION GATE ==========
CURRENT=$(codex --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
if [ -z "$CURRENT" ]; then
  echo "ERROR: codex CLI not found. Install: npm i -g @openai/codex" >&2
  exit 127
fi
# Semver comparison: check CURRENT >= MIN_VERSION
version_gte() {
  printf '%s\n%s' "$1" "$2" | sort -V | head -1 | grep -qx "$2"
}
if ! version_gte "$CURRENT" "$MIN_VERSION"; then
  echo "ERROR: codex v$CURRENT found, but v$MIN_VERSION+ is required. Upgrade: npm i -g @openai/codex" >&2
  exit 2
fi

# ========== TEMP DIR ==========
CODEX_TMPDIR=$(mktemp -d)
chmod 700 "$CODEX_TMPDIR"
RESULT_FILE="$CODEX_TMPDIR/result.txt"
cleanup() {
  # Do NOT auto-delete CODEX_TMPDIR — the host agent reads the result file AFTER this script exits.
  # Host agent is responsible for cleanup: rm -rf <path-from-stdout>
  # For worktrees: host must also run git worktree remove + git branch -d after merge/discard.
  :  # no-op — cleanup is the caller's responsibility
}
trap cleanup EXIT

# ========== BUILD CODEX ARGS ==========
CODEX_ARGS=()

if [ "$RESUME" = true ]; then
  CODEX_ARGS+=(exec resume --last)
  CODEX_ARGS+=(-o "$RESULT_FILE")
else
  CODEX_ARGS+=(exec)

  # Default flags based on mode
  case "$MODE" in
    write)     CODEX_ARGS+=(--full-auto --sandbox write-workspace) ;;
    read-only) CODEX_ARGS+=(--sandbox read-only) ;;  # explicit — never rely on user config defaults
    *)         echo "ERROR: unknown mode '$MODE'. Use: read-only | write" >&2; exit 2 ;;
  esac

  # Add --ephemeral unless --persist was passed (needed for future --resume)
  if [ "$PERSIST" = false ]; then
    CODEX_ARGS+=(--ephemeral)
  fi
  CODEX_ARGS+=(-o "$RESULT_FILE")

  # Web search override
  if [ "$WEB_SEARCH" = true ]; then
    CODEX_ARGS+=(-c "web_search_request=true")
  fi

  # Git worktree for medium collision confidence
  if [ "$COLLISION" = "medium" ] && [ "$MODE" = "write" ]; then
    WORKTREE_ID="codex-work-$(uuidgen 2>/dev/null || date +%s)"
    WORKTREE_DIR="/tmp/codex-wt-$WORKTREE_ID"
    if ! git worktree add "$WORKTREE_DIR" -b "$WORKTREE_ID" 2>&1; then
      echo "ERROR: Failed to create git worktree. Check for uncommitted changes or lock files." >&2
      echo "Cannot proceed with --collision medium without worktree isolation." >&2
      echo "Fix: commit or stash changes, then retry. Or use --collision high (no isolation)." >&2
      exit 2
    else
      CODEX_ARGS+=(--cd "$WORKTREE_DIR")
    fi
  fi
fi

# Append any passthrough args
CODEX_ARGS+=("${PASSTHROUGH_ARGS[@]}")

# ========== BUILD PROMPT ==========
PROMPT_FILE="$CODEX_TMPDIR/prompt.txt"
if [ -n "$REVIEW_PROMPT" ]; then
  if [ ! -f "$REVIEW_PROMPT" ]; then
    echo "ERROR: Review prompt file not found: $REVIEW_PROMPT" >&2
    echo "Pass an absolute path to a .md file, e.g.: --review-prompt /path/to/review-prompts/prompts/security.md" >&2
    exit 2
  fi
  # Prepend review prompt, then append stdin content
  cat "$REVIEW_PROMPT" > "$PROMPT_FILE"
  echo "" >> "$PROMPT_FILE"
  echo "--- Additional context from host agent ---" >> "$PROMPT_FILE"
  cat >> "$PROMPT_FILE"  # reads remaining stdin
else
  cat > "$PROMPT_FILE"  # just stdin
fi

# ========== GUARDRAILS ==========
PROMPT_SIZE=$(wc -c < "$PROMPT_FILE")
if [ "$PROMPT_SIZE" -gt "$MAX_PROMPT_CHARS" ]; then
  echo "WARNING: Prompt is very large (${PROMPT_SIZE} chars). Consider trimming context." >&2
fi

# ========== RUN CODEX ==========
# Disable set -e for codex invocation — we need to capture exit code AND print output paths
set +e
# Timeout: kill codex if it exceeds MAX_TIMEOUT seconds
if command -v timeout >/dev/null 2>&1; then
  timeout --kill-after=10 "$MAX_TIMEOUT" codex --color never "${CODEX_ARGS[@]}" < "$PROMPT_FILE"
  EXIT_CODE=$?
else
  # macOS fallback: background codex in new process group + timer
  ( codex --color never "${CODEX_ARGS[@]}" < "$PROMPT_FILE" ) &
  CODEX_PID=$!
  ( sleep "$MAX_TIMEOUT" && kill -- -"$CODEX_PID" 2>/dev/null && echo "TIMEOUT: codex killed after ${MAX_TIMEOUT}s" >&2 ) &
  TIMER_PID=$!
  wait "$CODEX_PID" 2>/dev/null
  EXIT_CODE=$?
  if [ "$EXIT_CODE" -gt 128 ]; then EXIT_CODE=124; fi  # Normalize signal exits to timeout convention
  kill "$TIMER_PID" 2>/dev/null; wait "$TIMER_PID" 2>/dev/null
fi
set -e

# ========== OUTPUT ==========
echo "$RESULT_FILE"
if [ -n "${WORKTREE_ID:-}" ]; then
  echo "WORKTREE_BRANCH=$WORKTREE_ID"
  echo "WORKTREE_DIR=$WORKTREE_DIR"
fi

exit $EXIT_CODE
```

#### Host Agent Workflow with Wrapper

For **high confidence** (most common):
1. Pipe prompt to `run_codex.sh --mode write --collision high -`
2. Read result file path from stdout
3. Read result file, review `git diff`, incorporate changes
4. Clean up: `rm -rf <result-dir>` after reading the file (wrapper does NOT auto-delete)

For **medium confidence** (worktree):
1. Pipe prompt to `run_codex.sh --mode write --collision medium -`
2. Read result file path AND `WORKTREE_BRANCH` from stdout
3. Read result file
4. Review: run `git diff HEAD..{WORKTREE_BRANCH}` (uses current branch, not hardcoded `main`)
5. If approved: run `git merge {WORKTREE_BRANCH}`
6. Cleanup: run `git worktree remove {WORKTREE_DIR}` and `git branch -d {WORKTREE_BRANCH}`

For **read-only** (always safe):
1. Pipe prompt to `run_codex.sh --mode read-only -`
2. Read result file, incorporate findings

> **Critical**: The SKILL.md must present `run_codex.sh` as the **only** way to invoke Codex. The SKILL.md should list only the wrapper's flags (`--mode`, `--collision`, `--web-search`, `--review-prompt`, `--timeout`, `--resume`, `--persist`) as available options — not raw `codex exec` flags. If the host agent tries to use a raw flag that the wrapper handles automatically (like `--ephemeral` or `--full-auto`), the wrapper will reject it with a helpful error message explaining what to do instead. This reduces failure rate by catching mistakes at the script level with actionable guidance.

> **Implementation note**: The bash pseudocode above is for readability. The actual implementation should use **Python 3** (`run_codex.py`) for OS-agnostic behavior — `subprocess.Popen` with `timeout` + `os.killpg` for process group kill solves the macOS/GNU timeout divergence, and `argparse` provides built-in validation. Python 3 is ubiquitous on dev machines.

### Install Location
Per the Agent Skills Open Standard, place in the appropriate skills directory for your host agent:
- **Windsurf**: `~/.codeium/windsurf/skills/codex-subagent/`
- **Claude Code**: `~/.claude/skills/codex-subagent/`
- **Cursor**: `.agents/skills/codex-subagent/` (project-level)
- **Any agent**: `.agents/skills/codex-subagent/` (project-level, universal)

---

## 7. SKILL.md Design

### Trigger Description
```
Delegate coding tasks to OpenAI Codex CLI as a sub-agent. Use when:
- The user asks to delegate work or run a parallel coding task
- A task would benefit from independent exploration with a fresh context
- The user wants a code review or second opinion
- Multiple independent subtasks can be parallelized
- A task requires deep exploration that would bloat the main context
- The user explicitly mentions codex, delegate, sub-agent, or parallel

Do NOT use when:
- The task is trivially simple (< 2 minutes of direct work)
- The task requires access to the host agent's conversation history
- The host agent's built-in tools can accomplish it more efficiently (see Tool Priority below)
- The user is in a rapid iteration loop where delegation latency hurts
- The user explicitly opts out of delegation or says "do it yourself"
- The target code contains sensitive/classified material the user flags

Tool Priority (always check before delegating):
1. Host agent's built-in tools — use these first:
   - Code search: e.g. Windsurf's Fast Context (code_search), grep_search;
     Claude Code's Grep/Glob; Cursor's grep_search
   - Web search: e.g. Windsurf's search_web, read_url_content;
     Claude Code's WebSearch/WebFetch
   - File operations: e.g. read_file, list_dir, find_by_name
2. MCP servers or other integrations if available (e.g. database MCP,
   GitHub MCP, custom tools)
3. Sub-agent delegation via this skill — only when:
   - Fresh context would help (accumulated context is hurting quality)
   - Parallel execution is needed (multiple independent tasks)
   - Task isolation adds value (prototype, spike, risky changes)
   - A second opinion or specialized review is wanted
```

### Prerequisites
- `codex` CLI installed and on PATH
- Authenticated: `codex login status` returns success
- Inside a git repository (or user consents to `--skip-git-repo-check`)
- Sufficient API quota for the target model

### Pre-flight Checks
The host agent should run these checks before first delegation. If a check fails, **offer to fix it** (with user confirmation):

```
1. Check codex is installed:
   Run: which codex
   If missing → Ask user: "Codex CLI not found. Want me to install it? (npm i -g @openai/codex)"
   If user agrees → Run: npm i -g @openai/codex

2. Check version (minimum v0.106.0):
   Run: codex --version
   If below minimum → Ask user: "Codex v{X} found, but v0.106.0+ is needed. Want me to upgrade?"
   If user agrees → Run: npm i -g @openai/codex

3. Check authentication:
   Run: codex login status
   If not logged in → Ask user: "Codex not authenticated. Want me to run 'codex login'?"
   If user agrees → Run: codex login (interactive — user must complete auth flow)

4. Check git repo (optional):
   Run: git rev-parse --git-dir 2>/dev/null
   If not in repo → Warn user, offer --skip-git-repo-check

5. Check wrapper script is available:
   Run: test -x ./scripts/run_codex.sh
   If missing → The skill may not be installed correctly. Check the skill directory structure.
   If not executable → Run: chmod +x ./scripts/run_codex.sh

6. Check model strictness configuration:
   Run: echo $CODEX_SUBAGENT_MODEL_STRICTNESS
   If not set → Ask user: "Model strictness not configured. Options:
     - conservative: always use best model (highest quality, highest cost)
     - balanced (recommended): smart routing based on task complexity
     - aggressive: always try cheapest model first
     Which do you prefer?"
   If user doesn't choose → Default to 'balanced'
   Set: export CODEX_SUBAGENT_MODEL_STRICTNESS=balanced
```

### Core Workflow

#### Operation 1: Delegate Implementation Task
1. Construct prompt (see Section 8)
2. Assess collision confidence (see P6): high, medium, or low
   - If low → do NOT delegate write task; do it yourself or delegate as read-only
3. Run via wrapper (handles `--full-auto`, `--ephemeral`, `-o`, temp dir, worktree):
   ```
   echo "<PROMPT>" | ./scripts/run_codex.sh --mode write --collision high -
   # or for medium confidence:
   echo "<PROMPT>" | ./scripts/run_codex.sh --mode write --collision medium -
   ```
4. Monitor via async polling (see P12 adaptive cadence)
5. Read result file path from wrapper stdout
6. Read result file, review `git diff`, incorporate changes
7. If worktree was used (medium): review diff, merge branch, cleanup worktree

#### Operation 2: Delegate Analysis/Review Task
1. Construct review-focused prompt
2. Run via wrapper:
   ```
   echo "<PROMPT>" | ./scripts/run_codex.sh --mode read-only -
   ```
3. Read result file, incorporate findings

#### Operation 2b: Dedicated Code Review (using `codex exec review`)
1. Determine review scope: uncommitted changes, specific branch, or specific commit
2. Run via wrapper with `review` passthrough:
   ```
   echo "Focus on security and error handling" | ./scripts/run_codex.sh --mode read-only review --uncommitted -
   # or against a branch:
   echo "Focus on performance" | ./scripts/run_codex.sh --mode read-only review --base main -
   ```
3. Read result file, incorporate findings

Note: `review` and its sub-flags (`--uncommitted`, `--base`, `--commit`, `--title`) are passed through to `codex exec review` by the wrapper.

#### Operation 3: Super-Review (Parallel Host Agent + Codex)
See Section 9 for full pattern.

#### Operation 4: Structured Output Task
1. Create JSON schema file for expected output shape
2. Run via wrapper with passthrough `--output-schema`:
   ```
   echo "<PROMPT>" | ./scripts/run_codex.sh --mode read-only --output-schema /path/to/schema.json -
   ```
3. Validate JSON output against schema; retry with clarified format on parse failure
4. Parse JSON result

#### Operation 5: Resume / Multi-Turn Delegation
When the host agent needs to iterate with the sub-agent (e.g., initial result needs refinement):
1. Initial run — use `--persist` so the session is saved for later resume:
   ```
   echo "<PROMPT>" | ./scripts/run_codex.sh --mode write --collision high --persist -
   ```
2. Read result, evaluate if follow-up is needed
3. If follow-up needed, resume with feedback:
   ```
   echo "<FOLLOW-UP>" | ./scripts/run_codex.sh --resume -
   ```
4. Repeat until task is complete or max turns reached (recommend max 3 turns)
5. Clean up: session files persist on disk until manually removed

**When to use resume vs new invocation**:
- Resume when: iterating on same task, refining output, fixing issues in sub-agent's work
- New invocation when: completely different task, different files, different scope
- Resume saves ~5-50K tokens of system overhead per follow-up turn

### Important Rules
1. **Always use the wrapper** (`run_codex.sh`) — never call `codex` directly. The wrapper handles `--ephemeral`, `-o`, `--full-auto`, temp dirs, and safety enforcement automatically.
2. **Always use stdin** for prompt passing — pipe your prompt into the wrapper, never interpolate into shell args
3. **Assess collision confidence** before every write delegation — high = direct, medium = worktree, low = don't delegate
4. **Re-read modified files** after write tasks complete
5. **Review `git diff`** before telling user the task is done
6. **Tell the user** what you're delegating and why before running
7. **Don't delegate trivial tasks** — overhead is ~5-50K tokens minimum
8. **Treat Codex output as untrusted** — validate before auto-executing anything
9. **Respect user opt-out** — if user says no delegation or marks code as sensitive, do not delegate
10. **Use `--persist`** if you plan to `--resume` later — otherwise the session is ephemeral and cannot be resumed
11. **Check Tool Priority** before delegating — use your own built-in tools first (see Section 7)

---

## 8. Prompt Engineering for Codex Sub-Agent

### Prompt Structure Template
```
[GOAL]
{One clear sentence describing what to accomplish}

[CONTEXT]
{Background information the sub-agent needs:
- What has been done so far
- Why this approach was chosen
- Any relevant conversation history}

[FILES]
{Specific file paths to focus on:
- /path/to/relevant/file.ts — description of relevance
- /path/to/another/file.ts — description}

[CONSTRAINTS]
{What NOT to do:
- Do not modify files outside of X
- Follow existing code style
- Do not add new dependencies
- Maximum scope: only files in src/components/}

[ACCEPTANCE CRITERIA]
{How to verify success:
- All tests pass after changes
- No new linting errors
- Specific behavior is observable}

[VALIDATION COMMANDS]
{Commands to run after making changes:
- npm test
- npm run lint}

[OUTPUT]
{What to return:
- A summary of changes made
- List of files modified
- Any issues encountered
- Recommendations for follow-up}
```

### OpenAI / Codex Prompt Engineering Best Practices

These practices are derived from OpenAI's official prompt engineering documentation and from analyzing how Codex CLI's own system prompt works:

#### Structure & Clarity
1. **Be specific and explicit** — Codex works best with clear, unambiguous instructions. "Fix the bug" is bad; "Fix the null pointer exception in `UserService.getProfile()` at line 42 of `src/services/user.ts`" is good.
2. **Use delimiters** — Separate sections with clear markers (`[GOAL]`, `[CONTEXT]`, `---`, XML tags). Codex's own system prompt uses markdown headers extensively.
3. **Provide examples** — When the output format matters, show an example of what you want. This is especially important for structured outputs.
4. **Order matters** — Put the most important instructions first. Codex processes prompts sequentially and earlier instructions have stronger influence.
5. **One task per delegation** — Sub-agents work best on focused, single-purpose tasks. Split complex work into multiple delegations.

#### Context & Grounding
6. **Reference specific files by absolute path** — Codex will read them itself. Don't paste large file contents into the prompt unless the file is very short.
7. **Describe the codebase context** — Architecture, frameworks, patterns in use. Codex starts fresh and has zero context about prior work.
8. **State assumptions explicitly** — "Assume TypeScript strict mode", "The project uses ESM imports", "Tests use Jest".
9. **Include error messages verbatim** — When debugging, paste the exact error. Codex's system prompt says "Do NOT guess or make up an answer."

#### Behavioral Control
10. **Specify what NOT to do** — Codex's system prompt includes many "NEVER" rules. Follow this pattern: "Do NOT modify test files", "Do NOT add inline comments", "Do NOT reformat unchanged code".
11. **Set scope boundaries** — "Only modify files in `src/auth/`". This prevents scope creep and file conflicts with other agents.
12. **Request validation** — "After making changes, run `npm test` and report results." Codex's system prompt encourages self-validation.
13. **Control verbosity** — "Respond in 3-5 bullet points" or "Provide a detailed walkthrough". Codex defaults to concise.

#### Output Control
14. **Use `--output-schema`** for structured data — Forces Codex to return valid JSON matching your schema.
15. **Request file references** — "Include absolute file paths and line numbers for all findings." This makes results actionable.
16. **Ask for confidence levels** — "Rate your confidence (high/medium/low) for each finding." Helps the host agent prioritize.

#### Token Budget Rubric (PE1)
Each `codex exec` invocation costs ~5-50K tokens in system overhead before your prompt is even processed. Budget accordingly:

| Task Type | Target Prompt Size | Trim Priority (keep first) |
|---|---|---|
| Simple search/analysis | < 500 tokens | Goal > Files > Constraints |
| Implementation | 500-2000 tokens | Goal > Constraints > Context > Files |
| Review | 500-1500 tokens | Goal > Files > Constraints > Output format |
| Debug | 500-2000 tokens | Goal > Error message > Files > Context |

Trim order when prompt is too long: drop optional context first, then examples, then reduce file list to most critical.

#### Stdin vs Inline Prompt (PE9)
| Scenario | Method | Example |
|---|---|---|
| Short static prompt (< 200 chars) | Inline argument | `codex exec "summarize README"` |
| Dynamic/templated prompt | Stdin pipe | `echo "$PROMPT" \| codex exec -` |
| Long prompt (> 1000 chars) | File stdin | `codex exec - < /tmp/prompt.txt` |
| Prompt with special chars/quotes | Always stdin | Never risk shell interpretation |
| Multi-line prompt | Heredoc or file | Write to temp file, pipe in |

**Rule**: When the host agent constructs prompts dynamically (which is always), **use stdin**. Never interpolate user-provided or context-derived text into shell command strings.

#### Context Inclusion Decision (PE2)
| Content Type | Include in Prompt? | Rationale |
|---|---|---|
| Exact error message/stack trace | Yes, inline | Codex needs the verbatim error |
| Small code snippet (< 30 lines) | Yes, inline | Faster than file read |
| Full file contents | No, provide path | Codex reads it; saves prompt tokens |
| Conversation history | No, summarize key decisions | Too many tokens, loses focus |
| Architecture/framework info | Yes, 1-2 sentences | Codex has no prior context |
| Diff of recent changes | Yes, if small; path if large | Critical for review tasks |

#### Anti-Patterns to Avoid
- Don't send the entire conversation history — too many tokens, confuses focus
- Don't ask multiple unrelated questions — split into separate invocations
- Don't rely on Codex knowing about the host agent's state — it doesn't
- Don't use vague language like "improve the code" — be specific about what to improve
- Don't include formatting instructions that conflict with Codex's system prompt
- Don't set contradictory constraints (e.g., "be thorough" + "respond in 3 bullets")
- Don't skip validation commands — always ask Codex to verify its own work
- Don't forget failure fallback — instruct what to do if the primary approach fails

### Prompt Examples

#### Example: Implementation
```
[GOAL]
Add input validation to the user registration endpoint.

[CONTEXT]
The Express.js API at src/routes/auth.ts has a POST /register endpoint that
currently accepts any input without validation. We use Zod for validation
elsewhere in the project (see src/schemas/profile.ts for the pattern).

[FILES]
- src/routes/auth.ts — the endpoint to modify
- src/schemas/profile.ts — reference for Zod validation pattern
- src/types/user.ts — User type definition

[CONSTRAINTS]
- Use Zod for validation (already a project dependency)
- Follow the pattern in profile.ts
- Return 400 with validation errors on invalid input
- Do not modify any other endpoints
- Do not add new dependencies

[OUTPUT]
- Summary of changes made
- The Zod schema you created
- Any edge cases you considered
```

#### Example: Code Review
```
[GOAL]
Review the authentication middleware for security vulnerabilities and correctness.

[CONTEXT]
This middleware was recently refactored from session-based to JWT-based auth.
The refactor touched 3 files. We need to verify there are no security gaps.

[FILES]
- src/middleware/auth.ts — the main middleware (REVIEW FOCUS)
- src/utils/jwt.ts — JWT utility functions
- src/routes/protected.ts — routes using the middleware

[CONSTRAINTS]
- This is a review only — do NOT modify any files
- Focus on: token validation, expiry handling, error responses, header parsing
- Check for OWASP top 10 relevant issues

[OUTPUT]
For each finding:
- Severity: critical / high / medium / low
- File and line number
- Description of the issue
- Suggested fix
- Confidence: high / medium / low
```

#### Example: Analysis
```
[GOAL]
Map the data flow from API request to database write for the order creation endpoint.

[FILES]
- src/routes/orders.ts — entry point
- src/services/order.ts — business logic
- src/models/order.ts — database model

[OUTPUT]
- Step-by-step data flow with file:line references
- Any transformations applied to the data
- Validation points
- Error handling gaps
```

#### Example: Debugging
```
[GOAL]
Find and fix the cause of this error in the payment processing flow.

[ERROR]
TypeError: Cannot read properties of undefined (reading 'amount')
    at processPayment (src/services/payment.ts:47:23)
    at async handleCheckout (src/routes/checkout.ts:31:5)

[FILES]
- src/services/payment.ts:47 — where the error occurs
- src/routes/checkout.ts:31 — where it's called from
- src/types/order.ts — Order type definition

[CONTEXT]
This happens when a user checks out with an empty cart. The order object
exists but the items array is empty, so total calculation returns undefined.

[CONSTRAINTS]
- Fix the root cause, not just the symptom
- Add a guard/validation for empty carts
- Do not change the Order type definition

[VALIDATION COMMANDS]
- npm test -- --grep "payment"
- npm test -- --grep "checkout"

[OUTPUT]
- Root cause explanation
- Fix applied with file:line references
- Test results after fix
```

#### Example: Refactoring
```
[GOAL]
Extract the email sending logic from UserService into a dedicated EmailService.

[FILES]
- src/services/user.ts — contains email logic to extract (lines 120-180)
- src/services/ — where new EmailService should be created
- src/tests/user.test.ts — tests that need updating

[CONTEXT]
UserService has grown too large (800+ lines). Email sending (welcome, reset,
notification) should be its own service. The project uses dependency injection
via tsyringe.

[CONSTRAINTS]
- Preserve all existing behavior
- Update all imports and DI registrations
- Update tests to use the new service
- Follow existing service patterns (see src/services/auth.ts for reference)

[VALIDATION COMMANDS]
- npm test
- npm run build

[OUTPUT]
- List of files created/modified
- Summary of the extraction
- Any decisions made about shared types/interfaces
```

#### Example: Test Generation
```
[GOAL]
Write comprehensive unit tests for the OrderService.calculateTotal method.

[FILES]
- src/services/order.ts:calculateTotal — the method to test
- src/tests/services/ — where test file should go
- src/tests/services/auth.test.ts — reference for test patterns

[CONSTRAINTS]
- Use Jest with the existing project configuration
- Follow the pattern in auth.test.ts (describe/it blocks, factory helpers)
- Cover: normal cases, empty input, single item, discounts, tax calculation,
  currency rounding, maximum values, negative quantities
- Mock external dependencies (database, payment gateway)

[ACCEPTANCE CRITERIA]
- All new tests pass
- No existing tests broken
- Coverage for calculateTotal reaches 90%+

[OUTPUT]
- Test file created
- Number of test cases and what they cover
- Any edge cases discovered during test writing
```

---

## 9. Super-Review Pattern

### Concept
When a review is requested, the host agent doesn't just delegate to Codex — it runs its own review in parallel with multiple specialized Codex reviews, then synthesizes everything into one cohesive, **graded** result.

### Why This Pattern
- **Coverage**: Different reviewers catch different issues
- **Depth**: Each Codex instance focuses on one review dimension
- **Speed**: Parallel execution means total time = slowest single review (not sum)
- **Quality**: The host agent's synthesis step filters false positives, ranks by severity, and assigns an overall grade

### The Pattern

#### Step 1: Host Agent's Own Review
The host agent performs its own review using its IDE context, conversation history, and understanding of the user's intent. This review has advantages Codex doesn't:
- Knowledge of the conversation and user's goals
- IDE integration (open files, cursor position, recent edits)
- Understanding of what the user cares about

#### Step 2: Select Review Types (Dynamic)
The host agent selects which review types to run based on **what is being reviewed** and **the user's prompt** — NOT from a fixed predetermined list. The host agent considers:
- What kind of artifact is this? (code, plan, config, docs, PR, etc.)
- What did the user ask to focus on?
- What aspects are most relevant for this artifact?

**Example selections**:
- PR with auth changes → `security`, `code-review`, `testing`
- Architecture plan → `plan-review`, `architecture`
- Python data pipeline → `code-review`, `performance`, `python`
- New API endpoint → `security`, `code-review`, `architecture`

#### Step 3: Launch Sub-Agent Reviews (Non-Blocking)
For each selected review focus, the host agent launches a sub-agent via the wrapper. If the companion `review-prompts` skill is installed, the agent resolves the file path from the skill's install location and passes it via `--review-prompt`:

```
# With review-prompts skill installed (wrapper loads + prepends the prompt file):
REVIEW_DIR="/path/to/review-prompts/prompts"  # resolved from review-prompts SKILL.md
echo "Files: src/auth/*.ts" | ./scripts/run_codex.sh --mode read-only --review-prompt "$REVIEW_DIR/security.md" review --base main -
echo "Files: src/api/users.ts" | ./scripts/run_codex.sh --mode read-only --review-prompt "$REVIEW_DIR/code-review.md" -
echo "New endpoint at src/api/" | ./scripts/run_codex.sh --mode read-only --review-prompt "$REVIEW_DIR/architecture.md" -

# Without review-prompts skill (full prompt via stdin — works fine, just uses more host context):
echo "Review this code for security vulnerabilities, focusing on OWASP top 10..." | ./scripts/run_codex.sh --mode read-only -

# Or point to any custom .md file:
echo "Focus on auth module" | ./scripts/run_codex.sh --mode read-only --review-prompt ./my-custom-review.md -
```

**Why `--review-prompt` matters**: The wrapper reads the file and prepends it to stdin — the full review prompt (~500-2000 tokens each) **never passes through the host agent's context**. The host agent only needs the short description from the review skill's SKILL.md (~50 tokens) to pick the right type.

**Without the companion skill**: The agent can pass a full custom review prompt via stdin, or point `--review-prompt` at any `.md` file. The sub-agent skill works independently.

**Bounded output requirement**: Each review prompt should include output constraints to prevent context overload during synthesis:
- `"Limit findings to top 10 most critical issues"`
- `"Maximum response length: 2000 words"`
- `"Use structured format: one finding per paragraph with severity/file/line/description/fix"`

#### Step 4: Synthesis & Grading
After all reviews complete, the host agent:
1. **Reads** all Codex review outputs
2. **Cross-references** with its own review
3. **De-duplicates** findings (multiple reviewers often catch the same issue)
4. **Validates** each finding — does the host agent agree? Is the finding accurate?
5. **Ranks** by severity and actionability
6. **Filters** false positives (Codex may flag things that are intentional)
7. **Grades** the reviewed artifact:
   - **Overall grade**: A-F (or 1-10) with a one-line justification
   - **Per-dimension grades**: one grade per review focus that was run (e.g., Security: B+, Architecture: A-)
   - Grade should reflect: severity of findings, quantity, how fundamental the issues are
8. **Produces** one cohesive review with:
   - Overall grade and per-dimension grades at the top
   - Findings grouped by severity (critical → low)
   - Each finding with file:line, description, suggested fix, which reviewer(s) caught it
   - Recommended actions prioritized by impact
   - Questions for clarification (if any ambiguities)

### Companion Skill: `review-prompts`

Review prompt files are maintained in a **separate companion skill** (`review-prompts/`). This keeps the sub-agent skill focused on delegation mechanics while making review prompts reusable — they can be used with sub-agents, standalone by the host agent, or by other skills. See [`review-prompts-plan.md`](review-prompts-plan.md) for the full plan.

The companion skill's SKILL.md provides:
- **Short descriptions** of each review type (~50 tokens each) — this is all the host agent needs in its context to pick the right one
- **File path pattern** — the agent resolves `<review-prompts-install-dir>/prompts/<type>.md`
- **Instructions** for using prompts standalone (agent reads the file directly) or with sub-agents (`--review-prompt`)

Available review types (provided by the companion skill):

| Type | File | Focus | Inspired By |
|---|---|---|---|
| `code-review` | `prompts/code-review.md` | General code quality, logic, style, bugs, DRY, error handling | [baz-scm/awesome-reviewers](https://github.com/baz-scm/awesome-reviewers) (8K+ prompts from real OSS reviews) |
| `security` | `prompts/security.md` | OWASP top 10, injection, auth, secrets, crypto | [anthropics/claude-code-security-review](https://github.com/anthropics/claude-code-security-review) |
| `plan-review` | `prompts/plan-review.md` | Structure, logic, completeness, consistency, implementation clarity | [google/eng-practices](https://github.com/google/eng-practices) (20K+), [joelparkerhenderson/architecture-decision-record](https://github.com/joelparkerhenderson/architecture-decision-record) (12K+), DocScope `plan-review` workflow |
| `architecture` | `prompts/architecture.md` | SOLID, coupling, cohesion, extensibility, API contracts | [mehdihadeli/awesome-software-architecture](https://github.com/mehdihadeli/awesome-software-architecture), [sanyuan0704/code-review-expert](https://github.com/sanyuan0704/code-review-expert) (2.1K), [joelparkerhenderson/architecture-decision-record](https://github.com/joelparkerhenderson/architecture-decision-record) (12K+) |
| `performance` | `prompts/performance.md` | N+1, complexity, hot paths, memory, caching | [google/eng-practices](https://github.com/google/eng-practices) (20K+), [analysis-tools-dev/static-analysis](https://github.com/analysis-tools-dev/static-analysis) (14K+), DocScope `review-staged` workflow |
| `testing` | `prompts/testing.md` | Coverage, edge cases, mocking, flaky tests | [goldbergyoni/javascript-testing-best-practices](https://github.com/goldbergyoni/javascript-testing-best-practices) (24K+), [TheJambo/awesome-testing](https://github.com/TheJambo/awesome-testing) (2.1K) |
| `typescript` | `prompts/typescript.md` | Strict null, generics, type narrowing, TS anti-patterns | [baz-scm/awesome-reviewers](https://github.com/baz-scm/awesome-reviewers) language-specific reviewers |
| `python` | `prompts/python.md` | Typing, async, idioms, Pythonic patterns | [baz-scm/awesome-reviewers](https://github.com/baz-scm/awesome-reviewers) language-specific reviewers |
| `java` | `prompts/java.md` | Spring Boot 3+, Java 21+, enterprise patterns, JPA/Hibernate | [google/error-prone](https://github.com/google/error-prone) (7.1K), [spring-projects/spring-boot](https://github.com/spring-projects/spring-boot) (76K+) |
| `scala` | `prompts/scala.md` | Functional patterns, implicits, type classes, effect systems | [scalacenter/scalafix](https://github.com/scalacenter/scalafix) (Scala Center official), [analysis-tools-dev/static-analysis](https://github.com/analysis-tools-dev/static-analysis) (14K+) |
| `javascript` | `prompts/javascript.md` | ES2024+, async, closures, Node.js, framework idioms | [airbnb/javascript](https://github.com/airbnb/javascript) (147K+), [goldbergyoni/nodebestpractices](https://github.com/goldbergyoni/nodebestpractices) (102K+) |

> **Extensible**: Users can add custom `.md` files to the `prompts/` directory or point `--review-prompt` at any file on disk.

#### Example: Code Review Flow
```
User: "Review this PR for me, focus on security"

Host agent (internally):
  1. Reads the PR diff, understands scope (auth changes + new API endpoint)
  2. Picks review focuses: security (user asked), code-review (always for PRs), architecture (new endpoint)
  3. Resolves paths from review-prompts skill install location
  4. Starts own review (in mind, using IDE context)
  5. Simultaneously launches (all non-blocking via wrapper):
     - echo "src/auth/*.ts, src/api/users.ts" | ./scripts/run_codex.sh --mode read-only --review-prompt $RP/security.md review --base main -
     - echo "src/api/users.ts, src/middleware/auth.ts" | ./scripts/run_codex.sh --mode read-only --review-prompt $RP/code-review.md review --uncommitted -
     - echo "New endpoint at src/api/users.ts" | ./scripts/run_codex.sh --mode read-only --review-prompt $RP/architecture.md -
  6. Polls command_status for each until all complete
  7. Reads all output files via read_file
  8. Synthesizes: merges with own findings, de-duplicates, validates
  9. Grades: "Overall: B+ — solid implementation, one medium security finding, clean architecture"
  10. Presents unified graded review to user
```

#### Example: Plan Review Flow
```
User: "Review this implementation plan"

Host agent (internally):
  1. Reads the plan file(s)
  2. Picks review focuses: plan-review (primary), architecture (design elements present)
  3. Starts own review
  4. Launches:
     - echo "docs/my-plan.md — 500 lines, API redesign" | ./scripts/run_codex.sh --mode read-only --review-prompt $RP/plan-review.md -
     - echo "Focus on API contracts in sections 3-5" | ./scripts/run_codex.sh --mode read-only --review-prompt $RP/architecture.md -
  5. Synthesizes and grades: "Overall: B — good structure, missing error handling strategy"
```

Note: `codex exec review` is particularly useful for code reviews — it automatically understands git diff context. For plan reviews and non-code artifacts, use standard `codex exec` with `--review-prompt`.

**Partial failure policy**: If one or more sub-agents fail (timeout, crash) during a parallel super-review, the host agent should:
1. Continue with available results — do not block on failed passes
2. Mark the missing dimension in the synthesis (e.g., "Security review: FAILED — timed out")
3. Optionally retry the failed pass once with a longer timeout tier
4. Never present partial results as a complete review — always disclose what's missing

---

## 10. Skill Operations Reference

### Operation Matrix
| Operation | Wrapper Mode | Collision | Extra Flags | Typical Timeout |
|---|---|---|---|---|
| **Implement** | `--mode write` | Assess (high/medium) | — | 5-10 min |
| **Refactor** | `--mode write` | Assess (high/medium) | — | 5-10 min |
| **Review** | `--mode read-only` | N/A | `--review-prompt <file>` + optional `review --uncommitted` passthrough | 3-5 min |
| **Analyze** | `--mode read-only` | N/A | — | 3-5 min |
| **Debug** | `--mode write` | Assess (high/medium) | — | 5-10 min |
| **Test** | `--mode write` | Assess (high/medium) | — | 5-10 min |
| **Search** | `--mode read-only` | N/A | `--web-search` if external info needed | 2-3 min |
| **Structured** | varies | varies | `--output-schema <file>` passthrough | varies |

### Decision Tree: When to Delegate
```
Pre-check: Can the host agent's built-in tools handle this?
  Yes → Use built-in tools (search, web search, file read, etc.)
  No  → Continue to delegation decision:

Is the task trivially simple (< 2 min)? → Do it yourself
Would a fresh context help? → Delegate
Are there multiple independent subtasks? → Delegate in parallel
Is the user asking for a review? → Super-review pattern
Would deep exploration bloat the context? → Delegate
Does the task need IDE state? → Do it yourself (or include context in prompt)
```

### Common Delegation Use Cases
| Use Case | Operation | Sandbox | Notes |
|---|---|---|---|
| **Code review** | Op 2b | `--mode read-only` + `--review-prompt .../code-review.md` | Pass `review --uncommitted` or `review --base` |
| **Security audit** | Op 2 | `--mode read-only` + `--review-prompt .../security.md` | Wrapper loads OWASP-focused prompt automatically |
| **Test generation** | Op 1 | `--mode write --collision high` | Provide test patterns; new file = high confidence |
| **Refactoring** | Op 1 | `--mode write --collision [assess]` | Scope to specific files |
| **Bug investigation** | Op 2 | `--mode read-only` | Include error + stack trace |
| **Documentation** | Op 1 | `--mode write --collision high` | README, API docs = high confidence (distinct files) |
| **Migration** | Op 1 | `--mode write --collision medium` | Framework/API upgrade often touches many files |
| **Code explanation** | Op 2 | `--mode read-only` | Onboarding, "explain this module" |
| **Prototype / spike** | Op 1 | `--mode write --collision high` | Try approach in isolation |
| **Cross-repo analysis** | Op 2 | `--mode read-only` | Pass `--add-dir` for multiple repos |
| **Dependency impact** | Op 2 | `--mode read-only` | "What breaks if we upgrade X?" |
| **Multi-perspective review** | Op 3 | `--mode read-only` + `--review-prompt` per reviewer | Parallel specialized reviews, dynamically selected |
| **Iterative refinement** | Op 5 | varies + `--persist` | Multi-turn with feedback |

### Model Selection
The host agent should select the model based on task complexity. This is configurable via a **strictness** setting:

| Strictness | Behavior | When to Use |
|---|---|---|
| `conservative` | Always use best model (`gpt-5.3-codex`) | Production code, security-sensitive, user explicitly requests quality |
| `balanced` (default) | Downgrade for tasks the agent is >80% confident are simple | Most everyday work |
| `aggressive` | Always try cheapest viable model first, upgrade on failure | Cost-conscious, high-volume delegation |

**Model routing guidance** (when `balanced`):
| Task Type | Recommended Model | Override Flag |
|---|---|---|
| Simple search/explain | Cheaper/faster model | `-m <model> -c model_reasoning_effort="low"` |
| Standard review/analyze | Default model | `-c model_reasoning_effort="medium"` |
| Complex implement/refactor | Best model | `-c model_reasoning_effort="high"` |
| Critical/security | Best model, high effort | `-c model_reasoning_effort="xhigh"` |

The user can configure this strictness via:
- Environment variable: `CODEX_SUBAGENT_MODEL_STRICTNESS=balanced`
- Or in a config comment in SKILL.md frontmatter
- The host agent should explain its model choice when delegating

---

## 11. Error Handling

### Error Decision Table
| Exit Code | Stderr/Output Contains | Action |
|---|---|---|
| 0 + output exists | — | Success: read output file |
| 0 + output missing/empty | — | Anomaly: retry once, then report to user |
| 1 | "rate limit" | Exponential backoff: wait 30s then 60s, max 2 retries |
| 1 | "auth" / "login" | Offer to run `codex login` for user |
| 1 | "model" / "unavailable" | Retry with fallback model |
| 1 | other | Read output file for partial result; report error |
| 2 | invalid flag/argument | Could be a codex version mismatch (check `codex --version`) OR a wrapper policy rejection (check stderr for "BLOCKED" or "ERROR" messages with usage guidance) |
| 101 | Rust panic / NULL / backtrace | Runtime crash — do NOT retry; report to user with stderr |
| 124 | timeout | Retry with simpler prompt or tell user |
| 127 | — | `codex` not installed — offer to install |
| 137 / SIGKILL | OOM or forced kill | Resource exhaustion — retry with simpler task or report |
| 143 / -15 | — | Terminated; check output file for partial result |
| No exit (hung) | Process exceeds max wait | Force kill process, check partial output, report to user |

**Lesson from our reviews**: The exec reviewer (Codex review #210) crashed with exit 101 (Rust panic) when it tried to run nested `codex exec` inside its own sandbox. Note: this was a Codex-specific sandbox limitation, not a general recursion issue. If the sub-agent has its own sub-agent capabilities, the timeout guardrail bounds any recursive cost. Reviews with web search enabled can take 5x longer — either disable web search for review tasks or increase timeout tier.

### Retry Strategy
- Max 2 retries per delegation
- On timeout: If original run used `--persist`, resume with next timeout tier (e.g., 10min → 20min → 40min). If original was ephemeral (default), retry as a fresh run (not resume) with next tier. If it times out at 40min, report to user — something is likely wrong.
- On rate limit: exponential backoff (30s, 60s)
- On unknown error: don't retry, report to user

---

## 12. What Makes This Different from Existing Skills

| Aspect | shinpr/sub-agents-skills | Our Approach |
|---|---|---|
| **Scope** | Generic multi-CLI Python wrapper | Codex-specific, optimized for any SKILL.md host agent |
| **Agent definitions** | Requires `.agents/` definition files | Inline prompt construction — host agent builds dynamically from conversation context |
| **Output capture** | JSONL stream parsing in Python | `-o` flag for simple file-based output |
| **Prompt guidance** | No guidance on prompt construction | Dedicated prompt patterns + OpenAI best practices reference |
| **Host integration** | Not agent-aware | Generic shell exec / file read / async poll pattern works in any SKILL.md agent |
| **Review pattern** | Not addressed | Super-review: parallel host agent + multi-Codex synthesis |
| **Error handling** | Basic exit code check | Decision table with retry strategies |
| **Prompt engineering** | Not included | OpenAI/Codex best practices reference doc |

---

## 13. Open Questions / Future Enhancements

1. ~~**Session resume**~~: Resolved → Added as Operation 5. Use `codex exec resume --last` without `--ephemeral`.
2. **MCP server mode**: If org enables MCP later, `codex mcp-server` might be a better integration path. Skill should be designed to not preclude this.
3. ~~**Git worktrees for parallel write safety**~~: Resolved → Integrated into P6 collision confidence framework. Worktrees are created automatically by `run_codex.sh` when `--collision medium` is passed. High confidence = direct, Medium = worktree, Low = don't delegate.
4. **Cost tracking**: Can we extract usage stats from JSONL `turn.completed` events to show the user token costs?
5. ~~**Model routing**~~: Resolved → Added configurable model selection with strictness levels in Section 10.
6. **Custom AGENTS.md**: Should the skill create a temporary AGENTS.md with the host agent's context for the Codex sub-agent?
7. **Config file management**: The skill should **never edit `~/.codex/config.toml`** directly (shared config, race conditions with parallel instances). Instead, use `-c key=value` CLI flags for per-invocation overrides. Exception: initial setup if config doesn't exist — confirm with user first.
8. **Subcommand ordering**: The wrapper places default flags (`--ephemeral`, `-o`, `--full-auto`) before passthrough args. If `review` or `resume` subcommands are in passthrough args, they end up after these flags (e.g., `codex exec --ephemeral -o /tmp/result.txt review --uncommitted`). Verify this ordering works correctly with Codex CLI's arg parser during implementation. If not, the wrapper should detect and reorder subcommands.
9. **Review scoping**: Sub-agent reviews should include explicit scope constraints to prevent them from doing things outside their mandate (e.g., web searching excessively, modifying files when asked to review). Recursive sub-agent spawning is allowed — the timeout guardrail bounds cost naturally.

---

## 14. Implementation Checklist

### Core Files
- [ ] Write `SKILL.md` with trigger, prerequisites, workflow, operations
- [ ] Write `scripts/run_codex.sh` wrapper (safety enforcement, version gate)
- [ ] Write `references/CODEX_FLAGS.md` (from Section 4)
- [ ] Write `references/PROMPT_PATTERNS.md` with templates and examples (from Section 8)
- [ ] Write `references/PROMPT_ENGINEERING.md` with OpenAI best practices (from Section 8)
- [ ] Write `references/OUTPUT_FORMAT.md`
- [ ] Create companion `review-prompts/` skill with SKILL.md + 11 prompt files (from Section 9 / [review-prompts-plan](review-prompts-plan.md))
- [ ] Create `assets/output-schema-review.json`
- [ ] Label Section 8 raw `codex exec` examples as "raw reference only — use wrapper in practice" (deferred from Round 3, M2)
- [ ] Add PID suffix to worktree naming fallback (`date +%s-$$`) for concurrent safety (deferred from Round 3, M6)

### Functional Tests
- [ ] Test: basic delegation (read-only analysis)
- [ ] Test: write delegation (implementation with `--full-auto`)
- [ ] Test: parallel reviews (super-review pattern, 3+ concurrent)
- [ ] Test: `codex exec review` subcommand (uncommitted, base branch, commit)
- [ ] Test: `codex exec resume` for multi-turn
- [ ] Test: structured output with `--output-schema`
- [ ] Test: stdin prompt passing (dynamic prompt, special characters)
- [ ] Test: error handling (auth, timeout, rate limit, version mismatch)

### Security & Edge Case Tests
- [ ] Test: `run_codex.sh` blocks `--sandbox danger-full-access` (exit 2)
- [ ] Test: `run_codex.sh` blocks `--dangerously-bypass-approvals-and-sandbox` (exit 2)
- [ ] Test: cancel/abort mid-delegation (verify cleanup)
- [ ] Test: output file missing/empty on exit 0
- [ ] Test: temp file cleanup on all paths
- [ ] Test: sensitive file denylist enforcement
- [ ] Test: version gate pre-flight (old codex version)
- [ ] Test: parallel write conflict detection
- [ ] Test: git worktree creation on `--collision medium`
- [ ] Test: git worktree merge + cleanup workflow
- [ ] Test: collision confidence assessment (high/medium/low examples)
- [ ] Test: cost control (verify max parallel limit enforced)
- [ ] Test: wrapper `--web-search` flag enables per-spawn web search
- [ ] Test: wrapper `--mode write` adds `--full-auto` automatically
- [ ] Test: wrapper `--resume` omits `--ephemeral`
- [ ] Test: wrapper `--persist` omits `--ephemeral` (session saved for future resume)
- [ ] Test: wrapper `--persist` skips temp dir cleanup (files persist for resume)
- [ ] Test: resume multi-turn (Operation 5 — non-ephemeral + resume --last)
- [ ] Test: review scoping (sub-agent can use its own capabilities; timeout bounds cost)
- [ ] Test: wrapper blocks `-s` short form sandbox flag (exit 2)
- [ ] Test: wrapper semver comparison rejects old versions (e.g., v0.50.0)
- [ ] Test: wrapper `--color never` is always passed to codex
- [ ] Test: non-zero codex exit still outputs result file path and worktree info
- [ ] Test: git worktree failure exits 2 with helpful error (no silent downgrade to direct write)
- [ ] Test: wrapper `--review-prompt /path/to/security.md` loads and prepends prompt file
- [ ] Test: wrapper `--review-prompt` with non-existent file exits 2 with helpful error
- [ ] Test: wrapper `--review-prompt` combined with stdin appends additional context
- [ ] Test: wrapper `--timeout 30` kills codex after 30 seconds
- [ ] Test: wrapper prompt size warning fires when prompt > MAX_PROMPT_CHARS
- [ ] Test: timeout kills entire process tree (including any recursive sub-agents)
- [ ] Test: result validation — host agent handles empty/missing output file
- [ ] Test: wrapper rejects raw `--ephemeral` flag (exit 2 with helpful error)
- [ ] Test: wrapper rejects raw `--full-auto` flag (exit 2 with helpful error)
- [ ] Test: wrapper rejects raw `-o` flag (exit 2 with helpful error)
- [ ] Test: wrapper rejects `--collision` with invalid value (exit 2)
- [ ] Test: wrapper rejects `--timeout` with non-tier value (exit 2)
- [ ] Test: wrapper blocks `-c sandbox*` passthrough (exit 2)
- [ ] Test: wrapper `--mode read-only` explicitly passes `--sandbox read-only` to codex
- [ ] Test: wrapper `--mode write` explicitly passes `--sandbox write-workspace` to codex
- [ ] Test: wrapper handles `-` stdin marker (stops arg parsing, reads pipe)
- [ ] Test: host agent cleanup after reading result file (wrapper does NOT auto-delete)
- [ ] Test: write all 11 review prompt files in `review-prompts/prompts/`

---

## 15. Review Audit Trail

This plan was reviewed using the super-review pattern described in Section 9.

### Reviews Conducted
| Reviewer | Type | Findings | Key Impact |
|---|---|---|---|
| **Windsurf (self)** | Comprehensive | W1-W8 | Identified ephemeral/resume contradiction, stdin needs, missing templates |
| **Codex: Gaps** | Gaps & completeness | G1-G18 | Found critical command injection, secret handling, temp file security gaps |
| **Codex: References** | Factual accuracy | R1-R11 | Confirmed v0.106.0 flags accurate, fixed item.completed types, identified missing patterns |
| **Codex: Exec** | CLI correctness | E1-E13 | Ran inside 0.27.0 sandbox — most findings were version artifacts (false positives); E10 (exit code 2) was valid |
| **Codex: Prompt Eng** | Prompt quality | PE1-PE11 | Added token budget rubric, stdin guidance, context inclusion matrix, 4 new templates |
| **Codex: Practical** | Windsurf feasibility | P1-P11 | Found /tmp access risk, md-only skill constraint, polling strategy gaps, context window concerns |
| **Codex: Security** | Adversarial analysis | S1-S9 | Elevated prompt injection to HIGH, added output trust boundary, cost controls, temp file hardening |

### Round 2: Super-Review (Session 5)
After adding glossary, wrapper-as-primary-interface, and consistency fixes, a second super-review was conducted with 6 criteria-specific passes:

| Pass | Focus | Findings | Key Impact |
|---|---|---|---|
| **Security** | Sandbox bypass, script safety, secrets | SEC-1 to SEC-5 | Found `-s` short form bypass (HIGH), `set -e` killing output (HIGH), missing semver comparison, `$TMPDIR` override |
| **Correctness** | Flags, CLI behavior, script logic | COR-1 to COR-7 | `set -e` bug same as SEC-4, subcommand ordering concern for `review` passthrough |
| **Completeness** | Gaps, missing features | GAP-1 to GAP-6 | Missing `--color never`, no pre-flight for wrapper script, output parsing format |
| **Prompt Engineering** | Template quality, examples | PE-1 to PE-4 | Examples all TypeScript (minor), missing validation commands in some templates |
| **Practical Feasibility** | Can agents actually do this? | FEAS-1 to FEAS-3 | Need to clarify wrapper runs sync inside async host command |
| **Consistency** | Terms, refs, cross-references | CON-1 to CON-3 | `--persist` missing from critical note and glossary |

#### Round 2 Synthesis
- **Accepted & Fixed**: SEC-1 (`-s` bypass), SEC-2 (semver gate), SEC-3 (worktree error handling), SEC-4/COR-1 (`set +e` around codex), SEC-5 (rename TMPDIR), GAP-1 (`--color never`), GAP-5 (pre-flight for wrapper), CON-1 (`--persist` in critical note), CON-2 (glossary Persist), COR-7 (open question), FEAS-1 (async note)
- **Deferred**: PE-1 (language diversity in examples — nice-to-have), PE-4 (reviewer prompt examples — for implementation phase)
- **Skipped**: PE-3 (not all tasks need validation commands), GAP-6 ("Our Approach" is fine), FEAS-3 (edge case)

### Round 3: Super-Review (Session 7) — 4 Parallel Codex Sub-Agents
After adding review-prompts companion skill, timeout tiers, recursion allowance, and reference updates, a third super-review was conducted using 4 parallel Codex sub-agents:

| Pass | Focus | Raw Findings | After De-dup |
|---|---|---|---|
| **Consistency** | Cross-file consistency (design + review-prompts + README) | 5 | 5 |
| **Plan Part 1** | Sections 1-9: guardrails, wrapper script, super-review | 10 | 7 (3 merged with security) |
| **Plan Part 2** | Sections 10-15: operations, errors, checklist, audit | 10 | 8 (2 merged with part 1) |
| **Security** | Wrapper script bash: injection, sandbox, timeout, temp files | 9 | 5 (4 merged with plan reviewers) |
| **Total** | | **34 raw** | **19 unique** |

#### Round 3 Synthesis (19 findings)
- **Fixed (15)**: C1 (cleanup race → host-responsible), C2 (sandbox bypass → explicit `--sandbox` + `-c sandbox*` block), H1 (process group kill + `--kill-after` + exit code normalization), H2 (timeout tier validation), H3 (worktree failure → exit 2 not fallback), H4 (collision validation), H5 (resume requires persist clarification), H6 (stdin `-` enforcement), H7 (rate limit alignment), H8 (10 new tests for flag rejection/validation), M1 (HEAD not main), M3 (consistent `review` subcommand in examples), M4 (partial failure policy), Python wrapper note added
- **Deferred (3)**: M2 (Section 8 raw codex examples — labeled as reference, not operational; fix during implementation), M6 (worktree naming race with `date +%s` fallback — acceptable for non-concurrent worktrees), M7 (subcommand ordering — already Open Question #8)
- **Noted (1)**: M5 (design doc ephemeral oversimplification — minor, design doc is intentionally simplified)
- **Low-priority fixes**: L1 (line count updated), L2 (v0.27.0 historical — left as-is, clearly dated in audit trail), L3 (review count wording — left as-is, context is clear)

### Round 1 Synthesis Decisions
- **Accepted**: G1-G11, G14-G18, S1-S7, S9, PE1-PE9, P2-P3, P5-P11, W1-W8, R2, R4, R6, R9-R11
- **Rejected**: G12-G13 (not Windsurf skill spec), P1 (params are standard), E1-E5/E7/E11-E12 (0.27.0 sandbox artifacts)
- **Downgraded**: S8 (repo classification — over-engineered for this scope)
