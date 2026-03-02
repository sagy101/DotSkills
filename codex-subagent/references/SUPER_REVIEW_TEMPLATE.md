# Super-Review Output Template

**Re-read this file before presenting super-review results.** Verify every section below appears in your output.

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

| ID | Title | Sources | Location | Issue | Agreement | Verdict | Fix |
|----|-------|---------|----------|-------|-----------|---------|-----|
| C1 | <title> | <which passes> | <file:line> | <what's wrong> | AGREE / PARTIAL / DISAGREE + why | ACCEPTED / REJECTED + reason | applied / deferred + reason |

### High

| ID | Title | Sources | Location | Issue | Agreement | Verdict | Fix |
|----|-------|---------|----------|-------|-----------|---------|-----|
| H1 | <title> | <which passes> | <file:line> | <what's wrong> | AGREE / PARTIAL / DISAGREE + why | ACCEPTED / REJECTED + reason | applied / deferred + reason |

### Medium

| ID | Title | Sources | Location | Issue | Agreement | Verdict | Fix |
|----|-------|---------|----------|-------|-----------|---------|-----|
| M1 | <title> | <which passes> | <file:line> | <what's wrong> | AGREE / PARTIAL / DISAGREE + why | ACCEPTED / REJECTED + reason | applied / deferred + reason |

### Low

| ID | Title | Sources | Location | Issue | Agreement | Verdict | Fix |
|----|-------|---------|----------|-------|-----------|---------|-----|
| L1 | <title> | <which passes> | <file:line> | <what's wrong> | AGREE / PARTIAL / DISAGREE + why | ACCEPTED / REJECTED + reason | applied / deferred + reason |

## Per-Dimension Grades

| Dimension | Grade | Justification |
|-----------|-------|---------------|
| Host (self) | <letter> | <brief justification> |
| <review type> | <letter> | <brief justification> |
(one row per review pass that was run)

## Not Reviewed

(list any relevant review types that were NOT run, so the user knows coverage gaps)

## Overall Grade: <letter>

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
- **Fix**: Disposition
  - `applied` — fixed in this session
  - `deferred` — valid but not fixing now, with reason (e.g., pre-existing, low priority, cross-cutting)
