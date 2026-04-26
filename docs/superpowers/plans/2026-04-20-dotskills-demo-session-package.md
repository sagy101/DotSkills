# DotSkills Demo Session Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable DotSkills session package with presenter-facing docs, agent-facing demo scripts, prepared markdown inputs, cleanup guidance, Codex skill installation, and a validated rehearsal flow for the 60-minute live demo.

**Architecture:** The package is documentation-first and lives entirely in the DotSkills repo. One approved design spec drives a small set of reusable markdown assets in `docs/session-plans/` and `demo/`, plus a short validation pass that confirms the installed-skill environment, the chosen repos, and the script flow all line up. The implementation should keep the live demo honest: Jira source markdown is prepared input, Confluence content is generated live by default with a prepared fallback, and cleanup instructions are explicit.

**Tech Stack:** Markdown, shell commands, local git, DotSkills repo docs, Codex local skill directories, Bitbucket/Jira/Confluence/Jenkins/EKS environment checks, Codex sub-agent rehearsal workflow

---

## File Structure

### New Files

- `docs/session-plans/2026-04-20-dotskills-session-plan.md`
  Session master doc for goals, timing, audience framing, Atlassian MCP comparison positioning, and the demo arc.
- `demo/2026-04-20-agent-demo-script.md`
  Agent-facing runbook with system-by-system actions, visible outcomes, pause points, and narration cues.
- `demo/2026-04-20-human-presenter-script.md`
  Presenter-facing script with exact prompts, commentary, fallback lines, and audience emphasis notes.
- `demo/2026-04-20-jira-demo-source.md`
  Prepared markdown input for the live Jira epic and two stories.
- `demo/2026-04-20-confluence-demo-doc.md`
  Prepared fallback Confluence markdown structure used only if the live-generated documentation path needs backup.
- `demo/2026-04-20-pr-review-comment-cheatsheet.md`
  Prepared PR review comments to paste during the human review step.
- `demo/2026-04-20-cleanup-runbook.md`
  Ordered teardown instructions for Jira, Confluence, PR, branches, and local files.
- `demo/2026-04-20-rehearsal-checklist.md`
  Preflight and rehearsal checklist covering connectivity, skills, target systems, and visible outcomes.

### Existing Files To Read During Execution

- `docs/superpowers/specs/2026-04-20-dotskills-demo-session-design.md`
  Approved design source of truth.
- `docs/atlassian-mcp-vs-skills.md`
  Source for sober Atlassian MCP comparison framing.
- `README.md`
  Source for install commands, skill summaries, and product framing.
- `install.sh`
  Source for installer usage shown in the session.

### External Working Context

- `~/cap-projects/cap-onboarding`
  Repo used for the engineering workflow demo and rehearsal target.
- `~/.codex/skills`
  Install target that must contain the required demo skills before rehearsal.

## Task 1: Install Required Skills In Codex

**Files:**
- Read: `README.md`
- Read: `install.sh`
- Verify target dirs: `~/.codex/skills`

- [ ] **Step 1: Inspect the documented install options**

Run:

```bash
sed -n '1,120p' /Users/sashlag/CascadeProjects/DotSkills-projects/bitbucket/README.md
sed -n '1,140p' /Users/sashlag/CascadeProjects/DotSkills-projects/bitbucket/install.sh
```

Expected: The README shows supported install commands and `install.sh` supports `--skill` and `--global`.

- [ ] **Step 2: Install the demo skills into Codex**

Run:

```bash
bash /Users/sashlag/CascadeProjects/DotSkills-projects/bitbucket/install.sh \
  --global \
  --skill jira-manager \
  --skill bitbucket-manager \
  --skill jenkins-manager \
  --skill eks-pod-ops \
  --skill confluence-publisher \
  --skill super-review \
  --skill review-prompts \
  --skill codex-subagent \
  --skill codebase-analyzer
```

Expected: The installer reports successful copies into `~/.codex/skills/...` for the listed skills.

- [ ] **Step 3: Verify the installed skill directories exist**

Run:

```bash
find /Users/sashlag/.codex/skills -maxdepth 2 -name SKILL.md | sort
```

Expected: The output includes:

