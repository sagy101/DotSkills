# Skills Catalog

Quick-reference guide to all skills in this repository. Each section describes what a skill can do, followed by example prompts at three complexity levels and the expected agent behavior.

---

## Jira Manager

Manage Jira tickets end-to-end: create, update, fetch, delete, transition, comment, link, and bulk-operate on issues. Fetch by key, JQL, filter, board, or sprint. Discover fields, statuses, and priorities. Supports bulk create from markdown and smart 400-error diagnosis for missing required fields.

> Full details: [docs/jira-manager/jira-manager-design.md](docs/jira-manager/jira-manager-design.md)

| # | Complexity | Prompt | Expected Agent Response |
|---|------------|--------|------------------------|
| 1 | Simple | "Show me PROJ-101" | Runs preflight, fetches the ticket in detail format, and displays key, status, assignee, description, and comments. |
| 2 | Simple | "What's in the current sprint?" | Discovers the board ID, fetches active sprint tickets, and shows them in a table (key, type, SP, priority, status, summary). |
| 3 | Medium | "Find all in-progress bugs assigned to me with priority High" | Builds a JQL filter combining `type=Bug`, `status=In Progress`, `assignee=currentUser()`, and `priority=High`. Presents results as a table. |
| 4 | Medium | "Create 5 subtasks under PROJ-100 for each of these items: auth, logging, caching, retry, metrics" | Creates subtasks one by one with `--parent PROJ-100`, using `--copy-fields-from PROJ-100` to inherit custom fields. Shows each created ticket key. |
| 5 | Complex | "Fetch all bugs in sprint 'Sprint 12', transition them to In Progress, and add a comment 'Investigation started' to each" | Fetches bugs via board+sprint filter, collects the keys, then runs bulk update with `--status "In Progress"` and `--comment "Investigation started"`. Previews the plan first (dry-run), asks for confirmation, then executes. |

---

## Confluence Publisher

Publish, sync, diff, delete, discover, and export markdown documentation to/from Confluence Cloud. Handles page creation, updates, deletion, cross-page link rewriting, Mermaid diagram rendering, hierarchy verification, and reverse export to markdown. Also supports surgical HTML edits, section append (insert new content after a heading or at end of page), version comparison, and page revert.

> Full details: [docs/confluence-publisher/confluence-publisher-design.md](docs/confluence-publisher/confluence-publisher-design.md)

| # | Complexity | Prompt | Expected Agent Response |
|---|------------|--------|------------------------|
| 1 | Simple | "Publish README.md to Confluence space DOCS" | Runs preflight, converts markdown to Confluence storage format, creates or updates the page under the configured parent, and returns the page URL. |
| 2 | Medium | "Diff my local docs/ folder against what's on Confluence and show me what changed" | Discovers existing Confluence pages via manifest, runs a diff for each page against local markdown, and presents a summary of pages that are ahead, behind, or in sync. |
| 3 | Medium | "Export the 'Architecture' page and its children from Confluence to local markdown" | Fetches the page tree recursively, converts Confluence storage format to markdown, writes files preserving hierarchy, and generates a manifest file. |
| 4 | Complex | "Discover all pages under the TEAM space, diff against local docs, then publish only the ones that have local changes — dry-run first" | Runs discover to build a manifest, diffs each page against local files, filters to changed-only, executes a dry-run publish showing what would change, asks for confirmation, then publishes the delta. |
| 5 | Complex | "Someone manually edited the 'API Reference' page on Confluence — show me what they changed and revert it to the previous version" | Fetches version history, diffs the latest two versions to show manual edits, asks for confirmation, then reverts to the prior version. |

---

## Bitbucket Manager

Manage Bitbucket Cloud pull requests: create, update, get, list, merge, and decline. Add, edit, delete, and resolve PR comments (general and inline). View PR build checks, commit/branch pipeline status, extract linked Jira issues, and list workspace repositories. Pure Python stdlib — zero pip dependencies.

> Full details: [docs/bitbucket-manager/bitbucket-manager-design.md](docs/bitbucket-manager/bitbucket-manager-design.md)

