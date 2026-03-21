---
name: sbt-build-test
description: >
  Use for ANY SBT operation: compile, test, publishLocal, dependency discovery, cross-repo builds. Handles multi-repo dependency chains automatically — detects upstream repos, publishes them in correct order, clears caches, and rebuilds. Uses an isolated build cache so normal sbt is never affected.
metadata:
  author: sagy101
  version: "11.0"
---

# SBT Multi-Repo Build & Test

Four commands for all SBT operations: build, status, refresh, reset.

## When to use this skill

Use this skill when you need to:
- **Compile or test** any SBT project (single or multi-project)
- **Publish local artifacts** for downstream validation
- **Understand dependencies** between workspace repos
- **Fix stale state** after upstream changes
- **Inspect test results** from JUnit XML reports

## Prerequisites

1. **SBT** and the required **JDK** installed (default: Java 17).
2. SBT repos under one workspace root, or define overrides in `.sbt-workspace.conf`.
3. **`python3`** available for test report parsing and workspace graph helpers.
4. **`~/.ivy2/.credentials`** present if the workspace resolves private artifacts.

## Configuration

Create `<workspace>/.sbt-workspace.conf` only when you need overrides:

```bash
.java_version=17
.group_id=com.acme
shared-models=/absolute/path/to/shared-models
```

See [references/CONFIG.md](references/CONFIG.md) for full schema.

## Commands

### `sbt_build.sh` — Compile, test, publishLocal

The single command for all build operations. Accepts one project, several, or `--all` for the entire workspace. Automatically handles preflight, upstream dep publishing, log capture, and JUnit XML test report parsing.

```bash
bash <skill_dir>/scripts/sbt_build.sh <project-dir>... [options] -- <sbt-commands>
bash <skill_dir>/scripts/sbt_build.sh --all [options] -- <sbt-commands>
```

| Option | Description |
|---|---|
| `--all` | Build all workspace projects in dependency order |
| `--workspace-dir <dir>` | Override workspace directory |
| `--artifact-version <ver>` | Set ARTIFACT_VERSION for publishLocal |
| `--sbt-env <value>` | Pass `-Dsbt_env=<value>` to SBT |
| `--tail <lines>` | Lines of log tail to show (default: 60) |
| `--auto-publish-deps` | Auto-publishLocal missing AND stale workspace deps before building |
| `--continue-on-error` | Keep going when a project fails (useful with `--all`) |
| `--fresh` | Force fresh SBT process (no server reuse) — use when SBT returns stale results |
| `--skip-preflight` | Skip Java/cache pre-check (for repeated calls) |

**Examples:**

```bash
# Compile one project
bash <skill_dir>/scripts/sbt_build.sh /path/to/service -- compile

# Run all tests (auto-parses JUnit XML reports)
bash <skill_dir>/scripts/sbt_build.sh /path/to/service -- test

# Test a specific subproject
bash <skill_dir>/scripts/sbt_build.sh /path/to/service -- "core / test"

# Compile with auto-publish of missing upstream deps
bash <skill_dir>/scripts/sbt_build.sh /path/to/service --auto-publish-deps -- compile

# Compile several projects
bash <skill_dir>/scripts/sbt_build.sh /path/to/svc-a /path/to/svc-b -- compile

# Compile all workspace projects in dependency order
bash <skill_dir>/scripts/sbt_build.sh --all -- compile

# Compile + test everything with auto-publish
bash <skill_dir>/scripts/sbt_build.sh --all --auto-publish-deps -- test

# Publish locally at a specific version
bash <skill_dir>/scripts/sbt_build.sh /path/to/library --artifact-version 0.532.0 -- publishLocal
```

Use the exact scoped project ID reported by `sbt_status.sh` for subproject names. In multi-project builds the ID may differ from the published artifact name (e.g. `myModule` vs `my-module`).

**rootPaths auto-detection**: When `--sbt-env dev` is requested but the project has `rootPaths`/`remoteCache` settings AND external `ProjectRef` entries, the skill auto-falls back to non-dev mode. No manual intervention needed.

### `sbt_status.sh` — Discover dependencies and workspace state

Single command for all discovery and diagnostics.

```bash
bash <skill_dir>/scripts/sbt_status.sh <project-dir> [options]
```

| Option | Description |
|---|---|
| `--workspace` | Full workspace preflight + dependency graph |
| `--plan-change <repo>` | Plan impact of a cross-repo change |
| `--verify <artifact>` | Verify artifact resolution source |
| `--workspace-dir <dir>` | Override workspace directory |
| `--json` | JSON output (workspace and plan-change modes) |

