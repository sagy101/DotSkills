# Codex CLI Sub-Agent Skill — Design Document

> Companion to [`codex-flags.md`](codex-flags.md) (Codex CLI `exec` flag reference).

> This document covers **why** this skill exists and the **key decisions** an implementer or reviewer needs to understand.

---

## Why This Skill Exists

AI coding agents hit limits on long tasks: context bloat degrades quality, there's no parallelism, and no way to get a fresh perspective. Some agents have built-in sub-agents (Claude Code's Task tool, Codex's `spawn_agent`, Cursor's Background Agent), but they're ecosystem-locked — you can't use Claude's Task tool from Windsurf.

This skill gives **any SKILL.md-compatible agent** sub-agent capabilities via Codex CLI. The sub-agent starts fresh, runs independently, can run in parallel, and returns a focused result.

### Why Codex CLI Specifically?

**Any CLI coding agent could work** — the architecture (wrapper → CLI → output file → host reads result) is agent-agnostic. We chose Codex CLI because it has the **lowest friction for programmatic use today**:

| What We Need | Codex CLI | Others (Claude CLI, Gemini CLI, Aider) |
|---|---|---|
| Non-interactive exec mode | `codex exec` — purpose-built | Workarounds or not available |
| File-based output capture | `-o file` — one flag | Stdout redirect (fragile) or N/A |
| Sandbox controls | 3 levels (read-only, workspace-write, danger) | Varies or none |
| Structured JSON output | `--output-schema` — enforced | Not available |
| Built-in code review | `codex exec review` with git integration | Manual prompt engineering |
| Session resume | `codex exec resume` | Not available |

> **Future-proofing**: The wrapper script is the abstraction layer. It could be extended to support `--backend codex|claude|gemini` if another CLI adds equivalent features.

---

## Capabilities

| Capability | Description |
|---|---|
| **Delegate implementation** | Run write tasks (create files, refactor code) in an isolated sub-agent with sandbox controls |
| **Delegate analysis** | Run read-only tasks (explain code, search, summarize) with fresh context |
| **Code review** | Dedicated `codex exec review` with git diff integration (uncommitted, branch-based) |
| **Structured output** | Enforce JSON output shape via `--output-schema` for machine-readable results |
| **Session resume** | Multi-turn delegation with `--persist` / `--resume` for iterative refinement |
| **Collision-aware writes** | Automatic git worktree isolation for medium-confidence write delegations |
| **Model routing** | Configurable model selection and reasoning effort per task complexity |
| **Review prompt integration** | Generic `--review-prompt <file>` interface — works with any skill providing `.md` review prompts |

---

## Key Design Decisions

**1. Wrapper script as the only interface** — `run_codex.py` sits between the host agent and `codex exec`. It enforces safety (blocks dangerous flags, explicitly sets `--sandbox`), adds defaults (`--ephemeral` unless `--persist`, `--full-auto` for write mode), manages temp files, handles git worktrees, prevents SIGHUP termination for safe backgrounding, and provides helpful error messages when the agent misuses raw flags. The host agent never calls `codex` directly.

**2. File-based output over JSONL streaming** — `-o <file>` is universally readable by all host agents. JSONL parsing is complex (881 lines in Codex source) and unnecessary for our use case.

**3. Stdin for all prompts** — Prevents command injection, avoids shell argument limits, eliminates quote escaping issues.

**4. Agent-agnostic design** — The SKILL.md uses abstract capabilities (shell exec, file read, async poll) mapped to concrete tools per agent. Works in Windsurf, Claude Code, Cursor, Codex, Gemini CLI.

**5. Trusted workspace assumption** — Downgrades prompt injection risk to LOW, simplifies security. Focus is on practical safety (sandbox enforcement, temp file cleanup) over adversarial defense.

---

## Decision Tree: When to Delegate

The host agent follows this priority order before every task:

```
1. Can my built-in tools handle this? (code search, web search, file read)
   → YES: Use them. Don't delegate.

2. Can an MCP server or integration handle this?
   → YES: Use it. Don't delegate.

3. Would delegation add value?
   - Fresh context needed? (accumulated bias hurting quality)
   - Parallel execution needed? (multiple independent tasks)
   - Isolation needed? (prototype, spike, risky changes)
   - Second opinion needed? (review, audit)
   → YES to any: Delegate via this skill.

4. Is the task trivially simple (< 2 min of direct work)?
   → YES: Do it yourself. Delegation overhead (~5-50K tokens) isn't worth it.
```