| # | Complexity | Prompt | Expected Agent Response |
|---|------------|--------|------------------------|
| 1 | Simple | "List my open PRs" | Runs preflight, lists open PRs filtered by the current user, and displays them in a table with title, branch, reviewers, and approval status. |
| 2 | Simple | "Show build status for PR #42" | Fetches PR build checks and displays each pipeline's name, status (passed/failed/running), and URL. |
| 3 | Medium | "Create a PR from my current branch to master with default reviewers" | Detects the current branch from git, creates a PR targeting master, adds default reviewers from config, and returns the PR URL. |
| 4 | Medium | "Resolve all my comments on PR #38 and add a summary comment saying 'All addressed'" | Fetches PR comments, filters to the current user's unresolved comments, resolves them in bulk, then adds a new general comment. |
| 5 | Complex | "List all open PRs for the repo, check which ones have passing builds and approvals, and merge those that are ready" | Lists open PRs, checks build status and approval state for each, filters to those fully approved with green builds, presents the merge candidates for confirmation, then merges them one by one. |

---

## Jenkins Manager

Check Jenkins CI/CD build status, view console logs, trigger builds, view build changesets (commits), check queue status, and list jobs and folders. Auto-discovers the Jenkins job from git remote origin. Supports Pipeline, MultiBranch Pipeline, and OrganizationFolder projects. Pure Python stdlib — zero pip dependencies.

> Full details: [docs/jenkins-manager/jenkins-manager-design.md](docs/jenkins-manager/jenkins-manager-design.md)

| # | Complexity | Prompt | Expected Agent Response |
|---|------------|--------|------------------------|
| 1 | Simple | "Check the build status" | Runs preflight, auto-discovers the Jenkins job from git remote, fetches the latest build for the current branch, and displays status (SUCCESS/FAILURE/BUILDING), duration, and timestamp. |
| 2 | Simple | "Show me the build log" | Fetches console output for the latest build and displays the last 100 lines (or filters with grep if a pattern is specified). |
| 3 | Medium | "Trigger a build for the feature/auth branch with parameter ENV=staging" | Triggers a parameterized build for the specified branch, monitors the queue until the build starts, and reports the build number and URL. |
| 4 | Medium | "What commits were included in the last build?" | Fetches the changeset for the latest build and displays commit hashes, authors, and messages in a table. |
| 5 | Complex | "Trigger a build, wait for it to finish, then show me the test results and any failures from the log" | Triggers the build, polls queue/status until completion, fetches JUnit test results (pass/fail/skip counts), then greps the console log for failure stack traces and presents a summary. |

---

## EKS Pod Ops

Read pod logs, list pods, execute commands in pods, and restart deployments on EKS clusters. Supports environment-based kubeconfig and AWS SSO profiles, output redaction for secrets, and a blocklist for dangerous commands.

> Full details: [docs/eks-pod-ops/eks-pod-ops-design.md](docs/eks-pod-ops/eks-pod-ops-design.md)

| # | Complexity | Prompt | Expected Agent Response |
|---|------------|--------|------------------------|
| 1 | Simple | "Show me logs for my-service in staging" | Runs preflight (checks kubectl, kubeconfig, SSO), finds pods matching `my-service` in the staging environment, and tails the last 100 log lines. |
| 2 | Simple | "List all pods in production" | Lists all pods in the production environment with name, status, restarts, and age. |
| 3 | Medium | "Show me the last 30 minutes of logs for my-service in staging, grep for ERROR" | Fetches logs with `--since 30m`, filters for lines containing "ERROR", and presents the filtered output with timestamps. |
| 4 | Medium | "Exec into my-service in staging and check disk usage" | Finds the pod, presents the exec plan for approval, then runs `df -h` inside the container and shows the output. |
| 5 | Complex | "My-service keeps crashing in production — show me the current pod status, previous container logs, and then restart the deployment" | Describes the pod (events, conditions, restart count), fetches previous container logs (pre-crash), asks for confirmation, then triggers a rollout restart of the deployment. |

---

## SBT Build & Test

Compile, test, and publishLocal any SBT project. Handles multi-repo dependency chains automatically — detects upstream repos, publishes them in correct order, clears caches, and rebuilds. Uses an isolated build cache so normal SBT is never affected.

> Full details: [docs/sbt-build-test/sbt-build-test-design.md](docs/sbt-build-test/sbt-build-test-design.md)

