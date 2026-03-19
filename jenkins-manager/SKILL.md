---
name: jenkins-manager
description: >
  Check Jenkins CI/CD build status, view console logs, trigger builds, view build changesets
  (commits), check queue status, list jobs and folders for Jenkins Pipeline and MultiBranch
  Pipeline projects. Auto-discovers Jenkins job from git remote origin. Use when the user
  mentions Jenkins, build status, CI/CD pipeline, build logs, trigger build, build changes,
  queue status, or check the build. Pure Python stdlib — zero pip dependencies.
license: MIT
metadata:
  author: sagy101
  version: "2.0"
compatibility: >
  Python 3.10+. Jenkins REST API with API token authentication.
  Works with any Jenkins 2.x+ deployment (Freestyle, Pipeline, MultiBranch, OrganizationFolder).
---

# Jenkins Manager

Check build status, view logs, trigger builds, and list jobs on any Jenkins instance.

## When to use this skill

Use when the user wants to:
- **Check** build status for a job or branch
- **View** Jenkins console output / build logs
- **Trigger** a Jenkins build (with optional parameters)
- **View changes** — see which commits are included in a build
- **Check queue** — see if a triggered build is queued, blocked, or started
- **List** jobs across organization folders
- **List** top-level folders and job types
- **Discover** which Jenkins job corresponds to the current repo

## Prerequisites

1. **Config**: `.jenkins.json` in project root and/or `~/.jenkins.json` for global defaults (see [CONFIG.md](references/CONFIG.md))
2. **Credentials**: `JENKINS_USER` and `JENKINS_TOKEN` (API token) exported in shell profile or in a `.env` file

No pip install or venv needed — all scripts use Python stdlib only.

Config is auto-discovered — scripts search CWD upward, then `~/.jenkins.json`. If both exist, they are deep-merged (project-level wins). No `--config` flag needed.

If no config is found anywhere, help the user create one. For users with one Jenkins instance, a global `~/.jenkins.json` covers the shared settings:

```json
{
  "base_url": "https://your-jenkins-instance.example.com",
  "credentials": {
    "username_env": "JENKINS_USER",
    "token_env": "JENKINS_TOKEN"
  }
}
```

Then a minimal per-project `.jenkins.json` only needs optional overrides:
```json
{
  "job_cache": {
    "my-service": "API/my-service"
  }
}
```

## Pre-flight checks

Run the preflight script before any other operation:

```bash
python3 <skill_dir>/scripts/jenkins_preflight.py
```

This checks Python version, config file, credentials, connectivity, repo detection, and job discovery in one pass. Each check prints `[PASS]`, `[FAIL]`, or `[WARN]` with actionable fix instructions. Exit code 0 = all checks passed, 1 = at least one failed.

Skip the connectivity and discovery checks (faster, offline-safe):

```bash
python3 <skill_dir>/scripts/jenkins_preflight.py --skip-connectivity
```

If any check fails, fix the issue and re-run before proceeding.

## Workflow

1. **Pre-flight** — run checks above
2. **Determine operation** — status / logs / trigger / list
3. **Plan** — for trigger: show plan with `--dry-run` and **wait for user approval**
4. **Execute** — run the appropriate script
5. **Verify** — offer to check status or view logs after trigger operations

## Operations

### Check build status

```bash
python3 <skill_dir>/scripts/get_status.py
python3 <skill_dir>/scripts/get_status.py --build 1094
python3 <skill_dir>/scripts/get_status.py --folder MyFolder --job my-service --branch main
python3 <skill_dir>/scripts/get_status.py --format json
python3 <skill_dir>/scripts/get_status.py --watch --interval 30 --timeout 300
python3 <skill_dir>/scripts/get_status.py --build 1094 --watch
```

Auto-resolves folder, job, and branch from git remote + current branch. Override with flags.

Flags: `--build N` (specific build number, default: last build), `--watch` (poll until build finishes), `--interval N` (poll interval in seconds, default 60), `--timeout N` (max wait in seconds, default 600). Watch mode exit codes: 0=success, 1=build failed, 2=timeout.

### View build logs

```bash
python3 <skill_dir>/scripts/get_logs.py
python3 <skill_dir>/scripts/get_logs.py --tail 50
python3 <skill_dir>/scripts/get_logs.py --grep "ERROR"
python3 <skill_dir>/scripts/get_logs.py --build 142 --tail 0
python3 <skill_dir>/scripts/get_logs.py --folder MyFolder --job my-service --branch main
```

Flags: `--tail N` (default 100, 0 for all), `--grep PATTERN` (regex filter), `--build N` (specific build number).

**All log output is redacted** — secrets (API keys, tokens, passwords, AWS keys, connection strings, private keys, JWTs) are scrubbed before display. ANSI escape codes (color, bold, etc.) are automatically stripped before redaction and grep matching.

### View test results

```bash
python3 <skill_dir>/scripts/get_test_results.py
python3 <skill_dir>/scripts/get_test_results.py --build 142
python3 <skill_dir>/scripts/get_test_results.py --failures-only
python3 <skill_dir>/scripts/get_test_results.py --format json
```

