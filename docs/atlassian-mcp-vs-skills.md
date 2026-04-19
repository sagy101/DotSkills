# Atlassian MCP vs DotSkills — Jira, Confluence, and Bitbucket Comparison

> Objective comparison of the [Atlassian Rovo MCP Server](https://support.atlassian.com/atlassian-rovo-mcp-server/docs/supported-tools/) against the DotSkills agent skills: **jira-manager**, **confluence-publisher**, and **bitbucket-manager**.
>
> Last updated: 2026-04-19

Comparison notes:
- This compares only the overlapping Jira, Confluence, and Bitbucket surfaces.
- It intentionally does not score Jira Service Management, Compass, Rovo Search/Fetch, Teamwork Graph, or other Atlassian products with no local skill equivalent.
- This compares the MCP tools listed in Atlassian's supported-tools page against capabilities that are actually implemented in this repo's scripts and skill docs.
- "Tie" means both sides support the capability at a broadly comparable functional level, even if the UX or ergonomics differ.
- The skills intentionally do not compete on wrappers for low-value native git/CLI operations when local tooling is clearly simpler.
- For Confluence inline comments, the skill follows the live Cloud API states such as `resolved` and `reopened` rather than inventing friendlier aliases.
- Context-efficiency claims are inherently client-dependent. Public anecdotes and Atlassian Labs' `mcp-compressor` project suggest preloaded Atlassian MCP tool descriptions often cost roughly `~7k-10k` tokens, with some clients/users reporting materially higher numbers in specific sessions. Skills are usually lighter in this repo's environment because only a short skill registry is present up front and full `SKILL.md` content is loaded on demand.

---

## Jira

| Capability | Atlassian MCP | jira-manager Skill | Advantage |
|---|---|---|---|
| **Get issue by key** | `getJiraIssue` — single issue by ID/key | `fetch_tickets.py --key` — single or `--key X --key Y` (repeatable, auto-coalesces) | **Skill** — repeatable `--key` |
| **Search (JQL)** | `searchJiraIssuesUsingJql` | `fetch_tickets.py --jql` | Tie |
| **Search (saved filter)** | Not supported | `fetch_tickets.py --filter FILTER_ID` — runs a saved Jira filter | **Skill** |
| **Fetch children** | Not supported | `fetch_tickets.py --children-of EPIC-1` — recursive child fetch | **Skill** |
| **Fetch by board** | Not supported | `fetch_tickets.py --board-id 123` — board backlog/sprint fetch | **Skill** |
| **List boards** | Not supported | `fetch_tickets.py --boards` — discover Scrum/Kanban boards | **Skill** |
| **Create issue** | `createJiraIssue` — single issue | `create_ticket.py` — single, with `--copy-fields-from`, auto-diagnosis on failure | **Skill** — copy-fields, auto-fix |
| **Bulk create** | Not supported (one at a time) | `bulk_create.py` — batch from markdown/JSON, epics+stories+subtasks | **Skill** |
| **Update issue** | `editJiraIssue` — field updates | `update_ticket.py` — any field via `--set`, plus `--status`, `--sprint`, `--parent`, `--link`, `--attachment`, `--comment`, `--worklog` in one call | **Skill** — richer single-call |
| **Bulk update** | Not supported | `bulk_update.py` — batch by JQL, board, or ticket list | **Skill** |
| **Delete issue** | Not supported | `delete_ticket.py` — with preview/confirm | **Skill** |
| **Transitions — list** | `getTransitionsForJiraIssue` | `discover_fields.py --transitions ISSUE-KEY` | Tie |
| **Transitions — execute** | `transitionJiraIssue` | `update_ticket.py --status "Done"` — auto-resolves name → transition ID | Tie (skill adds name resolution) |
| **Add comment** | `addCommentToJiraIssue` | `update_ticket.py --comment` | Tie |
| **Edit comment** | Not supported | `issue_comments.py edit --key PROJ-101 --comment-id 123 --body "..."` | **Skill** |
| **Delete comment** | Not supported | `issue_comments.py delete --key PROJ-101 --comment-id 123` | **Skill** |
| **Add worklog** | `addWorklogToJiraIssue` | `update_ticket.py --worklog "2h" --worklog-comment "..."` | Tie |
| **Issue links (create)** | Not supported | `update_ticket.py --link "Blocks:PROJ-456"` — auto-resolves link type names | **Skill** |
| **Remote issue links (read)** | `getJiraIssueRemoteIssueLinks` | `fetch_tickets.py --include-remote-links` — detail/json output enrichment | Tie |
| **Attachments** | Not supported | `--attachment` on create/update; images auto-extracted from markdown descriptions | **Skill** |
| **Field discovery** | `getJiraIssueTypeMetaWithFields` — create-field metadata for one type | `discover_fields.py` — full catalog, search, statuses, priorities, components, versions, sprints, fields-for-type, transitions | **Skill** — much richer discovery |
| **Issue type metadata** | `getJiraProjectIssueTypesMetadata` — list types in project | `discover_fields.py --fields-for-type` includes this | Tie |
| **Project listing** | `getVisibleJiraProjects` | `list_projects.py` — visible projects in table output | Tie |
| **User lookup** | `lookupJiraAccountId` — by name/email | Auto-resolves display name → accountId inline during updates | Tie |
| **Markdown → Jira markup** | Not supported (raw API) | Auto-converts markdown descriptions to Jira wiki markup | **Skill** |
| **Mermaid diagrams** | Not supported | Auto-renders ` ```mermaid ` blocks to PNG, uploads as attachments | **Skill** |
| **Diff local vs Jira** | Not supported | `diff_tickets.py` — local plan vs live issue comparison | **Skill** |
| **Estimate validation** | Not supported | `validate_estimates.py` — checks story points/time estimates | **Skill** |
| **Dry run** | Not supported | `--dry-run` on create, update, delete, bulk operations | **Skill** |
| **Auto-diagnosis** | Not supported | Hierarchy errors, field resolution failures → actionable fix suggestions | **Skill** |
| **Sprint management** | Not supported | `--sprint "Sprint 5"` on update/bulk update, board-based sprint listing | **Skill** |

**Jira totals: Skill wins 20, MCP wins 0, Tie 9**

---

## Confluence

| Capability | Atlassian MCP | confluence-publisher Skill | Advantage |
|---|---|---|---|
| **Get page** | `getConfluencePage` — by ID, body as markdown | `fetch_page()` — by ID, optionally at a specific version | Tie |
| **Create page** | `createConfluencePage` — single page, markdown body | `publish_page.py` — batch tree publish, auto cross-page links, mermaid rendering, emoji | **Skill** — tree publish, transforms |
| **Update page** | `updateConfluencePage` — full body replace | `publish_page.py --mode update` + `surgical_edit.py` (targeted find/replace without full overwrite) | **Skill** — surgical edits |
| **Delete page** | Not supported | `delete_page.py` — by manifest key or page ID, with `--dry-run` | **Skill** |
| **Search (CQL)** | `searchConfluenceUsingCql` | `search_pages.py --cql` | Tie |
| **Footer comments — list** | `getConfluencePageFooterComments` | `page_comments.py list --page-id` | Tie |
| **Footer comments — create** | `createConfluenceFooterComment` (supports replies) | `page_comments.py add --page-id --body` | Tie |
| **Footer comments — reply** | `createConfluenceFooterComment` — reply via parent | `page_comments.py reply --page-id --parent-comment-id --body` | Tie |
| **Footer comments — edit** | Not supported | `page_comments.py edit --comment-id ... --body ...` | **Skill** |
| **Footer comments — delete** | Not supported | `page_comments.py delete --comment-id ...` | **Skill** |
| **Inline comments — list** | `getConfluencePageInlineComments` | `page_comments.py list --page-id --inline` | Tie |
| **Inline comments — create** | `createConfluenceInlineComment` — tied to selected text | `page_comments.py add --page-id --inline --inline-text-selection ...` | Tie |
| **Inline comments — edit** | Not supported | `page_comments.py edit --comment-id ... --inline --body ...` | **Skill** |
| **Inline comments — delete** | Not supported | `page_comments.py delete --comment-id ... --inline` | **Skill** |
| **Inline comments — resolve / reopen** | Not supported | `page_comments.py resolve --comment-id 123 --inline` and `page_comments.py unresolve --comment-id 123 --inline` | **Skill** |
| **List spaces** | `getConfluenceSpaces` | `list_spaces.py` with `--type` filter | Tie |
| **Pages in space** | `getPagesInConfluenceSpace` — filter by title/status/type | `list_pages.py --space-key --title --status --type` | Tie |
| **Page descendants** | `getConfluencePageDescendants` | `discover_pages.py` — walks tree, builds manifest | Tie |
| **Page likes (read)** | Not supported | `page_comments.py likes --page-id 123` | **Skill** |
| **Comment likes (read)** | Not supported | `page_comments.py likes --comment-id 456 [--inline]` | **Skill** |
| **Likes / reactions (write)** | Not supported | Not supported | Tie |
| **Version history** | Not supported | `page_versions.py --list` — browse all versions | **Skill** |
| **Fetch specific version** | Not supported | `page_versions.py --fetch 56` — content at any version | **Skill** |
| **Version diff** | Not supported | `diff_versions.py` — compare two versions, section integrity check | **Skill** |
| **Page revert** | Not supported | `page_versions.py --revert 56 --confirm` | **Skill** |
| **Diff local vs Confluence** | Not supported | `diff_pages.py` — normalized markdown diff with mermaid handling | **Skill** |
| **Export to markdown** | Not supported | `export_pages.py` — single page, manifest, or full tree | **Skill** |
| **Surgical HTML edit** | Not supported | `surgical_edit.py` — targeted find/replace preserving manual formatting | **Skill** |
| **Structural element edit** | Not supported | `replace_element.py` — extract/replace tables, sections, lists; `--new-md` for markdown-to-HTML | **Skill** |
| **Append content** | Not supported | `replace_element.py --append-after` / `--append-end` | **Skill** |
| **Mermaid rendering** | Not supported | Auto-renders mermaid blocks to PNG in publish and `render_mermaid.py` for existing pages | **Skill** |
| **Cross-page link rewriting** | Not supported | Auto-rewrites `[text](file.md)` → Confluence page-link macros via manifest | **Skill** |
| **Attachment links** | Not supported | `attachment:filename` scheme → Confluence attachment macros | **Skill** |
| **Attachment upload** | Not supported | `--attachments` on publish, `--attachments-only` for standalone upload | **Skill** |
| **Manifest-based sync** | Not supported | `.confluence-manifest.json` tracks page ↔ file mapping | **Skill** |
| **Validate manifest** | Not supported | `validate_manifest.py` — checks disk + Confluence consistency | **Skill** |
| **Verify hierarchy** | Not supported | `verify_hierarchy.py` — shows full page tree | **Skill** |
| **Dry run** | Not supported | `--dry-run` on publish, surgical edit, replace, revert | **Skill** |

**Confluence totals: Skill wins 24, MCP wins 0, Tie 11**

---

## Bitbucket

| Capability | Atlassian MCP | bitbucket-manager Skill | Advantage |
|---|---|---|---|
| **List workspaces** | `bitbucketWorkspace.list` | Not supported (uses config) | **MCP** |
| **Get workspace** | `bitbucketWorkspace.get` | Not supported | **MCP** |
| **List repos** | `bitbucketRepository.list` | `repo_list.py` with `--name` filter | Tie |
| **Get repo** | `bitbucketRepository.get` | Not directly (auto-detected from git remote) | **MCP** |
| **Get branch** | `bitbucketRepoContent.branch.get` | Not supported | **MCP** |
| **Create branch** | `bitbucketRepoContent.branch.create` | Not supported | **MCP** |
| **Create commit** | `bitbucketRepoContent.commit.create` | Not supported | **MCP** |
| **Get commit** | `bitbucketRepoContent.commit.get` | Not supported (fetches build status for a commit) | **MCP** |
| **Get file contents** | `bitbucketRepoContent.files.get` | Not supported | **MCP** |
| **Create PR** | `bitbucketPullRequest.create` | `pr_create.py` with `--dry-run`, default reviewers from config | **Skill** — dry-run, config defaults |
| **Get PR** | `bitbucketPullRequest.get` | `pr_get.py` — shows reviewers with approval status | Tie |
| **List PRs** | `bitbucketPullRequest.list` | `pr_list.py` — filter by state, author, branch | Tie |
| **PR diff** | `bitbucketPullRequest.diff` | `pr_diff.py` — raw diff, summary, JSON metadata | Tie |
| **Approve PR** | `bitbucketPullRequest.approve` | Not supported | **MCP** |
| **Merge PR** | `bitbucketPullRequest.merge` | `pr_merge.py` — merge strategies (squash, fast-forward), precondition checks, `--dry-run` | **Skill** — strategies, preconditions |
| **Decline PR** | Not supported | `pr_decline.py` with `--dry-run` | **Skill** |
| **PR comment — add** | `bitbucketPullRequest.comment` | `pr_comment.py --body` — general, inline file-level, threaded replies | **Skill** — inline + replies |
| **PR comments — list** | `bitbucketPullRequest.comments` | `pr_comments.py` — threaded view, resolution status, filters (author, file, status, has-replies) | **Skill** — rich filtering |
| **PR comment — edit** | Not supported | `pr_comment.py --edit ID --body "..."` | **Skill** |
| **PR comment — delete** | Not supported | `pr_comment.py --delete ID [ID ...]` — bulk delete | **Skill** |
| **PR comment — resolve** | Not supported | `pr_comment.py --resolve ID [ID ...]` — bulk resolve | **Skill** |
| **PR comment — reopen** | Not supported | `pr_comment.py --unresolve ID [ID ...]` — bulk reopen for resolved inline threads | **Skill** |
| **PR emoji reactions** | Not supported | Not supported | Tie |
| **PR build checks** | Not supported | `pr_checks.py --pr 42` | **Skill** |
| **Commit/branch build status** | Not supported | `build_status.py --commit X` / `--branch Y` | **Skill** |
| **Extract Jira issues from PR** | Not supported | `pr_jira.py --pr 42` — scans branch, title, description, commits | **Skill** |
| **Pipeline — list** | `bitbucketPipeline.list` | `pipeline_list.py` | Tie |
| **Pipeline — get** | `bitbucketPipeline.get` | `pipeline_get.py` | Tie |
| **Pipeline — run** | `bitbucketPipeline.run` | `pipeline_run.py` with `--dry-run` | Tie |
| **Pipeline — steps / step.get / step.log** | `bitbucketPipeline.steps` / `step.get` / `step.log` | `pipeline_steps.py`, `pipeline_step_get.py`, `pipeline_log.py` | Tie |
| **Environments — list/get** | `bitbucketEnvironment` — list, get | `environment_list.py`, `environment_get.py` | Tie |
| **Environments — create/update/delete** | `bitbucketEnvironment` — create, update, delete | Not supported | **MCP** |
| **Deployments** | `bitbucketDeployment` — list, get | `deployment_list.py`, `deployment_get.py` | Tie |
| **Dry run** | Not supported | `--dry-run` on create, update, merge, decline, comment, edit, delete | **Skill** |
| **Auto-detect repo from git** | Not supported (must specify) | Auto-detects workspace + repo from `git remote` | **Skill** |
| **Config defaults** | Not supported | Default reviewers, destination branch, workspace from `.bitbucket.json` | **Skill** |

**Bitbucket totals: Skill wins 13, MCP wins 7, Tie 11**

---

## Score Summary

| Product | Skill Wins | MCP Wins | Tie |
|---|---|---|---|
| Jira | **20** | 0 | 9 |
| Confluence | **24** | 0 | 11 |
| Bitbucket | **13** | 7 | 11 |

**Bottom line within these three products:** the skills now tie or beat the MCP across most compared Jira and Confluence workflows and close much of the Bitbucket gap for PR, pipeline, environment, and deployment reads. The MCP still keeps clear advantages on several Bitbucket administrative and repository-content surfaces.