| # | Complexity | Prompt | Expected Agent Response |
|---|------------|--------|------------------------|
| 1 | Simple | "Compile my-service" | Runs the build script with `-- compile`, handles preflight (Java version, cache setup), and reports success or shows the error tail. |
| 2 | Simple | "Run tests for my-service" | Runs `-- test`, parses JUnit XML reports, and displays a summary of passed/failed/skipped tests with failure details. |
| 3 | Medium | "Compile my-service with auto-publish of upstream dependencies" | Runs with `--auto-publish-deps`, detects stale or missing upstream workspace artifacts, publishes them in dependency order, then compiles the target project. |
| 4 | Medium | "Run tests for just the core subproject" | Runs `-- "core / test"` targeting a specific subproject, parses its JUnit results, and reports findings. |
| 5 | Complex | "I changed shared-models — rebuild and test both my-service and api-gateway that depend on it" | Runs workspace status to map the dependency graph, publishes shared-models first, then builds both downstream projects in order with `--auto-publish-deps`, and reports combined test results. |

---

## Codebase Analyzer

Analyze any codebase to produce structured metrics: line counts by category (code, tests, docs, scripts), language breakdown with comment analysis, test:code ratio, file-size distribution, TODO/FIXME tracking, and git churn hotspots. Outputs in terminal (Rich), JSON, Markdown, or interactive web dashboard (Streamlit) format.

> Full details: [docs/codebase-analyzer/codebase-analyzer-design.md](docs/codebase-analyzer/codebase-analyzer-design.md)

| # | Complexity | Prompt | Expected Agent Response |
|---|------------|--------|------------------------|
| 1 | Simple | "How big is this codebase?" | Runs preflight and setup if needed, analyzes the repo with default config, and shows total lines broken down by category (code, tests, docs, scripts) with a language breakdown. |
| 2 | Simple | "Find all TODOs in the codebase" | Runs the TODO/FIXME analysis and displays each annotation with file path, line number, and content. |
| 3 | Medium | "Analyze this repo and show me the results in a web dashboard" | Checks for a config file (offers to create one if missing), runs the full analysis with `--output web`, and launches a Streamlit dashboard in the browser with interactive charts and drill-downs. |
| 4 | Medium | "Show me the git churn hotspots — which files change most often?" | Runs the git churn analysis, ranks files by commit frequency, and presents the top hotspots with change counts and last-modified dates. |
| 5 | Complex | "Analyze this repo, compare the test:code ratio against a 1:3 target, identify the largest files over 500 lines, and show churn hotspots — output everything as JSON" | Runs the full analysis with all metrics, filters large files by threshold, computes the test:code ratio and flags if below target, includes churn hotspots, and outputs everything as a single JSON report. |

---

## Review Prompts

Reusable markdown prompt files for reviewing code, security, architecture, performance, testing, and language-specific quality. Supports 12 review types including TypeScript, Python, Java, Scala, JavaScript, and prompt engineering reviews. Prompts are assembled by a build script and can be used standalone or delegated to sub-agents.

| # | Complexity | Prompt | Expected Agent Response |
|---|------------|--------|------------------------|
| 1 | Simple | "Review this code for security issues" | Builds the security review prompt via `build-prompt.py`, applies the checklist to the target code, and reports findings with severity levels (Critical/High/Medium/Low). |
| 2 | Simple | "Review the Python code in src/api/" | Builds the Python-specific review prompt, applies best-practice checks (typing, idioms, async patterns), and reports findings. |
| 3 | Medium | "Review my Scala code for both code quality and performance" | Builds two prompts (code-review + performance), applies both checklists, and presents a combined report organized by severity. |
| 4 | Medium | "Review this SKILL.md for prompt engineering quality" | Builds the prompt-engineering review prompt, evaluates the skill definition against the checklist (clarity, structure, examples, constraints), and reports findings. |
| 5 | Complex | "Review the auth module — check code quality, security, and TypeScript best practices, then give me a unified report" | Builds three prompts (code-review, security, typescript), applies all checklists to the auth module, de-duplicates overlapping findings, and presents a unified severity-ranked report. |

---

## Super-Review

