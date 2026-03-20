#!/usr/bin/env bash
# DotSkills command whitelist — auto-approve read-only skill scripts.
#
# Fires on PermissionRequest for Bash tool calls.
# Outputs an allow decision if the command matches a read-only skill script;
# exits silently otherwise so the normal approval dialog is shown.
#
# Read-only = fetches/reads data from external systems, no side effects.
# Write operations (create, update, delete, trigger, restart, exec) are NOT whitelisted.

INPUT=$(cat)
COMMAND=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)

[[ -z "$COMMAND" ]] && exit 0

_allow() {
  printf '{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow"}}}'
  exit 0
}

# ---------------------------------------------------------------------------
# Always-safe read-only scripts (matched by basename anywhere in the command)
# ---------------------------------------------------------------------------

# jira-manager
[[ "$COMMAND" == *"fetch_tickets.py"*     ]] && _allow
[[ "$COMMAND" == *"discover_fields.py"*   ]] && _allow
[[ "$COMMAND" == *"diff_tickets.py"*      ]] && _allow
[[ "$COMMAND" == *"validate_estimates.py"* ]] && _allow

# bitbucket-manager
[[ "$COMMAND" == *"bb_preflight.py"*  ]] && _allow
[[ "$COMMAND" == *"pr_get.py"*        ]] && _allow
[[ "$COMMAND" == *"pr_list.py"*       ]] && _allow
[[ "$COMMAND" == *"pr_comments.py"*   ]] && _allow
[[ "$COMMAND" == *"pr_checks.py"*     ]] && _allow
[[ "$COMMAND" == *"build_status.py"*  ]] && _allow
[[ "$COMMAND" == *"pr_jira.py"*       ]] && _allow
[[ "$COMMAND" == *"repo_list.py"*     ]] && _allow

# jenkins-manager
[[ "$COMMAND" == *"jenkins_preflight.py"* ]] && _allow
[[ "$COMMAND" == *"get_status.py"*        ]] && _allow
[[ "$COMMAND" == *"get_logs.py"*          ]] && _allow
[[ "$COMMAND" == *"get_test_results.py"*  ]] && _allow
[[ "$COMMAND" == *"get_changesets.py"*    ]] && _allow
[[ "$COMMAND" == *"get_queue_item.py"*    ]] && _allow
[[ "$COMMAND" == *"list_folders.py"*      ]] && _allow
[[ "$COMMAND" == *"list_jobs.py"*         ]] && _allow

# eks-pod-ops (preflight only — pods/logs handled below with subcommand check)
[[ "$COMMAND" == *"eks_preflight.py"* ]] && _allow

# confluence-publisher (read-only)
[[ "$COMMAND" == *"diff_pages.py"*       ]] && _allow
[[ "$COMMAND" == *"validate_manifest.py"* ]] && _allow
[[ "$COMMAND" == *"verify_hierarchy.py"* ]] && _allow
[[ "$COMMAND" == *"discover_pages.py"*   ]] && _allow
[[ "$COMMAND" == *"diff_versions.py"*    ]] && _allow

# skill-sync (distribution utility, no external side effects)
[[ "$COMMAND" == *"sync.py"* ]] && _allow

# skill-creator (read-only validation)
[[ "$COMMAND" == *"quick_validate.py"* ]] && _allow

# ---------------------------------------------------------------------------
# Scripts that are read-only only for specific subcommands / flags
# ---------------------------------------------------------------------------

# eks_ops.py: only pods and logs are read-only (exec and restart are not)
if [[ "$COMMAND" == *"eks_ops.py"* ]]; then
  if [[ "$COMMAND" =~ eks_ops\.py[[:space:]]+(pods|logs) ]]; then
    _allow
  fi
fi

# page_versions.py: --list and --fetch are read-only; --revert is not
if [[ "$COMMAND" == *"page_versions.py"* ]]; then
  if [[ "$COMMAND" =~ --(list|fetch) ]] && [[ "$COMMAND" != *"--revert"* ]]; then
    _allow
  fi
fi

# export_pages.py: --dry-run is safe (no local files written)
if [[ "$COMMAND" == *"export_pages.py"* ]]; then
  if [[ "$COMMAND" == *"--dry-run"* ]]; then
    _allow
  fi
fi

exit 0
