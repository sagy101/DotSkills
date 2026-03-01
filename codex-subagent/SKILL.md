---
name: codex-subagent
description: >
  Delegate coding tasks to OpenAI Codex CLI as a sub-agent. Use when the user asks to delegate work,
  run parallel coding tasks, get a code review or second opinion, explore code with fresh context, or
  when multiple independent subtasks can be parallelized. Use only when the task justifies delegation
  overhead (> 2 min of direct work) and benefits from fresh context or parallelism.
license: MIT
metadata:
  author: sagy101
  version: "1.0"
  codex_min_version: "0.106.0"
compatibility: >
  Requires Codex CLI v0.106.0+ (npm i -g @openai/codex), Python 3.10+, and a git repository.
  POSIX-only (macOS, Linux) — the wrapper uses os.setsid for process group management.
  Works with any SKILL.md-compatible host agent: Windsurf/Cascade, Claude Code, Cursor, Codex, Gemini CLI.
---

# Codex CLI Sub-Agent

Delegate coding tasks to OpenAI's Codex CLI (`codex exec`) as a sub-agent. This gives you (the host agent) sub-agent capabilities — running independent AI agents that work on focused tasks and return results.

## What is the "Host Agent"?

**You — the AI coding agent reading this skill right now — are the host agent.** Whether you are Windsurf/Cascade, Claude Code, Cursor, Codex, Gemini CLI, or any other SKILL.md-compatible agent, this skill is talking to you. When this document says "the host agent should...", it means **you** should.

## When to use this skill

**Tool Priority** — always check before delegating:
1. **Your built-in tools** — use these first (code search, web search, file read, etc.)
2. **MCP servers or integrations** — if available
3. **Sub-agent delegation via this skill** — only when:
   - Fresh context would help (accumulated context is hurting quality)
   - Parallel execution is needed (multiple independent tasks)
   - Task isolation adds value (prototype, spike, risky changes)
   - A second opinion or specialized review is wanted

**Prefer direct work when:**
- The task is trivially simple (< 2 minutes of direct work)
- The task requires your conversation history or IDE state
- Your built-in tools can handle it more efficiently
- The user is in a rapid iteration loop where delegation latency hurts
- The user explicitly opts out or says "do it yourself"
- The target code contains sensitive/classified material the user flags

## Prerequisites

- `codex` CLI installed and on PATH (`npm i -g @openai/codex`)
- Authenticated: `codex login status` returns success
- Inside a git repository (or user consents to `--skip-git-repo-check`)
- Python 3.10+ (for the wrapper script)
- Sufficient API quota for the target model

## Configuration

Model strictness controls how aggressively the host agent routes tasks to cheaper/faster models:

| Strictness | Behavior | When to Use |
|---|---|---|
| `conservative` | Always use best model | Production code, security-sensitive |
| `balanced` (default) | Downgrade when >80% confident task is simple | Most everyday work |
| `aggressive` | Always try cheapest first, upgrade on failure | Cost-conscious, high-volume |

Set via environment variable: `export CODEX_SUBAGENT_MODEL_STRICTNESS=balanced`

Model routing guidance (when `balanced`):
| Task Type | Override Flags |
|---|---|
| Simple search/explain | `-m <cheaper-model> -c model_reasoning_effort="low"` |
| Standard review/analyze | `-c model_reasoning_effort="medium"` |
| Complex implement/refactor | `-c model_reasoning_effort="high"` |
| Critical/security | `-c model_reasoning_effort="xhigh"` |

## Pre-flight checks

Run these checks before the first delegation in a session. If a check fails, offer to fix it (with user confirmation):

```
1. Check codex is installed:
   Run: which codex
   If missing → Ask user: "Codex CLI not found. Install with: npm i -g @openai/codex"

2. Check version (minimum v0.106.0):
   Run: codex --version
   If below minimum → Ask user: "Codex v{X} found, but v0.106.0+ is needed. Upgrade: npm i -g @openai/codex"

3. Check authentication:
   Run: codex login status
   If not logged in → Ask user: "Codex not authenticated. Run 'codex login' to authenticate."

4. Check git repo:
   Run: git rev-parse --git-dir 2>/dev/null
   If not in repo → Warn user, offer --skip-git-repo-check flag

5. Check wrapper script:
   Run: test -f <skill_dir>/scripts/run_codex.py
   If missing → The skill may not be installed correctly. Check the skill directory structure.

6. Check model strictness (optional):
   Run: echo $CODEX_SUBAGENT_MODEL_STRICTNESS
   If not set → Default to 'balanced'. Options: conservative, balanced, aggressive.
```

