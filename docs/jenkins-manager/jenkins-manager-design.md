# Jenkins Manager Skill — Design Document

> This document covers **why** this skill exists and the **key decisions** an implementer or reviewer needs to understand.

---

## Why This Skill Exists

The DevOps workflow has a gap between "PR merged in Bitbucket" and "running in EKS". Jenkins is the CI/CD engine in between, but without a skill, agents write ad-hoc `curl` commands that miss branch encoding, lack secret redaction, and hardcode job paths.

This skill gives **any SKILL.md-compatible agent** reliable Jenkins CI/CD management through deterministic CLI scripts. It completes the inner loop:

```
Jira (plan) → Code → Bitbucket (PR) → Jenkins (build/deploy) → EKS (verify) → Confluence (document)
```

---

## Capabilities

| Capability | Description |
|---|---|
| **Build status** | Check latest build result for a job + branch with auto-discovery |
| **Console logs** | View build output with tail/grep filtering and secret redaction |
| **Trigger build** | Start a build with optional parameters (dry-run required first) |
| **Build changes** | View commits included in a specific build |
| **Queue status** | Check if a triggered build is queued, blocked, stuck, or started |
| **List folders** | Browse top-level organization folders |
| **List jobs** | Search jobs across folders with regex filtering |
| **Pre-flight** | Validate config, credentials, connectivity, and job discovery in one pass |

---

## Key Design Decisions

**1. Zero pip dependencies** — Pure Python stdlib (`urllib`, `json`, `base64`, `argparse`, `subprocess`, `ssl`). No venv, no setup, no install. Instantly usable on any system with Python 3.10+.

**2. Fully generic — no deployment-specific values** — Unlike sister skills that were built for one team then generalized, this skill was designed generic from day one. All URLs, usernames, folder names, and job names come from config. Works with any Jenkins 2.x+ instance, any git host, any job type.

**3. Pipeline auto-discovery from git remote** — The hardest UX problem: "the user says 'check the build' — which Jenkins job?" Resolution is layered:
1. CLI flags (`--folder`, `--job`) — explicit override
2. `job_cache` in config — cached mapping from repo name to folder/job path
3. API search — parse `git remote get-url origin` → extract repo name → search all Jenkins folders for a matching MultiBranch/Pipeline project

This avoids requiring users to memorize Jenkins job paths while still allowing explicit control.

**4. Branch name URL encoding** — Jenkins encodes `/` as `%2F` in URL paths for branches like `feature/TICKET-123`. This is handled transparently by `url_encode_branch()` in every script — the user passes the natural branch name.

**5. Secret redaction on all log output** — Jenkins console logs can leak secrets (env vars, connection strings, API keys). All console output passes through `redact_text()` before the agent sees it. Always-on, no toggle. Mirrors the eks-pod-ops redaction module with identical patterns.

**6. Config hierarchy mirrors other skills** — Global `~/.jenkins.json` → local `.jenkins.json` → CLI flags. Deep-merge on overlap. Same pattern as bitbucket-manager, jira-manager, confluence-publisher. Users configure once globally and override per-project.

**7. Credentials via environment variables** — Config stores only env var *names* (`username_env`, `token_env`), never values. Missing credentials produce actionable error messages with shell-specific setup commands.

**8. CSRF crumb handling** — Jenkins requires a CSRF crumb token for POST requests. The client fetches `/crumbIssuer/api/json` on first POST and caches it. Some Jenkins instances have crumb disabled — handled gracefully (crumb fetch returns 404 → skip).

**9. Supports all Jenkins job types** — Not just MultiBranch Pipelines. Freestyle, Pipeline, Folder, OrganizationFolder are all handled. API paths are constructed dynamically based on whether a folder and/or branch is present.

**10. Console log size management** — Jenkins logs can be enormous (500K+ lines). `get_logs.py` defaults to `--tail 100` and supports `--grep` to keep output manageable for the agent context window.

---

## Architecture

```
jenkins-manager/
├── SKILL.md                  # Agent-facing instructions
├── scripts/
│   ├── jenkins_config.py     # Config loading, credential resolution, repo/branch detection
│   ├── jenkins_client.py     # Jenkins REST API wrapper (Basic auth, CSRF, SSL)
│   ├── jenkins_redaction.py   # Secret scrubbing for log output
│   ├── jenkins_preflight.py  # Pre-flight validation (6 checks)
│   ├── get_status.py         # Build status
│   ├── get_logs.py           # Console output with redaction
│   ├── get_changesets.py     # Commits in a build
│   ├── get_queue_item.py     # Queue item status
│   ├── trigger_build.py      # Trigger build (--dry-run gate)
│   ├── list_folders.py       # Top-level folder listing
│   └── list_jobs.py          # Job search with regex filter
├── references/
│   └── CONFIG.md             # Full config schema documentation
```

**Script → shared module dependency:**
- All operation scripts import `jenkins_config` (config + branch/job resolution)
- Scripts that call the API import `jenkins_client` (HTTP wrapper)
- `get_logs.py` and `trigger_build.py` import `jenkins_redaction` (secret scrubbing)

---

## Approval Gates

| Action | Approval Required | Mechanism |
|---|---|---|
| **Trigger build** | Yes | `--dry-run` shows job path + parameters; agent shows plan and waits for approval |
| **Get status / logs / changes** | No | Read-only operations |
| **List folders / jobs** | No | Read-only operations |
| **Queue status** | No | Read-only operation |

---

## Comparison to Official Jenkins MCP Plugin

The [official MCP Server plugin](https://plugins.jenkins.io/mcp-server) requires installing a plugin on the Jenkins server. This skill requires **zero server-side changes** — it uses the standard REST API.

| Feature | Our Skill | Official MCP Plugin |
|---|---|---|
| Server-side install | Not needed | Required |
| Secret redaction | Yes (always-on) | No |
| Job auto-discovery | Yes (git remote → API search) | Via `findJobsWithScmUrl` |
| Dry-run gates | Yes | No |
| Folder browsing | Yes | Via `getJobs` |
| Build changesets | Yes | Yes |
| Queue status | Yes | Yes |
| Update build name | No | Yes |
| SCM config viewing | No | Yes |

---

## Risks at a Glance

| Risk | Severity | Mitigation |
|---|---|---|
| Accidental build trigger | High | `--dry-run` required; agent must get user approval |
| Secret exposure in logs | High | Always-on redaction; no toggle |
| Credential exposure | High | Env var names only in config; values never printed |
| Wrong job targeted | Medium | Auto-detect from git remote; `--dry-run` shows target before action |
| SSL cert errors on corporate Jenkins | Low | `ssl_verify: false` config option; `SSL_CERT_FILE` env var |
| Large log output floods context | Low | Default `--tail 100`; `--grep` for filtering |

---

## References

- **Jenkins REST API** — The underlying API for all operations
- **bitbucket-manager** — Sister skill; config/credential patterns copied from here
- **eks-pod-ops** — Sister skill; redaction module patterns copied from here
- **Official Jenkins MCP Plugin** — Server-side alternative; feature comparison above

## Status

**Stable (v1.0)** — All 11 scripts validated against live Jenkins instance. Supports build status, logs, trigger, changesets, queue status, folder/job listing, and pre-flight checks.