**Default** (no flags): Discovers the project's cross-repo dependencies, workspace artifacts, transitive deps, dirty repo warnings, version variables, and build configuration.

**Examples:**

```bash
# What does this project depend on?
bash <skill_dir>/scripts/sbt_status.sh /path/to/service

# Full workspace state: preflight + all repos + dependency graph
bash <skill_dir>/scripts/sbt_status.sh /path/to/service --workspace

# What happens if I change commons and rebuild service-a?
bash <skill_dir>/scripts/sbt_status.sh /path/to/service-a --plan-change /path/to/commons

# Where is this artifact being resolved from?
bash <skill_dir>/scripts/sbt_status.sh /path/to/service --verify platform-commons
```

### `sbt_refresh.sh` — Fix stale state

Clears caches, publishes upstream deps, and rebuilds.

```bash
bash <skill_dir>/scripts/sbt_refresh.sh <project-dir> [options]
```

| Option | Description |
|---|---|
| `--publish-upstreams` | Publish upstream workspace deps in dependency order first |
| `--artifact-version <ver>` | Version for publishLocal |
| `--artifact <name>` | Artifact name for targeted cache clearing |
| `--version <ver>` | Version for targeted cache clearing |
| `--clean-target` | Delete project `target/` directory (also kills SBT server) |
| `--kill-server` | Explicitly shut down the SBT server for this project |
| `--rebuild` | Rebuild with `compile` after refresh |
| `--rebuild-arg <arg>` | Explicit SBT arg for rebuild (overrides `--rebuild`) |
| `--workspace-dir <dir>` | Override workspace directory |
| `--dry-run` | Show what would be done without doing it |

**Examples:**

```bash
# Full upstream publish + cache clear + rebuild (most common for cross-repo changes)
bash <skill_dir>/scripts/sbt_refresh.sh /path/to/service --publish-upstreams --clean-target --rebuild

# Clear caches for a specific artifact and rebuild
bash <skill_dir>/scripts/sbt_refresh.sh /path/to/service --artifact my-lib --version 0.532.0 --clean-target --rebuild

# Dry run to see what would happen
bash <skill_dir>/scripts/sbt_refresh.sh /path/to/service --publish-upstreams --dry-run
```

### `sbt_reset.sh` — Wipe isolated cache and return to clean state

Removes all local publishes and cached artifacts so builds resolve from remote again.

```bash
bash <skill_dir>/scripts/sbt_reset.sh [options]
```

| Option | Description |
|---|---|
| `--local-only` | Only wipe local publishes, keep downloaded cache |
| `--dry-run` | Show what would be deleted without deleting |

**Examples:**

```bash
# Full reset — everything from remote again
bash <skill_dir>/scripts/sbt_reset.sh

# Only wipe local publishes
bash <skill_dir>/scripts/sbt_reset.sh --local-only

# Preview what would be deleted
bash <skill_dir>/scripts/sbt_reset.sh --dry-run
```

## Decision Table

| Scenario | Command |
|---|---|
| Edit target service code, compile | `sbt_build.sh <target> -- compile` |
| Edit target service code, test | `sbt_build.sh <target> -- test` |
| Test a specific subproject | `sbt_build.sh <target> -- "<subproject> / test"` |
| Check what this project depends on | `sbt_status.sh <target>` |
| Check full workspace state | `sbt_status.sh <target> --workspace` |
| Upstream library changed, rebuild downstream | `sbt_refresh.sh <downstream> --publish-upstreams --clean-target --rebuild` |
| Dependency declarations changed in build.sbt | `sbt_status.sh <target>` then `sbt_build.sh <target> -- compile` |
| Downstream still sees old artifact | `sbt_refresh.sh <downstream> --artifact <name> --version <ver> --clean-target --rebuild` |
| Plan a cross-repo change | `sbt_status.sh <target> --plan-change <changed-repo>` |
| Verify artifact resolution source | `sbt_status.sh <target> --verify <artifact-name>` |
| Compile with auto-fix for missing deps | `sbt_build.sh <target> --auto-publish-deps -- compile` |
| Compile several specific projects | `sbt_build.sh <proj-a> <proj-b> -- compile` |
| Compile all workspace projects | `sbt_build.sh --all -- compile` |
| Compile + test everything | `sbt_build.sh --all --auto-publish-deps --continue-on-error -- test` |
| Reset to clean state (resolve from remote) | `sbt_reset.sh` |
| Reset only local publishes | `sbt_reset.sh --local-only` |
| SBT returns stale test results after edits | `sbt_build.sh <target> --fresh -- test` |
| SBT server is stuck/corrupted | `sbt_refresh.sh <target> --kill-server --clean-target --rebuild` |

