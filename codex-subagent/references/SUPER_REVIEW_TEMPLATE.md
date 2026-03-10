# Super-Review Output Template

**Re-read this file before presenting super-review results.** Apply the grading rubric, then verify every template section appears in your output.

## Scoring Dimensions

Dimensions are **dynamic** — they match the review types you actually launched. Each review pass (your own + each sub-agent) becomes a dimension to grade.

For example, if you launched security, python, and architecture sub-agents, your dimensions are:
- Self-review (host)
- Security
- Python
- Architecture

Grade only dimensions you actually reviewed. List anything not covered under "Not Reviewed" so the user knows coverage gaps.

## Grading Rubric

| Grade | Criteria |
|-------|----------|
| **A** | No critical/high findings. At most 2 medium findings. Production-ready. |
| **B** | No critical findings. 1-2 high or 3-5 medium findings. Ready with minor fixes. |
| **C** | 1 critical or 3+ high findings. Needs significant fixes before production. |
| **D** | Multiple critical findings. Fundamental issues requiring rework. |
| **F** | Unsafe or non-functional. Do not ship. |

Use `+` / `-` modifiers (e.g., `A-`, `B+`) when between thresholds. Apply per-dimension and overall.

---

# Super-Review: <subject>

## Review Passes

| # | Pass | Source | Status | Findings |
|---|------|--------|--------|----------|
| 1 | Host (self) | <agent name> | ✅ / ❌ | <count> |
| 2 | <review type> | Codex sub-agent | ✅ / ❌ | <count> |
(one row per review pass including your own)

## Findings

### Critical

| Done | ID | Title | Complexity | Sources | Location | Issue | Agreement | Verdict | Fix |
|------|----|----|------------|---------|----------|-------|-----------|---------|-----|
| ✅ / ❌ / (empty) | C1 | <title> | S / M / L / XL | <which passes> | <file:line> | <what's wrong> | AGREE / PARTIAL / DISAGREE + why | ACCEPTED / REJECTED + reason | applied / deferred + reason |

### High

| Done | ID | Title | Complexity | Sources | Location | Issue | Agreement | Verdict | Fix |
|------|----|----|------------|---------|----------|-------|-----------|---------|-----|
| ✅ / ❌ / (empty) | H1 | <title> | S / M / L / XL | <which passes> | <file:line> | <what's wrong> | AGREE / PARTIAL / DISAGREE + why | ACCEPTED / REJECTED + reason | applied / deferred + reason |

### Medium

| Done | ID | Title | Complexity | Sources | Location | Issue | Agreement | Verdict | Fix |
|------|----|----|------------|---------|----------|-------|-----------|---------|-----|
| ✅ / ❌ / (empty) | M1 | <title> | S / M / L / XL | <which passes> | <file:line> | <what's wrong> | AGREE / PARTIAL / DISAGREE + why | ACCEPTED / REJECTED + reason | applied / deferred + reason |

### Low

| Done | ID | Title | Complexity | Sources | Location | Issue | Agreement | Verdict | Fix |
|------|----|----|------------|---------|----------|-------|-----------|---------|-----|
| ✅ / ❌ / (empty) | L1 | <title> | S / M / L / XL | <which passes> | <file:line> | <what's wrong> | AGREE / PARTIAL / DISAGREE + why | ACCEPTED / REJECTED + reason | applied / deferred + reason |

## Per-Dimension Grades

| Dimension | Before | After | Justification |
|-----------|--------|-------|---------------|
| Host (self) | — | <letter> | <brief justification> |
| <review type> | — | <letter> | <brief justification> |
(one row per review pass that was run)

- **Before**: Grade from the initial review round (before fixes). Use `—` on the first round.
- **After**: Grade after fixes have been applied and verified.
- On follow-up review rounds, fill in **Before** with the previous round's **After** grade to show progression.

## Not Reviewed

(list any relevant review types that were NOT run, so the user knows coverage gaps)

## Overall Grade: <before> → <after>

## Changes Applied

(list of fixes made, with file:line references)

## Deferred / Rejected

| ID | Finding | Rationale |
|----|---------|-----------|
(one row per finding not fixed)

## Recommended Follow-Up

(numbered list of improvements for next iteration)

---

## Column Reference

- **Agreement**: Host agent's independent assessment of the sub-agent finding
  - `AGREE` — finding is valid and correctly identified
  - `PARTIAL` — finding has merit but is overstated, understated, or imprecise
  - `DISAGREE` — finding is incorrect, irrelevant, or not applicable
- **Verdict**: What action to take
  - `ACCEPTED` — will be addressed (now or deferred)
  - `REJECTED` — will not be addressed, with reason
- **Done**: Status indicator
  - ✅ — fix has been applied
  - ❌ — rejected / will not be fixed
  - *(empty)* — not yet addressed (deferred or pending)
- **Complexity**: Estimated effort to fix
  - `S` — trivial, single-line or config change
  - `M` — small code change, one file
  - `L` — multi-file change or design decision
  - `XL` — cross-cutting, platform-level, or architectural change
- **Fix**: Disposition
  - `applied` — fixed in this session
  - `deferred` — valid but not fixing now, with reason (e.g., pre-existing, low priority, cross-cutting)
