#!/usr/bin/env bash
# DotSkills command whitelist — auto-approve read-only skill script invocations.
#
# Fires on PermissionRequest for the Bash tool.
# Outputs an allow decision if the command calls a read-only skill script;
# exits 0 silently otherwise so the normal approval dialog appears.
#
# Read-only = scripts that only fetch/list/query external systems.
# Write scripts (create, update, delete, trigger, restart, exec, comment) are NOT listed here.

INPUT=$(cat)
COMMAND=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)

[[ -z "$COMMAND" ]] && exit 0

allow() {
  printf '{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow"}}}'
  exit 0
}

# ---------------------------------------------------------------------------
# jira-manager — read-only scripts
# ---------------------------------------------------------------------------
[[ "$COMMAND" == *"fetch_tickets.py"*    ]] && allow
[[ "$COMMAND" == *"discover_fields.py"*  ]] && allow
[[ "$COMMAND" == *"diff_tickets.py"*     ]] && allow
[[ "$COMMAND" == *"validate_estimates.py"* ]] && allow

# ---------------------------------------------------------------------------
# bitbucket-manager — read-only scripts
# ---------------------------------------------------------------------------
[[ "$COMMAND" == *"bb_preflight.py"*     ]] && allow
[[ "$COMMAND" == *"pr_get.py"*           ]] && allow
[[ "$COMMAND" == *"pr_list.py"*          ]] && allow
[[ "$COMMAND" == *"pr_comments.py"*      ]] && allow   # list comments (read)
[[ "$COMMAND" == *"pr_checks.py"*        ]] && allow
[[ "$COMMAND" == *"build_status.py"*     ]] && allow
[[ "$COMMAND" == *"pr_jira.py"*          ]] && allow
[[ "$COMMAND" == *"repo_list.py"*        ]] && allow

# ---------------------------------------------------------------------------
# jenkins-manager — read-only scripts
# ---------------------------------------------------------------------------
[[ "$COMMAND" == *"jenkins_preflight.py"* ]] && allow
[[ "$COMMAND" == *"get_status.py"*        ]] && allow
[[ "$COMMAND" == *"get_logs.py"*          ]] && allow
[[ "$COMMAND" == *"get_test_results.py"*  ]] && allow
[[ "$COMMAND" == *"get_changesets.py"*    ]] && allow
[[ "$COMMAND" == *"get_queue_item.py"*    ]] && allow
[[ "$COMMAND" == *"list_folders.py"*      ]] && allow
[[ "$COMMAND" == *"list_jobs.py"*         ]] && allow

# ---------------------------------------------------------------------------
# eks-pod-ops — pods and logs subcommands only (exec and restart require approval)
# ---------------------------------------------------------------------------
[[ "$COMMAND" == *"eks_preflight.py"* ]] && allow
if [[ "$COMMAND" == *"eks_ops.py"* ]]; then
  if [[ "$COMMAND" =~ eks_ops\.py[[:space:]]+(pods|logs) ]]; then
    allow
  fi
  # exec / restart — fall through to normal approval dialog
  exit 0
fi

# ---------------------------------------------------------------------------
# confluence-publisher — read-only scripts
# ---------------------------------------------------------------------------
[[ "$COMMAND" == *"diff_pages.py"*        ]] && allow
[[ "$COMMAND" == *"validate_manifest.py"* ]] && allow
[[ "$COMMAND" == *"verify_hierarchy.py"*  ]] && allow
[[ "$COMMAND" == *"discover_pages.py"*    ]] && allow
[[ "$COMMAND" == *"diff_versions.py"*     ]] && allow

# page_versions.py — allow --list and --fetch, block --revert
if [[ "$COMMAND" == *"page_versions.py"* ]]; then
  if [[ "$COMMAND" != *"--revert"* ]] && [[ "$COMMAND" =~ --(list|fetch) ]]; then
    allow
  fi
  exit 0
fi

# export_pages.py — only allow --dry-run (without it, it overwrites local files)
if [[ "$COMMAND" == *"export_pages.py"* ]]; then
  [[ "$COMMAND" == *"--dry-run"* ]] && allow
  exit 0
fi

# ---------------------------------------------------------------------------
# skill-sync and skill-creator — safe meta/tooling scripts
# ---------------------------------------------------------------------------
[[ "$COMMAND" == *"sync.py"*           ]] && allow
[[ "$COMMAND" == *"quick_validate.py"* ]] && allow

# No match — let the normal approval dialog appear
exit 0