---

## Collision Confidence Framework

Before every **write** delegation, the host agent assesses collision risk:

| Level | Confidence | Example | Action |
|---|---|---|---|
| **High** | >80% no conflict | Host editing `src/auth/`, delegating `src/payments/` | Delegate directly |
| **Medium** | 40-80% | Both touch files in `src/api/` but different ones | Delegate via **git worktree** (wrapper handles automatically with `--collision medium`) |
| **Low** | <40% | Both need to edit the same file | **Do NOT delegate writes** — do it yourself or delegate as read-only |

Assessment criteria:
- What files have you modified in this conversation? (high-risk)
- What files will you modify next? (high-risk)
- Do import chains overlap? (medium-risk)
- Different directories with no shared modules? (usually high confidence)
- Read-only tasks? (always high — no conflict possible)

---

## Guardrails

| Guardrail | Enforced By | Default |
|---|---|---|
| Dangerous sandbox block | Wrapper (script) | Always on, cannot be overridden |
| Scope flag blocking | Wrapper (script) | Blocks `--cd`, `-C`, `--add-dir` passthrough |
| Version gate | Wrapper (script) | Requires codex v0.106.0+ |
| Review prompt validation | Wrapper (script) | Rejects missing/invalid prompt files |
| Empty prompt rejection | Wrapper (script) | Rejects zero-byte prompts |
| Timeout tiers | Wrapper (`--timeout`) | 5 / 10 / 20 / 40 min — host agent selects based on complexity. Resume on timeout with next tier up. |
| Prompt size warning | Wrapper | Warns if > 50K chars |
| Misused flag detection | Wrapper | Helpful errors for raw flags and alternate syntaxes |
| Max parallel spawns | Wrapper (`--max-parallel`) | 6 (PID tracking; override with `--max-parallel N`, not recommended) |
| Max retries | Host agent (SKILL.md) | 2 |
| Result validation | Host agent | Check: file exists? non-empty? < 1MB? |
| Output trust boundary | Host agent | Never auto-execute sub-agent output |
| Output scanning | Host agent | Scan result files for secrets/API keys before surfacing to user |
| Collision confidence gate | Host agent | Low confidence → don't delegate writes |

> **Note on recursion**: If the sub-agent has its own sub-agent capabilities, it's free to use them. The timeout naturally bounds any recursive cost — the entire process is killed when it expires.

---

## Risks at a Glance

| Risk | Severity | Mitigation |
|---|---|---|
| Command injection | Critical | Stdin-only prompts; wrapper script |
| Dangerous sandbox | Critical | Wrapper blocks `danger-full-access` and `-s` at script level |
| Runaway sub-agents | High | Timeout tiers (5-40 min), max parallel (6) via PID tracking, `--status` inspection, stale PID auto-cleanup, SIGHUP handler |
| Secret leakage | High | Denylist paths; path-only references; output scanning |
| File conflicts | Medium | Collision confidence framework (above) |
| Cost overrun | Medium | Max 6 parallel, max 2 retries, timeout tiers |

---

## References

- [baz-scm/awesome-reviewers](https://github.com/baz-scm/awesome-reviewers) — 8K+ review prompts from real OSS PR comments
- [anthropics/claude-code-security-review](https://github.com/anthropics/claude-code-security-review) — AI-powered security review
- [anthropics/skills](https://github.com/anthropics/skills) — Official Agent Skills specification and examples
- [skillmatic-ai/awesome-agent-skills](https://github.com/skillmatic-ai/awesome-agent-skills) — Curated agent skills directory
- **shinpr/sub-agents-skills** — Multi-CLI sub-agent pattern (SKILL.md structure, JSONL processing)
- **openai/codex (Rust source)** — System prompts, orchestrator template, multi-agent collaboration
- **Piebald-AI/claude-code-system-prompts** — Task tool definition, subagent guidance patterns