## Workflow

The wrapper script (`scripts/run_codex.py`) is the **only interface** you should use to invoke Codex. Never call `codex` directly. The wrapper handles safety enforcement, default flags, temp files, git worktrees, and error messages automatically.

### Wrapper interface

```bash
# Basic usage — pipe prompt via stdin:
echo "<PROMPT>" | python3 <skill_dir>/scripts/run_codex.py --mode read-only -

# Write task with high collision confidence:
echo "<PROMPT>" | python3 <skill_dir>/scripts/run_codex.py --mode write --collision high -

# Write task with medium collision confidence (auto git worktree):
echo "<PROMPT>" | python3 <skill_dir>/scripts/run_codex.py --mode write --collision medium -

# Enable web search:
echo "<PROMPT>" | python3 <skill_dir>/scripts/run_codex.py --mode read-only --web-search -

# Review with a review prompt file:
echo "<file paths and context>" | python3 <skill_dir>/scripts/run_codex.py --mode read-only --review-prompt /path/to/security-prompt.md -

# Resume a previous session:
echo "<FOLLOW-UP>" | python3 <skill_dir>/scripts/run_codex.py --resume -
```

### Wrapper flags

| Flag | Required | Values | Default | Purpose |
|---|---|---|---|---|
| `--mode` | Yes (unless `--resume`) | `read-only`, `write` | `read-only` | Sets sandbox level |
| `--collision` | Only for `--mode write` | `high`, `medium` | `high` | Controls git worktree isolation |
| `--web-search` | No | *(flag)* | off | Enables web search for this spawn |
| `--review-prompt` | No | file path | none | Reads file and prepends to stdin before passing to codex |
| `--timeout` | No | `300`, `600`, `1200`, `2400` | `600` | Max seconds before kill |
| `--resume` | No | *(flag)* | off | Resume last session |
| `--persist` | No | *(flag)* | off | Keep session on disk (required for future `--resume`) |
| `--skip-git-repo-check` | No | *(flag)* | off | Run outside a git repository |
| `-` | Yes | *(literal dash)* | — | Read prompt from stdin (must be last argument) |

Wrapper flags are parsed first. Any unrecognized flags are passed through to `codex exec` after a safety scan (see Passthrough Flags below). The wrapper will reject dangerous flags with helpful error messages.

You can also use the standard POSIX `--` separator to explicitly mark the boundary between wrapper flags and passthrough flags:
```bash
echo "<PROMPT>" | python3 <skill_dir>/scripts/run_codex.py --mode read-only -- -m o3 -c model_reasoning_effort="high" -
```

### Passthrough flags

Any flag not listed in the Wrapper Flags table above is forwarded directly to `codex exec` — **unless** it is blocked by the safety scanner. This is how you pass model overrides, config tweaks, feature toggles, and subcommand args.

**Safe passthrough flags:**

| Flag | Example | Purpose |
|---|---|---|
| `-m` / `--model` | `-m o3` | Override model |
| `-c` / `--config` | `-c model_reasoning_effort="high"` | Config override (non-sandbox keys only) |
| `--output-schema` | `--output-schema /path/to/schema.json` | Structured JSON output via schema |
| `-i` / `--image` | `-i screenshot.png` | Attach image(s) to prompt |
| `--enable` / `--disable` | `--enable streaming` | Toggle codex features |
| `-p` / `--profile` | `-p fast` | Load a named config profile |
| `--oss` | `--oss` | Use open-source provider |
| `--local-provider` | `--local-provider ollama` | Specify local model provider |
| `review --uncommitted` | `review --uncommitted` | Review subcommand: uncommitted changes |
| `review --base` | `review --base main` | Review subcommand: diff against branch |

**Blocked flags** — never pass these; the wrapper exits with an error and usage guidance if any are detected:

