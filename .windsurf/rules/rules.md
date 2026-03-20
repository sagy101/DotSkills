---
trigger: always_on
---

# DotSkills Command Approval Rules

These rules define which skill script commands Cascade may run automatically
and which always require explicit user approval before execution.

## Auto-approve — run without asking

These scripts are read-only: they only fetch, list, or query external systems.
Run them directly without prompting the user.

### jira-manager
- `fetch_tickets.py` — fetch tickets by key, JQL, filter, board, or sprint
- `discover_fields.py` — discover Jira fields and issue types (read + apply to config)
- `diff_tickets.py` — diff local manifest against Jira (read-only comparison)
- `validate_estimates.py` — validate story point sums (read-only)

### bitbucket-manager
- `bb_preflight.py` — connectivity and config checks
- `pr_get.py` — get PR details
- `pr_list.py` — list PRs
- `pr_comments.py` — list/view PR comments (read-only)
- `pr_checks.py` — view PR build checks
- `build_status.py` — view commit or branch pipeline status
- `pr_jira.py` — extract Jira issue keys from a PR
- `repo_list.py` — list workspace repositories

### jenkins-manager
- `jenkins_preflight.py` — connectivity and config checks
- `get_status.py` — check build status
- `get_logs.py` — view build console logs
- `get_test_results.py` — view test results
- `get_changesets.py` — view commits included in a build
- `get_queue_item.py` — check queue item status
- `list_folders.py` — list top-level Jenkins folders
- `list_jobs.py` — list jobs in a folder

### eks-pod-ops
- `eks_preflight.py` — connectivity and config checks
- `eks_ops.py pods` — list or describe pods (read-only)
- `eks_ops.py logs` — read pod logs (read-only)

### confluence-publisher
- `diff_pages.py` — diff local markdown against Confluence (read-only)
- `validate_manifest.py` — validate manifest against Confluence (read-only)
- `verify_hierarchy.py` — verify page hierarchy on Confluence (read-only)
- `discover_pages.py` — discover existing Confluence pages (read-only)
- `diff_versions.py` — compare two page versions (read-only)
- `page_versions.py --list` — browse version history (read-only)
- `page_versions.py --fetch` — fetch a specific version's content (read-only)

### skill-sync / skill-creator
- `sync.py` — distribute skills to IDE directories (no external system writes)
- `quick_validate.py` — validate a skill against the spec (read-only)

---

## Always ask — require explicit user approval

These scripts create, update, delete, or trigger changes in external systems.
**Always show the plan and wait for the user to confirm before running.**

### jira-manager
- `create_ticket.py` — creates a new Jira issue
- `bulk_create.py` — creates multiple Jira issues
- `update_ticket.py` — updates fields, status, comments, or links
- `bulk_update.py` — bulk updates across multiple tickets
- `delete_ticket.py` — deletes a Jira issue (irreversible)

### bitbucket-manager
- `pr_create.py` — opens a new pull request
- `pr_update.py` — updates PR title, description, or reviewers
- `pr_merge.py` — merges a pull request
- `pr_decline.py` — declines a pull request
- `pr_comment.py` — adds, edits, deletes, or resolves PR comments

### jenkins-manager
- `trigger_build.py` — triggers a Jenkins build

### eks-pod-ops
- `eks_ops.py exec` — executes a command inside a pod
- `eks_ops.py restart` — restarts a deployment (rollout restart)

### confluence-publisher
- `publish_page.py` — creates or updates a Confluence page
- `delete_page.py` — deletes a Confluence page (irreversible)
- `surgical_edit.py` — targeted in-place edits to a Confluence page
- `replace_element.py` — replaces a structural element on a Confluence page
- `page_versions.py --revert` — reverts a page to a previous version
- `export_pages.py` — exports Confluence pages to local files (overwrites local files; `--dry-run` is safe)