```text
/Users/sashlag/.codex/skills/bitbucket-manager/SKILL.md
/Users/sashlag/.codex/skills/codebase-analyzer/SKILL.md
/Users/sashlag/.codex/skills/codex-subagent/SKILL.md
/Users/sashlag/.codex/skills/confluence-publisher/SKILL.md
/Users/sashlag/.codex/skills/eks-pod-ops/SKILL.md
/Users/sashlag/.codex/skills/jenkins-manager/SKILL.md
/Users/sashlag/.codex/skills/jira-manager/SKILL.md
/Users/sashlag/.codex/skills/review-prompts/SKILL.md
/Users/sashlag/.codex/skills/super-review/SKILL.md
```

- [ ] **Step 4: Commit the repo changes for the plan/spec only if the worktree policy requires docs commits**

Run:

```bash
git -C /Users/sashlag/CascadeProjects/DotSkills-projects/bitbucket status --short
```

Expected: Only docs/spec/plan files appear. Do not commit yet unless explicitly requested.

## Task 2: Write The Session Master Plan

**Files:**
- Read: `docs/superpowers/specs/2026-04-20-dotskills-demo-session-design.md`
- Read: `docs/atlassian-mcp-vs-skills.md`
- Read: `README.md`
- Create: `docs/session-plans/2026-04-20-dotskills-session-plan.md`

- [ ] **Step 1: Draft the session-plan header and audience framing**

Write this file content:

```markdown
# DotSkills Session Plan

## Session Summary

- Audience: mixed developers and tech leads
- Duration: 60 minutes
- Goal: show a real end-to-end DotSkills workflow that attendees can try themselves later
- Style: live, autonomous, clear, and honest about what is and is not deployed

## Core Message

DotSkills gives coding agents reusable, system-aware workflows so they can operate across Jira, Bitbucket, Jenkins, EKS, Confluence, and multi-agent review with safer defaults and less prompt choreography than raw API or MCP usage.
```

- [ ] **Step 2: Add the session agenda and time budget**

Append this content:

```markdown
## Agenda

1. What Agent Skills are and what DotSkills is
2. Install/setup framing
3. Jira creation from markdown
4. Jira enrichment
5. Code change in `cap-onboarding`
6. Jenkins and EKS visibility
7. Super-review with Codex sub-agents
8. PR comment loop
9. Confluence publish and surgical edit
10. Jira closeout, cleanup, and codebase analysis

## Time Budget

- Intro and framing: 8 min
- Install/setup framing: 4 min
- Jira creation and enrichment: 12 min
- Code change, Jenkins, and EKS: 12 min
- Super-review and fix: 10 min
- PR comment loop, Confluence publish, surgical edit, Jira closeout: 10 min
- Cleanup and Q&A: 4 min
```

- [ ] **Step 3: Add the Atlassian MCP comparison framing**

Append this content:

```markdown
## How To Talk About Atlassian MCP

- Atlassian MCP is broad and useful for low-level product access.
- DotSkills aims higher in the stack: it packages repeatable developer workflows with safety and ergonomics.
- The session should emphasize dry-runs, approval gates, typo-tolerant resolution, markdown-driven workflows, and surgical edit capabilities.
- The session should also acknowledge that Atlassian MCP still has strengths on some Bitbucket administrative and repository-content surfaces.
```

- [ ] **Step 4: Add the live-demo arc and closing notes**

Append this content:

```markdown
## Live Demo Arc

- Start from Jira intent, not from code
- Turn markdown into a real epic and two real stories
- Enrich one story with typo-tolerant assignee lookup and markdown/diagram content
- Implement a small backend change in `cap-onboarding`
- Inspect Jenkins and EKS as real read-only workflow steps
- Run a super-review with Codex sub-agents and a custom business-logic review
- Create a PR, fetch a human review comment, and fix it
- Publish a live-generated Confluence summary and perform a surgical edit
- Transition Jira and clean everything up

## Bonus Skills To Mention

- `sbt-build-test`: safe multi-repo SBT build orchestration
- `skill-creator`: turning one-off scripts into reusable skills
- `codebase-analyzer`: quick repo-level metrics and structure insight
```

- [ ] **Step 5: Verify the file exists and reads cleanly**

Run:

```bash
sed -n '1,260p' /Users/sashlag/CascadeProjects/DotSkills-projects/bitbucket/docs/session-plans/2026-04-20-dotskills-session-plan.md
```

Expected: The file contains the summary, agenda, MCP framing, live demo arc, and bonus skills sections.

## Task 3: Write The Presenter Script

**Files:**
- Read: `docs/superpowers/specs/2026-04-20-dotskills-demo-session-design.md`
- Create: `demo/2026-04-20-human-presenter-script.md`

- [ ] **Step 1: Write the script opening and install framing**