| Flag | Reason |
|---|---|
| `--sandbox` / `-s` | Controlled by `--mode` |
| `--dangerously-bypass-approvals-and-sandbox` | Not permitted by skill policy |
| `--full-auto` | Controlled by `--mode write` |
| `--ephemeral` | Controlled by `--persist` |
| `-o` / `--output-last-message` | Managed by wrapper (result file) |
| `--json` | stdout is captured internally — output would be lost |
| `--cd` / `-C` / `--add-dir` | Wrapper controls working directory |
| `-c sandbox*` | Sandbox config overrides not permitted |

### Wrapper output

The wrapper prints the output file path to **stdout** (one line):
```
/tmp/codex-abc123/result.txt
```
On worktree mode, it also prints the worktree branch:
```
/tmp/codex-abc123/result.txt
WORKTREE_BRANCH=codex-work-abc123
WORKTREE_DIR=/tmp/codex-wt-codex-work-abc123
```

### Running the wrapper

Always run the wrapper as a **non-blocking/background** command and poll for completion:
1. Launch wrapper as background command (with ~3s initial wait to catch quick failures)
2. Tell the user: "Delegated to Codex, working on X..."
3. Poll at adaptive intervals based on task complexity:
   - Simple (search, explain): 10-30s, max 5 min
   - Standard (review, analyze): 30-60s, max 10 min
   - Complex (implement, refactor): 60-180s, max 20 min
   - Extended (migration, full analysis): 120-300s, max 40 min
4. Read result file path from wrapper stdout
5. Read result file contents
6. Clean up: `rm -rf <result-dir>` (wrapper does NOT auto-delete)

### Timeout tiers

| Tier | Timeout | When to Use |
|---|---|---|
| Short | `--timeout 300` | Simple searches, single-file reviews |
| Standard | `--timeout 600` | Code reviews, analysis, standard implementation |
| Long | `--timeout 1200` | Large refactors, multi-file implementation |
| Extended | `--timeout 2400` | Major migrations, full-codebase analysis |

On timeout: inform user, re-launch with `--persist` + next tier up. If 40min times out, report to user.

## Operations

### Operation 1: Delegate Implementation Task

1. Construct prompt using the template from [PROMPT_PATTERNS.md](references/PROMPT_PATTERNS.md)
2. Assess collision confidence (see Collision Confidence below):
   - High → delegate directly
   - Medium → delegate via git worktree (`--collision medium`)
   - Low → do NOT delegate writes; do it yourself or delegate as read-only
3. Run via wrapper:
   ```
   echo "<PROMPT>" | python3 <skill_dir>/scripts/run_codex.py --mode write --collision high -
   ```
4. Monitor via async polling
5. Read result file, review `git diff`, incorporate changes
6. If worktree: review diff with `git diff HEAD..<WORKTREE_BRANCH>`, merge if approved, cleanup

### Operation 2: Delegate Analysis/Review Task

1. Construct review-focused prompt
2. Run via wrapper:
   ```
   echo "<PROMPT>" | python3 <skill_dir>/scripts/run_codex.py --mode read-only -
   ```
3. Read result file, incorporate findings

### Operation 2b: Dedicated Code Review (using `codex exec review`)

1. Determine review scope: uncommitted changes, specific branch, or specific commit
2. Run via wrapper with `review` passthrough:
   ```
   echo "Focus on security" | python3 <skill_dir>/scripts/run_codex.py --mode read-only review --uncommitted -
   ```
   Or against a branch:
   ```
   echo "Focus on performance" | python3 <skill_dir>/scripts/run_codex.py --mode read-only review --base main -
   ```
3. Read result file, incorporate findings

### Operation 3: Super-Review (Parallel Host + Codex)

When a review is requested, run your own review AND launch specialized sub-agent reviews in parallel, then synthesize.

1. **Your own review**: Use IDE context, conversation history, user intent
2. **Select review types** based on what's being reviewed and user's prompt (dynamic, not fixed)
3. **Discover review prompts** — search in this order:
   a. Installed skills providing review prompts (read their SKILL.md for types and build instructions)
   b. Workflows and project docs (`.windsurf/workflows/`, `docs/`)
   c. Custom inline via stdin (fallback)
4. **Show review plan** — present the selected review types, target files, and sub-agent count to the user. Wait for explicit approval before launching.
5. **Launch sub-agents** in parallel (max 6), each with `--review-prompt <file>`:
   ```
   echo "src/auth/*.ts" | python3 <skill_dir>/scripts/run_codex.py --mode read-only --review-prompt /tmp/sec-prompt.md review --base main -
   echo "src/api/users.ts" | python3 <skill_dir>/scripts/run_codex.py --mode read-only --review-prompt /tmp/cr-prompt.md -
   ```
