# Workspace Config Reference

This skill optionally reads a workspace config file named `.sbt-workspace.conf` from the workspace root.

Read this reference only when `.sbt-workspace.conf` is already needed and you want the exact schema, defaults, or validation rules.

## File format

The file is line-oriented:
- blank lines are ignored
- lines starting with `#` are ignored
- settings use `key=value`
- project overrides use `project-name=/absolute/path/to/project`

## Supported settings

### `.java_version`

- **Type**: string or integer-like major version
- **Required**: no
- **Default**: `17`
- **Purpose**: selects the Java major version used by `run_sbt.sh`, `preflight_check.sh`, and discovery commands

Example:

```bash
.java_version=21
```

### `.group_id`

- **Type**: string
- **Required**: no
- **Default**: auto-detected from local `organization :=` settings when possible
- **Purpose**: filters `libraryDependencies` and `dependencyTree` output to artifacts from your organization or workspace namespace when auto-detection is missing or ambiguous

Example:

```bash
.group_id=com.acme
```

## Project override entries

Project override entries map a logical project name to an absolute path.

- **Type**: `project-name=/absolute/path`
- **Required**: no
- **Default**: auto-scan `workspace/*/build.sbt`
- **Purpose**: add repos outside the workspace root or override an auto-discovered path

Example:

```bash
shared-models=/Users/me/dev/shared-models
service-a=/Volumes/worktrees/service-a
```

## Complete example

```bash
# <workspace>/.sbt-workspace.conf
.java_version=17
.group_id=com.acme

shared-models=/Users/me/dev/shared-models
platform-commons=/Users/me/dev/platform-commons
service-a=/Users/me/dev/service-a
```

## Resolution order

1. Auto-scan direct workspace children containing `build.sbt`
2. Read `.sbt-workspace.conf` if present
3. Apply `.java_version` and `.group_id`
4. Auto-detect `GROUP_ID` from workspace `organization :=` settings if `.group_id` is absent
5. Add or replace project paths by project name
6. Sort final project list by project name

## Validation rules

A project override is ignored when:
- the project name is blank
- the path is blank
- the path does not contain `build.sbt`

Unknown settings beginning with `.` are ignored with a warning.

## Agent usage notes

Use the config when:
- the user works from a sparse checkout or multiple worktrees
- an upstream repo lives outside the main workspace root
- the default group ID would hide required local artifacts

Do not create this file unless the user actually needs non-default repo layout or group ID behavior.
