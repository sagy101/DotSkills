# Super-Review Skill — Design Document

> This document covers **why** the super-review skill exists, the **key design decisions**, and **how it relates** to the rest of the skill ecosystem.

---

## Why This Skill Exists

Single-pass code reviews miss things. Every reviewer — human or AI — has blind spots. Security experts miss performance issues, performance experts miss API design problems, and generalist reviewers catch a bit of everything but go deep on nothing.

The super-review skill solves this by running **multiple independent, specialized reviews in parallel** using sub-agents, then synthesizing all findings into a single graded report. The host agent adds its own review (using IDE context and conversation history that sub-agents don't have), creating a multi-perspective assessment that's more thorough than any single pass.

### Why a Separate Skill?

The super-review was originally part of the `codex-subagent` skill. We split it out because:

1. **The review methodology is backend-agnostic** — the grading rubric, synthesis workflow, output template, and finding tables have nothing to do with Codex CLI specifically. They work with any sub-agent execution backend.
2. **Multiple backends exist** — Codex CLI sub-agents, Claude Code CLI, and future tools all can spawn parallel tasks. Locking the review methodology to one backend limits adoption.
3. **Separation of concerns** — the review *orchestration* (what to review, how to synthesize, how to grade) is a different concern from the sub-agent *execution* (how to spawn, monitor, and collect results).

### The Three-Layer Stack

The super-review sits in the middle of a three-layer architecture:

| Layer | Skill | Responsibility |
|-------|-------|---------------|
| **Criteria** | `review-prompts` | Defines *what* to look for — security checklist, architecture checklist, performance checklist, etc. |
| **Orchestration** | `super-review` | Defines *how* to coordinate parallel reviews, synthesize results, de-duplicate findings, grade, and present |
| **Execution** | `codex-subagent`, Claude Code, etc. | Provides *where* to run sub-agents — spawning, monitoring, collecting results |

Each layer is independently replaceable:
- Swap review prompts without changing orchestration or execution
- Use a different sub-agent backend without changing criteria or orchestration
- Evolve the synthesis/grading methodology without touching the other layers

---

## How It Works

The host agent (you, the AI coding assistant) orchestrates the entire flow:

1. **Self-review** — The host reviews the target using IDE context, conversation history, and understanding of user intent. This becomes the "Host (self)" dimension. Sub-agents don't have this context, so the host's review is always unique.

2. **Review type selection** — Based on the target and user's request, the host picks which review perspectives matter. This is dynamic — auth code gets security + code-review + language-specific; a design doc gets architecture + plan-review.

3. **Prompt discovery** — The host finds review prompt files in priority order:
   - Installed skills providing review prompts (e.g., `review-prompts` skill with `build-prompt.py`)
   - Project-local prompts (`.windsurf/workflows/`, `docs/`)
   - Custom inline prompts as fallback

4. **Approval gate** — The host presents a review plan (target, types, sub-agent count, backend, estimated time) and waits for explicit user approval before launching anything.

5. **Parallel execution** — One sub-agent per review type, all launched in parallel via the execution backend. Each gets a review prompt file and read-only access to the target.

6. **Synthesis** — The host reads all sub-agent outputs and cross-references them with its own review:
   - Corroborated findings (multiple passes flagged it) get higher confidence
   - Unique findings (one pass only) get independent validation
   - Contradictions get resolved by the host's judgment
   - Duplicates get merged with all sources noted

7. **Grading** — Each dimension (review pass) gets a letter grade (A-F), then an overall grade is assigned using the rubric in the output template.

8. **Presentation** — The host re-reads the output template to verify completeness, then presents the full report with per-severity finding tables, per-dimension grades, coverage gaps, and recommended follow-ups.

### Review Prompt Integration (Generic Pattern)

The super-review skill has no dependency on any specific review prompt skill. Sub-agents receive a complete `.md` prompt file — how that file is produced is the criteria layer's concern.

A review prompt skill typically provides:
- A SKILL.md listing available review types with short descriptions
- A way to produce complete prompt files (build script, ready-to-use `.md` files, or both)
- Instructions for how to get a complete prompt file for a given type

The host agent connects the layers:
- **With a review prompt skill**: Reads its SKILL.md, picks types, follows instructions to get complete `.md` files
- **Without one**: Writes custom prompts inline or points to any `.md` file

---

## Key Design Decisions

**1. Backend-agnostic orchestration** — The SKILL.md never mentions specific CLI commands. Step 5 says "launch using your execution backend" and defers to that backend's own skill instructions. This means the super-review works identically whether you're using Codex CLI, Claude Code, or a future tool.

**2. Host review is always included** — The host agent's self-review is a mandatory first step, not optional. The host has context sub-agents don't (conversation history, IDE state, user intent), making it a uniquely valuable perspective that shouldn't be skipped.

**3. Dynamic review types** — Review types are chosen per-target, not from a fixed list. This prevents wasted passes (no point running a Python review on TypeScript code) and lets the host add domain-specific perspectives as needed.

**4. Approval gate before launch** — Sub-agents cost tokens and time. The user sees exactly what will be launched and approves before anything runs. This prevents surprise costs and lets the user adjust the review scope.

**5. Untrusted sub-agent output** — Every sub-agent finding goes through the host's Agreement column (AGREE / PARTIAL / DISAGREE). The host never auto-accepts findings — it validates each one independently. This catches false positives and adds nuance that automated passes miss.

**6. Grading rubric is explicit** — The A-F scale with specific thresholds (e.g., "A = no critical/high, at most 2 medium") prevents grade inflation and makes grades comparable across reviews.

**7. Partial failure resilience** — If some sub-agents fail, the review continues with available results. Failed dimensions are marked "Not Reviewed" so the user knows coverage gaps. This is better than failing the entire review because one perspective timed out.

**8. Preflight script** — `sr_preflight.py` validates Python 3.10+ and the dependency stack (review-prompts skill, sub-agent backend, Codex CLI login status) before any review is launched. Since super-review has no config, credentials, or venv of its own, the preflight focuses on the Python version, dependency presence checks, and delegates Codex validation to the codex-subagent's own preflight script.

---

## Output Template

The complete output template lives in `super-review/references/SUPER_REVIEW_TEMPLATE.md` and includes:

- **Review Passes table** — which passes ran, their source, status, and finding count
- **Per-severity finding tables** (Critical / High / Medium / Low) with columns: Done, ID, Title, Complexity, Sources, Location, Issue, Agreement, Verdict, Fix
- **Per-dimension grades** with Before/After columns for tracking improvement across rounds
- **Not Reviewed section** — explicit coverage gap disclosure
- **Overall grade** with Before → After progression
- **Changes Applied** — list of fixes made
- **Deferred / Rejected** — findings not addressed, with rationale
- **Recommended Follow-Up** — next steps for the user

The template is designed to be re-read by the agent before every presentation, ensuring no sections are missed.

---

## References

- [baz-scm/awesome-reviewers](https://github.com/baz-scm/awesome-reviewers) — 8K+ review prompts from real OSS PR comments
- [anthropics/claude-code-security-review](https://github.com/anthropics/claude-code-security-review) — AI-powered security review pattern