6. **Synthesize**: Read all outputs, cross-reference with your review, de-duplicate, validate each finding
7. **Grade**: Use the scoring rubric and dimensions below
8. **Present**: Use the host output template below

**Partial failure policy**: If sub-agents fail, continue with available results. Mark missing dimensions. Optionally retry once. Never present partial results as complete.

#### Scoring Dimensions

Dimensions are **dynamic** — they match the review types you actually launched. Each review pass (your own + each sub-agent) becomes a dimension to grade.

For example, if you launched security, python, and architecture sub-agents, your dimensions are:
- Self-review (host)
- Security
- Python
- Architecture

Grade only dimensions you actually reviewed. List anything not covered under "Not Reviewed" so the user knows coverage gaps.

#### Grading Rubric

| Grade | Criteria |
|-------|----------|
| **A** | No critical/high findings. At most 2 medium findings. Production-ready. |
| **B** | No critical findings. 1-2 high or 3-5 medium findings. Ready with minor fixes. |
| **C** | 1 critical or 3+ high findings. Needs significant fixes before production. |
| **D** | Multiple critical findings. Fundamental issues requiring rework. |
| **F** | Unsafe or non-functional. Do not ship. |

Use `+` / `-` modifiers (e.g., `A-`, `B+`) when between thresholds. Apply per-dimension and overall.

#### Host Output Template

Present the synthesized review in this exact structure:

```markdown
# Super-Review: <subject>

## Review Passes
| # | Pass | Source | Status | Findings |
|---|------|--------|--------|----------|
(one row per review pass including your own)

## Findings (by severity)
### Critical
- **<ID>: <title>** — Sources: <which passes>
  Location: <file:line>
  Issue: <what's wrong>
  Verdict: ACCEPTED / REJECTED + reason
  Fix: <applied / deferred + reason>

### High
(same format)

### Medium / Low
(same format, may be abbreviated for Low)

## Per-Dimension Grades
| Dimension | Grade | Justification |
|-----------|-------|---------------|
(one row per review pass that was run)

## Not Reviewed
(list any relevant review types that were NOT run, so the user knows coverage gaps)

## Overall Grade: <letter>

## Changes Applied
(list of fixes made, with file:line references)

## Deferred / Rejected
(table of findings not fixed, with rationale)

## Recommended Follow-Up
(numbered list of improvements for next iteration)
```

### Operation 4: Structured Output Task

1. Create JSON schema file for expected output shape (see [assets/output-schema-review.json](assets/output-schema-review.json) for example)
2. Run via wrapper with `--output-schema` passthrough:
   ```
   echo "<PROMPT>" | python3 <skill_dir>/scripts/run_codex.py --mode read-only --output-schema /path/to/schema.json -
   ```
3. Validate JSON output against schema; retry with clarified format on parse failure

### Operation 5: Resume / Multi-Turn Delegation

1. Initial run with `--persist`:
   ```
   echo "<PROMPT>" | python3 <skill_dir>/scripts/run_codex.py --mode write --collision high --persist -
   ```
2. Read result, evaluate if follow-up needed
3. Resume with feedback:
   ```
   echo "<FOLLOW-UP>" | python3 <skill_dir>/scripts/run_codex.py --resume -
   ```
4. Max 3 turns recommended. Session files persist until manually removed.

**When to resume vs new invocation**:
- Resume: iterating on same task, refining output, fixing sub-agent's work
- New invocation: different task, different files, different scope
- Resume saves ~5-50K tokens of system overhead per follow-up

## Collision Confidence

Before every **write** delegation, assess how likely the sub-agent's work will conflict with your own:

| Level | Confidence | Example | Action |
|---|---|---|---|
| **High** | >80% no conflict | You edit `src/auth/`, delegating `src/payments/` | Delegate directly |
| **Medium** | 40-80% | Both touch files in `src/api/` but different ones | Delegate via git worktree (`--collision medium`) |
| **Low** | <40% | Both need to edit the same file | Do NOT delegate writes — do it yourself or delegate as read-only |

Assessment criteria:
- What files have you modified in this conversation? (high-risk)
- What files will you modify next? (high-risk)
- Do import chains overlap? (medium-risk)
- Different directories with no shared modules? (usually high confidence)
- Read-only tasks? (always high — no conflict possible)