Write this file content:

```markdown
# Human Presenter Script

## Opening

Say:

"DotSkills is a collection of Agent Skills that teach coding agents how to work safely across the systems we actually use, not just inside the IDE."

"Today I’m going to show one real end-to-end loop: Jira, code, Bitbucket, Jenkins, EKS, multi-agent review, Confluence, and cleanup."

"The environment is already prepared so we can focus on the workflow, but I’ll still show the install shape so you can try this later."

## Install Framing

Say:

"Installation is one command. For the demo, I’ve already installed the relevant skills into my Codex environment so we can go straight into the flow."
```

- [ ] **Step 2: Add exact presenter prompts for the Jira and code sections**

Append this content:

```markdown
## Jira Creation Prompt

Ask:

"Use the prepared markdown source to create a new demo epic and two child stories in Jira, then read them back and summarize what you created."

## Jira Enrichment Prompt

Ask:

"Assign the first story to Dor Melamd, add the prepared markdown-rich description and diagram content, then fetch the issue again so we can verify the result."

## Code Change Prompt

Ask:

"Implement the first story on a fresh temporary branch in `~/cap-projects/cap-onboarding`, keep the change small and safe, then commit and push it."
```

- [ ] **Step 3: Add exact presenter prompts for Jenkins, EKS, review, PR, and Confluence**

Append this content:

```markdown
## Jenkins And EKS Prompt

Ask:

"Inspect the CI status for the change, then do a read-only EKS verification step in dev. Narrate clearly that we are not deploying anything as part of this session."

## Super-Review Prompt

Ask:

"Run a super-review on this change using several built-in review prompts plus one custom review that checks whether the implementation actually satisfies the Jira business logic."

## PR Prompt

Ask:

"Create a PR for this branch, then pause so I can add a review comment."

## PR Follow-Up Prompt

Ask:

"Fetch my latest PR comment, fix it, then commit and push the update."

## Confluence Prompt

Ask:

"Create a short markdown summary of what we actually did in this demo, publish it to the Confluence demo target, then pause for a surgical edit request."

## Surgical Edit Prompt

Ask:

"Update the sentence about EKS verification so it clearly says this was a read-only workflow demonstration and no deployment was performed."
```

- [ ] **Step 4: Add the closeout, cleanup, and backup narration**

Append this content:

```markdown
## Closeout Prompt

Ask:

"We’re done. Transition the relevant Jira work, clean up all demo artifacts, and then give me a quick codebase-analyzer snapshot."

## Slow-Moment Narration

Say during waiting:

"Notice that the agent is not just calling raw APIs. It’s following workflows: it knows when to create, verify, summarize, pause for approval, and continue."

"For Jira and Confluence in particular, the differentiator is not CRUD. It’s higher-level tasks like markdown-driven issue creation, fuzzy assignee resolution, and surgical edits."
```

- [ ] **Step 5: Verify the presenter script reads like a stage script**

Run:

```bash
sed -n '1,260p' /Users/sashlag/CascadeProjects/DotSkills-projects/bitbucket/demo/2026-04-20-human-presenter-script.md
```

Expected: The file has direct speaking lines and exact prompts grouped by demo phase.

## Task 4: Write The Agent Demo Script

**Files:**
- Read: `docs/superpowers/specs/2026-04-20-dotskills-demo-session-design.md`
- Create: `demo/2026-04-20-agent-demo-script.md`

- [ ] **Step 1: Write the script header and operating rules**

Write this file content:

```markdown
# Agent Demo Script

## Operating Rules

- Keep the audience oriented: briefly explain what you are about to do before each major step.
- Prefer naming the skill being used when it helps the audience understand the workflow.
- Use real systems and real created artifacts, all prefixed with `DOTSKILLS DEMO 2026-04-20`.
- Be explicit that Jenkins is not a blocking step for the session and EKS is read-only verification only.
- Pause at the PR creation step and the Confluence publish step for presenter interaction.
```

- [ ] **Step 2: Add the execution sequence for Jira through code push**

Append this content:

```markdown
## Phase 1: Jira Intent

1. Confirm the required skills are installed.
2. Read `demo/2026-04-20-jira-demo-source.md`.
3. Create one new demo epic and two child stories in Jira.
4. Fetch the created issues and summarize them.
5. Update the first story:
   - assign it using the intentionally misspelled assignee name supplied by the presenter
   - add markdown-rich content
   - attach diagram content
6. Fetch the updated issue and summarize the visible result.

## Phase 2: Implementation

1. Switch to `~/cap-projects/cap-onboarding`.
2. Create a new temp branch using the session prefix.
3. Implement the small backend change for rejecting empty execution-plan patch requests.
4. Seed one safe business-logic gap: reject the request, but leave the error message too generic.
5. Add or update tests.
6. Commit and push.
```

