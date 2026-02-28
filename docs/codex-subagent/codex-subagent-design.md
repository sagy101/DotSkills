# Codex CLI Sub-Agent Skill — Design Document

> Companion to [`codex-subagent-plan.md`](codex-subagent-plan.md) (full implementation plan, ~1690 lines).
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

## Key Design Decisions

**1. Wrapper script as the only interface** — `run_codex.py` sits between the host agent and `codex exec`. It enforces safety (blocks dangerous flags, explicitly sets `--sandbox`), adds defaults (`--ephemeral` unless `--persist`, `--full-auto` for write mode), manages temp files, handles git worktrees, and provides helpful error messages when the agent misuses raw flags. The host agent never calls `codex` directly.

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

## Super-Review Pattern

The host agent doesn't just delegate reviews — it runs its own review AND launches specialized sub-agent reviews in parallel, then synthesizes and **grades** the result.

### How It Works
1. **Host agent reviews** using IDE context, conversation history, user intent
2. **Selects review focuses** based on what's being reviewed and the user's prompt (dynamic, not a fixed list)
3. **Discovers pre-configured prompts** (installed skills first, then project docs/workflows, then custom inline as fallback) and obtains complete prompt files by following the discovered skill's instructions
4. **Launches sub-agents** in parallel, each with a review prompt file loaded via `--review-prompt <filepath>` — the wrapper reads the file and prepends it to stdin, so the full prompt never passes through the host agent's context
5. **Synthesizes**: reads all outputs, cross-references with own review, de-duplicates, validates, filters false positives
6. **Grades**: assigns an overall grade (A-F or 1-10) with per-dimension grades and justification
7. **Presents** unified review grouped by severity with actionable recommendations

### Review Prompt Skills (Generic Pattern)

The sub-agent skill's `--review-prompt` flag accepts **any** complete `.md` file. A separate **review prompt skill** can provide pre-configured review prompts, but this skill has no dependency on any specific one. They connect through the generic `--review-prompt <file>` interface.

A review prompt skill typically provides:
- **A SKILL.md** listing available review types with short descriptions (~50 tokens each)
- **A way to produce complete prompt files** (build script, ready-to-use `.md` files, or both)
- **Instructions** for how to get a complete prompt file for a given review type

**How the host agent connects them:**
- **With a review prompt skill**: Reads its SKILL.md, picks the right type, follows instructions to get a complete `.md` file, passes it via `--review-prompt`
- **Without any review prompt skill**: Full review prompt via stdin, or `--review-prompt ./any-custom-file.md`
- **Adding context to a prompt**: Pipe additional context via stdin — it's appended after the review prompt file

**Prompt discovery order** (super-review Step 2):
1. Installed skills (any skill providing review prompts)
2. Workflows & project docs (`.windsurf/workflows/`, `docs/`, etc.)
3. Custom inline via stdin (fallback)

> The sub-agent skill never imports, calls, or depends on any specific review prompt skill. It only receives a file path.

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
| Max parallel spawns | Host agent (SKILL.md) | 6 |
| Max retries | Host agent (SKILL.md) | 2 |
| Result validation | Host agent | Check: file exists? non-empty? < 1MB? |
| Output trust boundary | Host agent | Never auto-execute sub-agent output |
| Collision confidence gate | Host agent | Low confidence → don't delegate writes |

> **Note on recursion**: If the sub-agent has its own sub-agent capabilities, it's free to use them. The timeout naturally bounds any recursive cost — the entire process is killed when it expires.

---

## Risks at a Glance

| Risk | Severity | Mitigation |
|---|---|---|
| Command injection | Critical | Stdin-only prompts; wrapper script |
| Dangerous sandbox | Critical | Wrapper blocks `danger-full-access` and `-s` at script level |
| Runaway sub-agents | High | Timeout tiers (5-40 min), max parallel (6), process killed on expiry |
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

## Status

**Experimental** — Full plan at [`codex-subagent-plan.md`](codex-subagent-plan.md). Review prompt integration is generic — works with any skill providing `.md` review prompts via `--review-prompt`. All custom terms defined in the plan's Glossary (Section 1). Super-reviewed twice (Round 1: 7 parallel Codex reviews; Round 2: 6 criteria-specific passes, 11 fixes).