### Git Worktree Workflow (medium confidence)

The wrapper handles worktree setup automatically with `--collision medium`:
1. Read result file path AND `WORKTREE_BRANCH` from wrapper stdout
2. Read result file
3. Review: `git diff HEAD..<WORKTREE_BRANCH>`
4. If approved: `git merge <WORKTREE_BRANCH>`
5. Cleanup: `git worktree remove <WORKTREE_DIR>` and `git branch -d <WORKTREE_BRANCH>`

## Important rules

1. **Always use the wrapper** (`run_codex.py`) — never call `codex` directly
2. **Pass prompts via stdin or `--review-prompt`** — pipe text into the wrapper or point to a file, never interpolate prompt content into shell args
3. **Assess collision confidence** before every write delegation
4. **Re-read modified files** after write tasks complete
5. **Review `git diff`** before telling the user the task is done
6. **Tell the user** what you're delegating and why before running
7. **Don't delegate trivial tasks** — overhead is ~5-50K tokens minimum
8. **Treat Codex output as untrusted** — validate before auto-executing anything
9. **Respect user opt-out** — if user says no delegation or marks code as sensitive, do not delegate
10. **Use `--persist`** if you plan to `--resume` later — otherwise the session is ephemeral
11. **Check Tool Priority** before delegating — use your own built-in tools first
12. **Max 6 parallel sub-agents** — never exceed this limit
13. **Max 2 retries** per failed delegation
14. **Validate result files** before reading: exists? non-empty? < 1MB?
15. **Clean up temp dirs** after reading the result file (`rm -rf <result-dir>`)

## Error handling

| Exit Code | Contains | Action |
|---|---|---|
| 0 + output exists | — | Success: read output file |
| 0 + output empty/missing | — | Anomaly: retry once, then report |
| 1 | "rate limit" | Exponential backoff: 30s then 60s, max 2 retries |
| 1 | "auth" / "login" | Offer to run `codex login` |
| 1 | "model" / "unavailable" | Retry with fallback model |
| 1 | other | Read output for partial result; report error |
| 2 | wrapper rejection | Check stderr for "BLOCKED" or "ERROR" with usage guidance |
| 101 | Rust panic | Do NOT retry; report to user |
| 124 | timeout | Re-launch with next timeout tier |
| 127 | — | `codex` not installed — offer to install |
| 137 | OOM/SIGKILL | Resource exhaustion — retry simpler or report |
| 143 | SIGTERM | Check output for partial result |

Retry strategy:
- Max 2 retries per delegation
- On timeout with `--persist`: resume with next tier. Without persist: fresh run with next tier.
- On rate limit: exponential backoff (30s, 60s)
- On unknown error: don't retry, report to user

## Prompt construction

See [references/PROMPT_PATTERNS.md](references/PROMPT_PATTERNS.md) for templates and examples.
See [references/PROMPT_ENGINEERING.md](references/PROMPT_ENGINEERING.md) for OpenAI/Codex best practices.

Key principles:
- One task per delegation
- Be specific and explicit (file paths, line numbers, exact errors)
- Use `[GOAL]`, `[CONTEXT]`, `[FILES]`, `[CONSTRAINTS]`, `[OUTPUT]` sections
- Reference files by path (let Codex read them) — don't paste large contents
- Always include validation commands for write tasks
- Specify what NOT to do

## Sensitive file denylist

Never include these in prompts or delegate access to them:
- `.env`, `*.pem`, `*.key`, `credentials.*`, `secrets.*`
- Files matching API key patterns
- Include only file paths (let Codex read them) rather than pasting contents

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `codex: command not found` | CLI not installed | `npm i -g @openai/codex` |
| Version too old | Below v0.106.0 | `npm i -g @openai/codex` |
| `401` / auth error | Not logged in | `codex login` |
| Wrapper rejects flag | Raw codex flag used | Use wrapper flags instead (see Wrapper flags table) |
| Timeout | Task too complex for tier | Re-run with next timeout tier |
| Empty output file | Codex failed silently | Check exit code and stderr; retry once |
| Git worktree failure | Uncommitted changes or locks | Commit/stash changes, then retry |
| Rate limit | API quota exceeded | Wait 30-60s, retry max 2 times |