- [ ] **Step 3: Add the Jenkins, EKS, review, and PR phases**

Append this content:

```markdown
## Phase 3: CI And Operational Visibility

1. Use `jenkins-manager` to inspect the relevant build or job for the pushed branch.
2. Summarize the visible CI state without waiting for full completion.
3. Use `eks-pod-ops` to inspect read-only logs in dev.
4. Say clearly that this is a workflow demonstration and no deployment occurred.

## Phase 4: Super-Review

1. Run `super-review`.
2. Use `review-prompts` for several built-in review lenses.
3. Use `codex-subagent` as the execution backend.
4. Add one custom review asking whether the implementation satisfies the Jira business logic.
5. Present the findings in a way the audience can follow.
6. Fix one finding.
7. Commit and push again.

## Phase 5: PR Collaboration

1. Create a PR in Bitbucket.
2. Pause for the presenter to add a prepared PR comment.
3. Fetch the latest PR comment.
4. Implement the requested update.
5. Commit and push.
```

- [ ] **Step 4: Add the Confluence, cleanup, and bonus phase**

Append this content:

```markdown
## Phase 6: Documentation

1. Generate a short markdown summary of what actually happened in the demo.
2. Publish it to the Confluence demo target.
3. Pause for the presenter’s surgical edit request.
4. Perform the requested surgical edit.

## Phase 7: Closeout

1. Transition the Jira work as directed by the cleanup runbook.
2. Remove or blank the Confluence demo content.
3. Close or decline the PR.
4. Delete the temporary branch.
5. Remove local temporary demo artifacts if they were generated during the session.
6. Run `codebase-analyzer` for a short closing summary.
```

- [ ] **Step 5: Verify the agent script is readable top-to-bottom**

Run:

```bash
sed -n '1,320p' /Users/sashlag/CascadeProjects/DotSkills-projects/bitbucket/demo/2026-04-20-agent-demo-script.md
```

Expected: The file reads as a complete operator script, with clear phases and pause points.

## Task 5: Write The Jira Source And PR Comment Assets

**Files:**
- Create: `demo/2026-04-20-jira-demo-source.md`
- Create: `demo/2026-04-20-pr-review-comment-cheatsheet.md`

- [ ] **Step 1: Write the prepared Jira markdown source**

Write `demo/2026-04-20-jira-demo-source.md` with this content:

```markdown
# DOTSKILLS DEMO 2026-04-20: Safer execution-plan patch validation

## Epic Summary

Improve the execution-plan patch workflow in `cap-onboarding` so obviously invalid patch requests are rejected earlier and the behavior is easy to explain during a live demo.

## Story 1: Reject empty execution-plan patch requests

### Summary

Reject patch requests where all fields are omitted.

### Acceptance Criteria

- `ExecutionPlanPatch(None, None, None)` is rejected
- existing valid patch requests still pass validation
- the rejection is explicit and easy to understand

## Story 2: Add regression coverage for execution-plan patch validation

### Summary

Add regression tests for valid, invalid, and empty patch requests.

### Acceptance Criteria

- valid patch requests still pass
- negative interval or next-start values still fail
- empty patch requests fail
- the tests make the intended behavior obvious to a reviewer
```

- [ ] **Step 2: Write the PR comment cheat sheet**

Write `demo/2026-04-20-pr-review-comment-cheatsheet.md` with this content:

```markdown
# PR Review Comment Cheat Sheet

## Primary Comment

The empty-patch case is rejected now, but the error still looks generic. Can we make the response clearly say that at least one patch field must be provided?

## Backup Comment 1

Can we add a dedicated test that proves an entirely empty patch is rejected?

## Backup Comment 2

The Jira story asked for an explicit failure. The current behavior rejects the request, but I’m not sure the caller gets a clear enough reason.
```

- [ ] **Step 3: Verify both files**

Run:

```bash
sed -n '1,220p' /Users/sashlag/CascadeProjects/DotSkills-projects/bitbucket/demo/2026-04-20-jira-demo-source.md
sed -n '1,220p' /Users/sashlag/CascadeProjects/DotSkills-projects/bitbucket/demo/2026-04-20-pr-review-comment-cheatsheet.md
```

