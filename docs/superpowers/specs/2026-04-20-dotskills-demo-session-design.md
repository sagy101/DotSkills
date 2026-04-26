# DotSkills Demo Session Design

## Summary

This document defines a reusable live demo package for a 60-minute DotSkills session aimed at a mixed audience of developers and tech leads. The session must show three things clearly:

1. What DotSkills is and why Agent Skills matter
2. Why the skills are safer and more workflow-oriented than raw Jira/Confluence/Bitbucket MCP tool use
3. How an attendee could try this themselves after the session

The demo should feel highly autonomous: the presenter should be able to tell the agent to proceed, and the agent should carry the workflow across systems with minimal manual steering. The audience should see a real end-to-end developer loop across Jira, code, Bitbucket, Jenkins, EKS, review, Confluence, and cleanup.

## Audience And Goals

### Audience

- Mixed developers and tech leads
- Interested in both practical workflows and safety/operational credibility
- Most important outcome: attendees should feel they can try one or two workflows themselves after the session

### Primary Goals

- Show real systems, not mocks
- Keep changes non-production-impacting and reversible
- Demonstrate high-value workflow differentiation, especially for Jira and Confluence
- Make the session feel clear, autonomous, and repeatable
- Leave no demo artifacts active after the session

## Session Constraints

- Duration: 60 minutes
- Install/setup should be shown briefly, but the environment should already be prepared
- No real production deployment
- Jenkins step should be real, but the session does not depend on waiting for Jenkins to finish
- EKS step should be real and read-only, but the presenter will explicitly state that the code was not deployed and the EKS step is a workflow demonstration only
- Jira epic and stories should be created live from scratch under a new demo epic
- The main implementation should be a small backend code change in `cap-onboarding`
- The initial implementation should contain one safe seeded issue so the review loop reliably finds something meaningful to fix

## Demo Systems And Scope

### Live Systems

- Jira board: `API` board
- Confluence target: `Deleted` area/page
- Bitbucket repo for DotSkills: used for install/setup framing and Atlassian MCP comparison framing
- Bitbucket repo for engineering loop: `~/cap-projects/cap-onboarding`
- Jenkins: CI environment for `cap-onboarding`
- EKS: dev environment, read-only verification only

### Demo Object Strategy

All created items are real system objects created live during the session, but they are demo-only artifacts with no real product or release purpose. They should all use a shared session prefix such as:

`DOTSKILLS DEMO 2026-04-20`

This includes:

- Jira epic and stories
- temporary branch
- pull request
- Confluence page/content
- local markdown source files created for the session

## Session Narrative

The session should use one hero flow plus a small closing bonus:

1. Explain what Agent Skills are and what DotSkills provides
2. Briefly show install/setup so the session still feels adoptable
3. Run one coherent live workflow:
   - Jira intent
   - code change
   - CI/status visibility
   - operational visibility
   - multi-agent review
   - PR comment loop
   - Confluence publish
   - Jira closeout
   - cleanup
4. Close with `codebase-analyzer` as a bonus meta skill
5. Mention `sbt-build-test` and `skill-creator` verbally rather than forcing them into the live path

## Positioning Against Atlassian MCP

The session should not market against Atlassian MCP in a fluffy way. The positioning should be:

- Atlassian MCP provides broad low-level tool access
- DotSkills provides opinionated developer workflows on top of those systems
- The value is not generic AI magic; it is workflow ergonomics and safety:
  - dry-runs
  - approval gates
  - typo-tolerant resolution
  - markdown-driven issue/page workflows
  - richer diff/update/edit flows
  - safer operational defaults

The session should explicitly acknowledge that Atlassian MCP still has strengths on some Bitbucket admin and repository primitives.

## Skills Covered

### Live In The Main Flow

- `jira-manager`
- `bitbucket-manager`
- `jenkins-manager`
- `eks-pod-ops`
- `confluence-publisher`
- `super-review`
- `review-prompts`
- `codex-subagent`

### Live At The End

- `codebase-analyzer`

### Mentioned Verbally

- `sbt-build-test`
- `skill-creator`

## Time Budget