## Exit Codes

| Code | Meaning |
|---|---|
| `0` | SUCCESS — build/test completed without errors |
| `1` | SBT error — compilation failure, test failure, or dependency resolution error |
| `2` | Infrastructure error — lock contention, missing Java, missing config, or no test reports |

## Important rules

1. **Use `sbt_build.sh` for all compile, test, and publishLocal flows.** It preserves full logs, auto-checks deps, and auto-parses test reports.
2. **All skill-driven SBT runs use the isolated cache** at `~/.sbt-build-cache` (Ivy, Coursier, SBT boot, SBT global) to avoid contaminating system caches.
3. **Use `sbt_status.sh` before guessing dependency order.** Do not guess publish order.
4. **Show the dry-run plan before running `sbt_refresh.sh`** with `--publish-upstreams` for the first time in a session.
5. **JUnit XML is the source of truth for test results.** Console success only means SBT finished.

## Parallel worktree builds

All SBT caches (Ivy, Coursier, SBT boot, SBT global) are isolated inside
`SBT_BUILD_CACHE_ROOT` (default: `~/.sbt-build-cache`). For parallel builds
across git worktrees, set a different cache root per worktree:

```bash
# In worktree 1
export SBT_BUILD_CACHE_ROOT=~/.sbt-build-cache/wt-main

# In worktree 2
export SBT_BUILD_CACHE_ROOT=~/.sbt-build-cache/wt-feature-x
```

Each worktree gets its own publishLocal artifacts, Coursier downloads, and
SBT boot files. No lock contention or cache corruption between parallel builds.

> **Note:** The first build in a new cache root is slower due to cold Coursier and
> SBT boot caches. Subsequent builds are fast.

## Error handling

| Error | Cause | Fix |
|---|---|---|
| `Java <version> not found` | Requested JDK is not installed | Update `.sbt-workspace.conf` or install the matching JDK |
| `python3 is required` | Report parsing runtime missing | Install `python3` |
| `Credentials file does not exist` | Private resolver credentials missing | Create `~/.ivy2/.credentials` |
| `cannot be mapped using the root paths` | Local publishes conflict with root-path/remote-cache settings | Auto-detected by `sbt_build.sh` — falls back to non-dev mode automatically |
| `MISSING: <artifact> @ <version>` | Workspace dep not in isolated cache | Use `--auto-publish-deps` on `sbt_build.sh`, or run `sbt_refresh.sh --publish-upstreams` |
| `STALE: <artifact> @ <version>` | Upstream workspace repo on a feature branch with no local publish | Warning only. Republish upstream if you hit runtime errors |
| `NoSuchMethodError` / `NoSuchFieldError` | Stale artifact on classpath | `sbt_refresh.sh <project> --publish-upstreams --clean-target --rebuild` |
| `not a valid command` | Wrong scoped SBT command | Run `sbt_status.sh <project>` and use a listed subproject name |
| `No test-reports directory found` | Tests did not generate XML reports | Run tests first via `sbt_build.sh` |
| `CRASH (no JUnit XML produced)` | Test suite crashed before writing XML | Check SBT log for ClassCastException, OutOfMemoryError, or initialization errors |
| `Stale lock file detected` | A previous build was killed leaving a lock | Auto-cleaned — no action needed |
| `WARNING: Log file is from a previous run` | SBT did not execute (likely lock contention) | Check for concurrent builds or stale SBT server |

## Troubleshooting

| Problem | Fix |
|---|---|
| Console output truncated | `sbt_build.sh` saves full logs — inspect the log file path in the summary |
| Downstream still sees old artifact | `sbt_refresh.sh <project> --artifact <name> --clean-target --rebuild` |
| Unsure if a change affects the target | `sbt_status.sh <target> --plan-change <changed-repo>` |
| Need the full workspace dependency order | `sbt_status.sh <project> --workspace` |
| `NoSuchMethodError` at runtime | `sbt_refresh.sh <project> --publish-upstreams --clean-target --rebuild` |
| Upstream repo on a feature branch | `sbt_status.sh <project> --workspace` to see branch alignment |