Expected: The Jira source contains one epic and two stories with acceptance criteria; the cheat sheet contains one primary and two backup comments.

## Task 6: Write The Confluence Fallback, Cleanup, And Rehearsal Assets

**Files:**
- Create: `demo/2026-04-20-confluence-demo-doc.md`
- Create: `demo/2026-04-20-cleanup-runbook.md`
- Create: `demo/2026-04-20-rehearsal-checklist.md`

- [ ] **Step 1: Write the fallback Confluence doc template**

Write `demo/2026-04-20-confluence-demo-doc.md` with this content:

```markdown
# DOTSKILLS DEMO 2026-04-20 Session Summary

## What We Demonstrated

- Jira issue creation from markdown
- typo-tolerant assignee update
- markdown and diagram content flowing into Jira
- a small backend code change and PR workflow
- Jenkins visibility and read-only EKS verification
- multi-agent review with a custom business-logic lens
- Confluence publishing and surgical edit

## Install Shape

```bash
npx skills add git@bitbucket.org:firelayers/dotskills.git -g -y
```

## Demo Flow

```mermaid
flowchart LR
  A["Markdown plan"] --> B["Jira epic and stories"]
  B --> C["cap-onboarding change"]
  C --> D["Bitbucket PR"]
  D --> E["Jenkins visibility"]
  E --> F["EKS read-only verification"]
  F --> G["Super-review"]
  G --> H["Confluence publish"]
  H --> I["Cleanup"]
```

## EKS Note

We used EKS logs to verify the change in dev after the CI step.
```

- [ ] **Step 2: Write the cleanup runbook**

Write `demo/2026-04-20-cleanup-runbook.md` with this content:

```markdown
# Cleanup Runbook

## Cleanup Order

1. Transition or close the demo Jira issues according to the live session decision
2. Delete or blank the Confluence demo page
3. Close or decline the PR
4. Delete the temporary Bitbucket branch
5. Delete the temporary local branch
6. Remove any generated local demo notes if they were created during rehearsal
7. Verify no `DOTSKILLS DEMO 2026-04-20` artifacts remain unexpectedly active

## Verification Checklist

- Jira epic and stories are no longer active
- Confluence page is deleted or blanked
- PR is closed
- remote branch is deleted
- local branch is deleted
```

- [ ] **Step 3: Write the rehearsal checklist**

Write `demo/2026-04-20-rehearsal-checklist.md` with this content:

```markdown
# Rehearsal Checklist

## Environment

- Codex demo skills are installed
- Jira connectivity works
- Bitbucket connectivity works
- Confluence connectivity works
- Jenkins connectivity works
- EKS connectivity works
- Codex sub-agent flow is available

## Demo Preconditions

- `~/cap-projects/cap-onboarding` is available
- the target assignee resolves with a small typo
- a PR can be created from a temporary branch
- the Confluence target is writable
- the Jira board is writable

## Rehearsal Success Criteria

- Jira issues are created from markdown
- issue enrichment is visible and readable
- the code change is small and believable
- the seeded issue is caught by review
- the prepared PR comment still makes sense
- the surgical edit is visually obvious
- cleanup fully removes the demo artifacts
```

- [ ] **Step 4: Verify the three files**

Run:

```bash
sed -n '1,260p' /Users/sashlag/CascadeProjects/DotSkills-projects/bitbucket/demo/2026-04-20-confluence-demo-doc.md
sed -n '1,220p' /Users/sashlag/CascadeProjects/DotSkills-projects/bitbucket/demo/2026-04-20-cleanup-runbook.md
sed -n '1,220p' /Users/sashlag/CascadeProjects/DotSkills-projects/bitbucket/demo/2026-04-20-rehearsal-checklist.md
```

Expected: The Confluence fallback doc contains headings, bullets, an install command, a Mermaid diagram, and the editable EKS sentence. The cleanup and rehearsal docs should read as operational checklists.

## Task 7: Validate Plan Coverage And Repo State

**Files:**
- Read: `docs/superpowers/specs/2026-04-20-dotskills-demo-session-design.md`
- Read: all files created in Tasks 2-6

- [ ] **Step 1: Confirm every requested asset exists**

Run:

```bash
ls -1 /Users/sashlag/CascadeProjects/DotSkills-projects/bitbucket/docs/session-plans
ls -1 /Users/sashlag/CascadeProjects/DotSkills-projects/bitbucket/demo
```