- Intro and framing: 8 minutes
- Install/setup framing: 4 minutes
- Jira creation and enrichment: 12 minutes
- Code change, Jenkins, and EKS: 12 minutes
- Super-review and fix: 10 minutes
- PR comment loop, Confluence publish, surgical edit, Jira closeout: 10 minutes
- Cleanup and Q&A: 4 minutes

## Detailed Demo Flow

### 1. Intro And Framing

Presenter explains:

- what Agent Skills are
- what DotSkills is
- that the environment is preconfigured so the session can focus on the workflow
- that the session will show real systems, live-created demo artifacts, and live cleanup

The agent confirms the relevant skills are installed and briefly names the ones it will use.

### 2. Jira Creation From Markdown

The presenter asks the agent to create a demo epic and two stories from a prepared markdown source file.

The agent should:

- use the markdown source as input
- create a new demo epic from scratch
- create two child stories
- read back the created issues
- summarize what was created

This should highlight that `jira-manager` supports higher-level markdown-driven issue creation rather than only one-ticket-at-a-time CRUD.

### 3. Jira Enrichment

The presenter asks the agent to:

- assign a story to a real person using a slightly misspelled display name
- attach a diagram and markdown-rich content to the issue
- read the updated issue back for verification

This should showcase:

- fuzzy assignee resolution
- markdown conversion
- richer Jira workflow ergonomics

### 4. Code Change In `cap-onboarding`

The presenter asks the agent to implement one of the stories on a fresh temporary branch in `cap-onboarding`.

The agent should:

- create/switch to a temp branch
- make a small backend code change
- add or update tests
- commit and push

### 5. Jenkins And EKS

The presenter asks the agent to inspect CI and then perform an operational read-only check.

The agent should:

- use `jenkins-manager` to discover the relevant job and inspect build status/logs
- use `eks-pod-ops` to inspect dev logs
- explicitly say that the code was not deployed and the EKS step is demonstrating the operational workflow only

This keeps the session honest while still showing the real capability.

### 6. Super-Review

The presenter asks for a super-review of the change.

The review stack should be:

- `review-prompts` for built-in review lenses
- `super-review` for orchestration
- `codex-subagent` as the execution backend

In addition to several standard review prompts, the session should include one custom live review:

`Does the implementation satisfy the business logic described by the Jira story?`

The agent should present the resulting review report, then fix one finding, commit, and push again.

### 7. PR And Human Comment Loop

The presenter asks the agent to create a pull request.

The presenter then manually adds a prepared PR comment.

The agent should:

- fetch the PR comment
- implement the requested change
- commit and push

This shows real human-in-the-loop collaboration with Bitbucket comments.

### 8. Confluence Publish And Surgical Edit

The Confluence page should be created at the end of the workflow, based on what actually happened in the demo.

The agent should:

- create a markdown summary of the demo outcome live
- publish it to the Confluence target
- later perform one surgical edit requested by the presenter

There may also be a prepared fallback markdown template on disk, but the default path should be to generate the documentation live from the demo outcome.

### 9. Jira Closeout And Cleanup

The presenter signals that the session is done.

The agent should:

- transition the relevant Jira items as planned
- run the cleanup workflow

### 10. Codebase Analyzer Bonus

At the end, the presenter asks for a quick repo analysis summary using `codebase-analyzer`.

## Content Choices

### Jira Theme

The hero workflow should revolve around safer execution-plan patch validation in `cap-onboarding`.

Proposed epic:

- `DOTSKILLS DEMO 2026-04-20: Safer execution-plan patch validation`

Proposed stories:

- `Story 1: Reject empty execution-plan patch requests`
- `Story 2: Add regression coverage for execution-plan patch validation`

### Acceptance Criteria

For the main story:

- patch requests with no fields set are rejected
- the failure is explicit and easy to understand
- existing valid patch requests still work

For the test story:

- tests cover valid, invalid, and empty patch requests
- empty-patch behavior is documented by tests

### Code Change Target

Recommended target files:

- `src/main/scala/com/proofpoint/cap/onboarding/MonitoringExecutors/MonitoringEPValidator.scala`
- `src/test/scala/com/proofpoint/cap/onboarding/monitoring/EPPatchTests.scala`
- optionally `src/main/scala/com/proofpoint/cap/onboarding/services/RequestValidator.scala`