Run parallel multi-perspective code reviews using sub-agents. Synthesizes, de-duplicates, and grades all findings into a unified report with severity levels (Critical/High/Medium/Low) and an overall letter grade (A-F). **Requires a platform that can spawn parallel sub-agents** (e.g., Claude Code's Agent tool) **or the codex-subagent skill installed** — without one of these, the skill falls back to a single-pass self-review.

> Full details: [docs/super-review/super-review-design.md](docs/super-review/super-review-design.md)

| # | Complexity | Prompt | Expected Agent Response |
|---|------------|--------|------------------------|
| 1 | Simple | "Super-review the auth module" | Selects relevant review types (code-review, security), presents the review plan for approval, launches parallel sub-agents, synthesizes findings, and presents a graded report. |
| 2 | Medium | "Run a thorough review of the API layer — security, performance, and TypeScript quality" | Plans 3 parallel reviews (security, performance, typescript), gets approval, launches sub-agents, de-duplicates findings across perspectives, and presents a unified letter-graded report. |
| 3 | Medium | "Super-review the database migration scripts with focus on security and code quality" | Selects security + code-review perspectives, launches sub-agents, and produces a graded report with emphasis on SQL injection, data integrity, and migration safety. |
| 4 | Complex | "Super-review the entire PR — I want code quality, security, architecture, performance, and Python-specific checks, all in one report" | Plans 5 parallel reviews, gets approval, launches sub-agents for each perspective, performs its own host review, synthesizes all findings with de-duplication, and delivers a comprehensive letter-graded report. |

---

## Codex Sub-Agent

Delegate coding tasks to OpenAI Codex CLI as a sub-agent for parallel or isolated work. Supports read-only exploration, write tasks with git worktree isolation, structured JSON output, model routing by task complexity, and multi-turn delegation.

> Full details: [docs/codex-subagent/codex-subagent-design.md](docs/codex-subagent/codex-subagent-design.md)

| # | Complexity | Prompt | Expected Agent Response |
|---|------------|--------|------------------------|
| 1 | Simple | "Delegate: explore how error handling works in src/api/" | Runs preflight, launches a read-only Codex task with the exploration prompt, and returns the sub-agent's findings. |
| 2 | Medium | "Delegate: refactor the logging utility to use structured JSON output" | Assesses collision confidence, creates a git worktree for isolation, launches Codex in suggest mode, reviews the diff, and presents changes for approval. |
| 3 | Medium | "Get a second opinion on my implementation of the retry logic in src/client.ts" | Launches a read-only Codex review task with the code-review prompt, and returns the sub-agent's assessment and suggestions. |
| 4 | Complex | "In parallel: delegate refactoring auth to one agent and refactoring logging to another" | Assesses collision confidence for both tasks (should be low — different files), creates two worktrees, launches both Codex agents in parallel, collects results, and presents both diffs for review. |

---

## Skill Creator

Convert working scripts or ideas into polished, generic Agent Skills (SKILL.md + scripts + references). Handles analysis of source scripts, generalization of hardcoded values into configuration, creation of directory structures, and writing of SKILL.md with proper frontmatter, workflow sections, pre-flight checks, and supporting reference documents.

| # | Complexity | Prompt | Expected Agent Response |
|---|------------|--------|------------------------|
| 1 | Simple | "Create a new skill from scratch for managing GitHub releases" | Gathers requirements (API, operations, inputs/outputs, failure modes), designs the directory structure, and generates SKILL.md with frontmatter, prerequisites, preflight, and operation sections. |
| 2 | Medium | "Turn my deploy.py script into a reusable skill" | Reads and analyzes the script (purpose, hardcoded values, dependencies, side effects), designs the skill architecture, generalizes hardcoded values into config, creates CONFIG.md, and generates SKILL.md. |
| 3 | Medium | "Refactor the jenkins-manager skill — the SKILL.md is getting long, check it against best practices" | Reads the current SKILL.md and supporting files, runs the 10-point best-practices checklist, identifies gaps (missing error table, verbose sections, etc.), and rewrites with improvements. |
| 4 | Complex | "I have three scripts — fetch_data.py, transform.py, and upload.py — turn them into one cohesive data-pipeline skill with config, setup, and error handling" | Analyzes all three scripts and their data flow, designs a unified skill with a shared config loader, creates a setup script for dependencies, generalizes all hardcoded values, builds the directory structure, and produces SKILL.md + CONFIG.md + reference docs with a linear workflow tying the three operations together. |