Expected: The new session plan and the six demo assets appear in the appropriate directories.

- [ ] **Step 2: Confirm the content covers the approved spec**

Run:

```bash
rg -n "Atlassian MCP|super-review|codex-subagent|surgical edit|cleanup|EKS|Jira|Confluence|codebase-analyzer" \
  /Users/sashlag/CascadeProjects/DotSkills-projects/bitbucket/docs/session-plans/2026-04-20-dotskills-session-plan.md \
  /Users/sashlag/CascadeProjects/DotSkills-projects/bitbucket/demo/2026-04-20-agent-demo-script.md \
  /Users/sashlag/CascadeProjects/DotSkills-projects/bitbucket/demo/2026-04-20-human-presenter-script.md \
  /Users/sashlag/CascadeProjects/DotSkills-projects/bitbucket/demo/2026-04-20-confluence-demo-doc.md \
  /Users/sashlag/CascadeProjects/DotSkills-projects/bitbucket/demo/2026-04-20-cleanup-runbook.md
```

Expected: Matches appear for all core flows and differentiators requested in the spec.

- [ ] **Step 3: Review git status before rehearsal work**

Run:

```bash
git -C /Users/sashlag/CascadeProjects/DotSkills-projects/bitbucket status --short
```

Expected: The newly created docs are listed. No unrelated files should be modified by the session-package work.

## Task 8: Rehearsal Readiness And Validation Notes

**Files:**
- Read: `demo/2026-04-20-agent-demo-script.md`
- Read: `demo/2026-04-20-human-presenter-script.md`
- Read: `demo/2026-04-20-rehearsal-checklist.md`

- [ ] **Step 1: Smoke-check the target repo and branch context**

Run:

```bash
git -C /Users/sashlag/cap-projects/cap-onboarding rev-parse --is-inside-work-tree
git -C /Users/sashlag/cap-projects/cap-onboarding branch --show-current
git -C /Users/sashlag/cap-projects/cap-onboarding remote -v
```

Expected: `cap-onboarding` is a usable git repo with a Bitbucket remote.

- [ ] **Step 2: Prepare the sub-agent rehearsal prompt**

Write this exact rehearsal brief into the execution session or sub-agent handoff:

```text
Follow the agent demo script at /Users/sashlag/CascadeProjects/DotSkills-projects/bitbucket/demo/2026-04-20-agent-demo-script.md and simulate the human prompts from /Users/sashlag/CascadeProjects/DotSkills-projects/bitbucket/demo/2026-04-20-human-presenter-script.md. Validate flow order, pause points, and whether the seeded review issue and cleanup steps are clear. Do not perform production-impacting actions. Report any ambiguity, missing prerequisites, or steps likely to confuse an audience.
```

- [ ] **Step 3: Run the rehearsal or record the exact blocker**

Run either:

```bash
printf '%s\n' "Manual or sub-agent rehearsal required; see demo/2026-04-20-rehearsal-checklist.md"
```

or the available sub-agent execution path for this environment.

Expected: Either a real rehearsal result or a precise list of blockers such as missing credentials, inaccessible systems, or unresolved skill installation issues.

- [ ] **Step 4: Commit documentation only after validation if the user wants the package saved**

Run:

```bash
git -C /Users/sashlag/CascadeProjects/DotSkills-projects/bitbucket status --short
```

Expected: Only the intended markdown package files are staged or pending. Do not commit automatically unless requested.

## Self-Review

### Spec Coverage

- Session plan file: covered in Task 2
- Agent script: covered in Task 4
- Human presenter script: covered in Task 3
- Jira markdown source: covered in Task 5
- Confluence fallback and live-generation guidance: covered in Task 6 and Task 4
- PR comment cheat sheet: covered in Task 5
- Cleanup runbook: covered in Task 6
- Rehearsal checklist and validation: covered in Task 6 and Task 8
- Codex skill installation prerequisite: covered in Task 1

### Placeholder Scan

No `TODO`, `TBD`, or “implement later” placeholders should remain in the deliverables. Any rehearsal blocker must be reported explicitly with the exact missing dependency or inaccessible system.

### Type And Naming Consistency

- Shared session prefix: `DOTSKILLS DEMO 2026-04-20`
- Session-plan path: `docs/session-plans/2026-04-20-dotskills-session-plan.md`
- Demo assets all use the `demo/2026-04-20-*` naming pattern
- Rehearsal references point to the exact generated file paths