Shows structured test results from JUnit reports: totals (pass/fail/skip) and failed test details (suite, test name, error message). Works with any language/framework that produces JUnit XML. Gracefully handles 404 when JUnit plugin is not installed.

Flags: `--build N` (specific build number), `--failures-only` (show only failed tests), `--format json`.

### Trigger a build

```bash
python3 <skill_dir>/scripts/trigger_build.py --dry-run
python3 <skill_dir>/scripts/trigger_build.py --folder MyFolder --job my-service --branch feature/my-branch --dry-run
python3 <skill_dir>/scripts/trigger_build.py --parameters ENV=staging VERSION=1.2.3 --dry-run
```

Remove `--dry-run` after review. Supports parameterized builds with `--parameters KEY=VALUE`.

### View build changes (commits)

```bash
python3 <skill_dir>/scripts/get_changesets.py
python3 <skill_dir>/scripts/get_changesets.py --folder MyFolder --job my-service --branch main
python3 <skill_dir>/scripts/get_changesets.py --build 142
python3 <skill_dir>/scripts/get_changesets.py --format json
```

Shows commits included in a build: short SHA, author, message, and affected file count. Defaults to the latest build.

### Check queue status

```bash
python3 <skill_dir>/scripts/get_queue_item.py --queue-id 12345
python3 <skill_dir>/scripts/get_queue_item.py --queue-id 12345 --format json
```

Shows whether a queued build is waiting, blocked, stuck, or has started. Use the queue ID returned after triggering a build.

### List top-level folders

```bash
python3 <skill_dir>/scripts/list_folders.py
python3 <skill_dir>/scripts/list_folders.py --format json
```

### List jobs

```bash
python3 <skill_dir>/scripts/list_jobs.py
python3 <skill_dir>/scripts/list_jobs.py --folder MyFolder
python3 <skill_dir>/scripts/list_jobs.py --name "my-service"
python3 <skill_dir>/scripts/list_jobs.py --format json
```

Flags: `--folder` (search specific folder), `--name PATTERN` (regex/substring filter).

### Common flags (all scripts)

All scripts accept `--job <name>` (auto-detected from git remote if omitted), `--folder <name>` (auto-discovered if omitted), `--branch <name>` (auto-detected from current git branch if omitted), and `--config <path>` (auto-discovered if omitted).

## Important rules

1. **ALWAYS use the provided scripts.** Every operation has a dedicated script. Run them via `python3 <skill_dir>/scripts/<script>.py`. NEVER write inline Python to call `JenkinsClient`, `jenkins_config`, or the Jenkins REST API directly. The scripts handle auth, config merging, error formatting, job auto-discovery, secret redaction, and branch encoding.
2. **If a script fails, debug the script invocation** (wrong flags, missing config, missing credentials). Do NOT abandon the scripts and write custom code. Check the error table below and re-run with corrected arguments.
3. **Never trigger a build without `--dry-run` first + explicit user approval.**
4. **Never print credentials.** Only confirm env vars are set.
5. **Job is auto-discovered from git remote.** Override with `--folder` and `--job` if needed.
6. **All log output is redacted.** Secret patterns are scrubbed before display. Do not attempt to bypass redaction.

## Error handling

| Error | Cause | Fix |
|---|---|---|
| `401 Unauthorized` | Bad credentials | Verify `JENKINS_USER` and `JENKINS_TOKEN` env vars. Token must be a Jenkins API token, not account password |
| `403 Forbidden` | Insufficient permissions or CSRF issue | Check user permissions. For POST operations, CSRF crumb is handled automatically |
| `404 Not Found` | Wrong folder, job, or branch name | Verify with `list_folders.py` and `list_jobs.py`. Branch names are URL-encoded automatically |
| `500 Internal Server Error` | Jenkins server error | Check Jenkins server health. Retry after a moment |
| `SSL certificate verification failed` | Self-signed cert or custom CA | Set `ssl_verify: false` in config, or set `SSL_CERT_FILE` env var |
| Config not found | No `.jenkins.json` anywhere | Create `~/.jenkins.json` with `base_url` and credentials |
| Job not found | Auto-discovery failed | Add `job_cache` entry in `.jenkins.json`, or use `--folder` + `--job` |
| `env_file escapes project root` | Relative `env_file` in global config | Use an absolute path for `env_file` in global `~/.jenkins.json` |
| `env_file not found` | Path in config doesn't exist | Check the `env_file` path in config; use absolute path in global config |

## Troubleshooting

| Problem | Fix |
|---|---|
| `python3: command not found` | Install Python 3.10+ |
| Can't detect repo from git remote | Provide `--job <name>` explicitly |
| Can't find job in Jenkins | Run `list_jobs.py --name <repo>` to search; add result to `job_cache` |
| Build trigger returns 403 | User may lack build permissions. Check Jenkins user roles |
| Console log is huge/slow | Use `--tail 50` or `--grep "ERROR"` to filter |
| Branch name with `/` not found | Branch encoding is automatic; verify branch exists with `list_jobs.py --folder F --name J` |
| SSL errors on corporate Jenkins | Set `"ssl_verify": false` in `.jenkins.json` |
