# Windsurf Read Command Whitelist

Read-only skill commands that can be safely auto-approved. Add these patterns to
your Windsurf allowed-commands configuration to reduce approval prompts during
agent sessions.

These commands only **read** data — they never create, update, or delete resources.

## jira-manager

```
*/scripts/fetch_tickets.py *
*/scripts/discover_fields.py *
*/scripts/diff_tickets.py *
*/scripts/validate_estimates.py *
*/scripts/jira_setup_env.py
```

## bitbucket-manager

```
*/scripts/bb_preflight.py *
*/scripts/pr_get.py *
*/scripts/pr_list.py *
*/scripts/pr_comments.py *
*/scripts/pr_checks.py *
*/scripts/build_status.py *
*/scripts/pr_jira.py *
*/scripts/repo_list.py *
```

## jenkins-manager

```
*/scripts/jenkins_preflight.py *
*/scripts/get_status.py *
*/scripts/get_logs.py *
*/scripts/get_test_results.py *
*/scripts/get_changesets.py *
*/scripts/get_queue_item.py *
*/scripts/list_folders.py *
*/scripts/list_jobs.py *
```

## eks-pod-ops

```
*/scripts/eks_preflight.py *
*/scripts/eks_ops.py pods *
*/scripts/eks_ops.py logs *
```

## sbt-build-test

```
*/scripts/sbt_status.sh *
```

## confluence-publisher

```
*/scripts/validate_manifest.py *
*/scripts/verify_hierarchy.py *
*/scripts/discover_pages.py *
*/scripts/diff_pages.py *
*/scripts/diff_versions.py *
*/scripts/page_versions.py --list *
*/scripts/page_versions.py --fetch *
*/scripts/confluence_setup_env.py
```

## codebase-analyzer

```
*/scripts/analyze.py *
*/scripts/analyzer_setup_env.py
```

## review-prompts

```
*/scripts/build-prompt.py *
```

## codex-subagent

```
*/scripts/run_codex.py --mode read-only *
*/scripts/run_codex.py --status *
```
