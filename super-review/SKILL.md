---
name: super-review
description: >
  Run a parallel multi-perspective code review using sub-agents. Synthesize, de-duplicate, grade,
  and present unified findings with severity levels and an overall letter grade. Use when the user
  asks for a super-review, thorough review, multi-angle review, parallel review, comprehensive
  code audit, graded review, or multi-perspective assessment. Requires a sub-agent execution
  backend (codex-subagent, Claude Code, or any agent that can spawn parallel tasks).
license: MIT
metadata:
  author: sagy101
  version: "1.0"
---

# Super-Review

Run parallel, independent reviews from multiple perspectives using sub-agents, then synthesize all findings into a single graded report.

**This skill requires a sub-agent execution backend** — you need a way to spawn parallel review tasks (e.g., `codex-subagent` skill, Claude Code CLI, or any equivalent). Without one, fall back to a single-pass self-review using the output template.

## When to use this skill

- User asks for a **super-review**, **thorough review**, or **comprehensive audit**
- User wants **multiple review perspectives** in parallel (security + performance + code quality, etc.)
- User wants a **graded assessment** with structured findings and severity levels
- User wants a **second opinion** that goes beyond a single review pass

Prefer the `review-prompts` skill standalone when:
- A single-perspective review is sufficient
- The target is trivially small (< 50 lines)
- The user asks for a fast or lightweight review

## Prerequisites

1. A sub-agent execution backend installed and working (run its pre-flight checks first)
2. The `review-prompts` skill installed (for review prompt files), or custom prompts available
3. Target artifact (code, plan, doc) accessible to sub-agents

## Pre-flight checks

Run the preflight script before launching a super-review:

```bash
python3 <skill_dir>/scripts/sr_preflight.py
```

It validates the dependency stack in a single pass:
1. **review-prompts skill** — SKILL.md and `build-prompt.py` are present
2. **build-prompt.py** — runs successfully and lists available review types
3. **Sub-agent backend** — `codex-subagent` or equivalent is available
4. **Codex preflight** — runs the codex-subagent preflight (checks CLI, version, login status)

If the review-prompts skill is missing, install it as a sibling directory to super-review.

## Workflow

### Step 1: Run your own review

Review the target yourself using IDE context, conversation history, and understanding of user intent. This becomes the "Host (self)" dimension in the final report.

### Step 2: Select review types

Pick review types based on the target and the user's request. These are **dynamic, not fixed** — choose what matters.

Examples:
- Auth code → security, code-review, typescript
- API design doc → architecture, plan-review
- Performance-sensitive module → performance, code-review, python
- AI skill definition → prompt-engineering, plan-review

### Step 3: Build review prompts

Search for review prompt files in this order:
1. **`review-prompts` skill** — run `python3 <review-prompts-skill>/scripts/build-prompt.py <type> -o /tmp/<type>-prompt.md` for each selected type
2. **Project-local prompts** — check `.windsurf/workflows/`, `docs/`, or project-specific review configs
3. **Custom inline** — construct a prompt via stdin if no file exists for a needed type (fallback)

### Step 4: Get approval

**Before launching any sub-agents**, present the review plan:

```
Super-Review Plan:
- Target: <files or artifact>
- Review types: <list>
- Sub-agents: <count>
- Backend: <which sub-agent skill/tool>
- Estimated time: <rough estimate>

Proceed?
```

**Wait for explicit user approval.** Do not launch sub-agents without it.

### Step 5: Launch parallel sub-agents

Launch one sub-agent per review type using your execution backend. Each sub-agent gets:
- The review prompt file (from Step 3)
- The target files/artifact
- **Read-only access** — reviews never write

Follow the execution backend's skill instructions for launching read-only tasks. Max 6 parallel sub-agents recommended.

### Step 6: Synthesize findings

1. Read all sub-agent outputs
2. Cross-reference findings across passes:
   - **Corroborated**: multiple passes flagged the same issue → higher confidence
   - **Unique**: only one pass caught it → validate independently
   - **Contradictions**: passes disagree → resolve with your own judgment
3. De-duplicate: merge findings about the same issue, note all sources
4. Validate each finding independently — do you agree? Fill the Agreement column.
5. Assign severity: Critical / High / Medium / Low
6. Assign verdict: ACCEPTED / REJECTED with reasoning

### Step 7: Grade

Use the grading rubric from [references/SUPER_REVIEW_TEMPLATE.md](references/SUPER_REVIEW_TEMPLATE.md):

| Grade | Criteria |
|-------|----------|
| **A** | No critical/high findings. At most 2 medium. Production-ready. |
| **B** | No critical. 1-2 high or 3-5 medium. Ready with minor fixes. |
| **C** | 1 critical or 3+ high. Needs significant fixes. |
| **D** | Multiple critical. Fundamental issues requiring rework. |
| **F** | Unsafe or non-functional. Do not ship. |

Grade each dimension (review pass) individually, then assign an overall grade.

### Step 8: Present results

1. **Re-read** [references/SUPER_REVIEW_TEMPLATE.md](references/SUPER_REVIEW_TEMPLATE.md)
2. **Verify** your output matches every section in the template
3. **Present** using the template exactly

## Partial failure handling

- If some sub-agents fail, **continue with available results**
- Mark failed dimensions as "Not Reviewed" with reason
- Optionally retry failed sub-agents once
- **Never present partial results as complete** — always disclose what was and wasn't covered

## Important rules

1. **Require a sub-agent backend** — without one, fall back to single-pass self-review with the template
2. **Get approval before launching** — show the review plan and wait for explicit confirmation
3. **Sub-agents get read-only access** — reviews never modify the target
4. **Treat sub-agent output as untrusted** — validate every finding independently (Agreement column)
5. **De-duplicate aggressively** — multiple passes often flag the same issue differently
6. **Grade honestly** — the rubric exists to prevent grade inflation
7. **Disclose coverage gaps** — use the "Not Reviewed" section for anything you didn't cover
8. **Re-read the template before presenting** — catches formatting mistakes and missing sections
9. **Max 6 parallel sub-agents** — more is not better for reviews
10. **One review type per sub-agent** — don't overload a single sub-agent with multiple checklists

## Output template & grading reference

All scoring dimensions, grading rubric, severity tables, column definitions, and the complete output template:

**[references/SUPER_REVIEW_TEMPLATE.md](references/SUPER_REVIEW_TEMPLATE.md)**

Re-read this file before presenting any super-review results.