Recommended implementation:

- reject `ExecutionPlanPatch(None, None, None)`
- preserve current negative-value validation behavior
- add or adjust tests for valid, invalid, and empty patches

### Seeded Review Issue

The first implementation should intentionally stop short of fully satisfying the ticket intent. Specifically:

- the initial implementation should reject empty patches
- but the resulting error should remain too generic

This gives the custom business-logic review something real to catch:

- the code blocks the invalid request
- but it does not yet clearly communicate that at least one patch field must be provided

This issue is safe, believable, and easy to fix live.

### Assignee Typo Demo

Use one prevalidated real assignee whose display name can be safely misspelled during the demo. Example pattern:

- actual name: `Dor Melamed`
- demo input: `Dor Melamd`

The specific name should be validated during rehearsal.

### Prepared PR Review Comment

Primary prepared PR comment:

`The empty-patch case is rejected now, but the error still looks generic. Can we make the response clearly say that at least one patch field must be provided?`

Backup comments:

- `Can we add a dedicated test that proves an entirely empty patch is rejected?`
- `The Jira story asked for an explicit failure. The current behavior rejects the request, but I’m not sure the caller gets a clear enough reason.`

### Confluence Content

The live Confluence page should include:

- a title
- a short session summary
- bullets summarizing the loop
- one code block with the install command
- one Mermaid diagram
- one sentence intentionally chosen for later surgical editing

Recommended sentence for later surgical edit:

Initial:

`We used EKS logs to verify the change in dev after the CI step.`

After surgical edit:

`We demonstrated a read-only EKS verification workflow in dev; no deployment was performed as part of this session.`

This edit is visible, honest, and clearly demonstrates the value of surgical edits.

## Asset Package To Create

The session package should be created as markdown files in the repo:

- `docs/session-plans/2026-04-20-dotskills-session-plan.md`
- `demo/2026-04-20-agent-demo-script.md`
- `demo/2026-04-20-human-presenter-script.md`
- `demo/2026-04-20-jira-demo-source.md`
- `demo/2026-04-20-confluence-demo-doc.md`
- `demo/2026-04-20-pr-review-comment-cheatsheet.md`
- `demo/2026-04-20-cleanup-runbook.md`
- `demo/2026-04-20-rehearsal-checklist.md`

## Validation Strategy

### Smoke Check

Before the session, verify:

- required skills are installed in Codex
- optionally install them in Windsurf as well if the session will mention both
- Jira connectivity
- Bitbucket connectivity
- Confluence connectivity
- Jenkins connectivity
- EKS connectivity
- `codex-subagent` readiness

### Full Rehearsal

Run one rehearsal using the generated agent script and presenter script. The rehearsal should validate:

- flow order
- timing
- seeded issue detection
- PR comment handling
- Confluence surgical edit visibility
- cleanup completeness

The rehearsal can use a sub-agent as part of the validation approach.

## Cleanup Contract

At the end of the session, the agent should clean up all demo-created artifacts:

- cancel, close, or otherwise resolve demo Jira items according to the runbook
- delete or blank Confluence demo content
- close or decline the PR
- delete the temporary git branch
- remove temporary local files created only for the session
- verify that no demo-created items remain unexpectedly active

## Risks And Mitigations

### Risk: Demo Flow Feels Too Magical Or Too Staged

Mitigation:

- be explicit about what was prepared ahead of time
- use the hybrid content model:
  - Jira markdown source is prepared input
  - Confluence documentation is generated live from session outcomes

### Risk: Jenkins Is Slow

Mitigation:

- inspect status/logs without depending on completion
- explicitly say the session does not require waiting for deployment

### Risk: EKS Does Not Show Session-Specific Change

Mitigation:

- narrate the EKS step honestly as a read-only workflow demonstration

### Risk: Review Finds Nothing Actionable

Mitigation:

- include one safe seeded issue in the first implementation

### Risk: Cleanup Is Incomplete

Mitigation:

- use a shared demo prefix across all created artifacts
- include an explicit cleanup runbook

## Approval Needed Before Implementation

Once this design is approved, the next phase is to create the reusable markdown assets, install the required skills in Codex, and validate the session package with a rehearsal.
