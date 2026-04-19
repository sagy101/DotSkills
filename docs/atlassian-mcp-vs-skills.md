# Atlassian Rovo MCP Server vs DotSkills — Feature Comparison

> Objective comparison of the [Atlassian Rovo MCP Server](https://support.atlassian.com/atlassian-rovo-mcp-server/docs/supported-tools/) against the DotSkills agent skills: **jira-manager**, **confluence-publisher**, and **bitbucket-manager**.
>
> Last updated: 2026-04-19

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
| **Add worklog** | `addWorklogToJiraIssue` | `update_ticket.py --worklog "2h" --worklog-comment "..."` | Tie |
| **Issue links (create)** | Not supported | `update_ticket.py --link "Blocks:PROJ-456"` — auto-resolves link type names | **Skill** |
| **Remote issue links (read)** | `getJiraIssueRemoteIssueLinks` | Not supported (reads regular issue links, not remote) | **MCP** |
| **Attachments** | Not supported | `--attachment` on create/update; images auto-extracted from markdown descriptions | **Skill** |
| **Field discovery** | `getJiraIssueTypeMetaWithFields` — create-field metadata for one type | `discover_fields.py` — full catalog, search, statuses, priorities, components, versions, sprints, fields-for-type, transitions | **Skill** — much richer discovery |
| **Issue type metadata** | `getJiraProjectIssueTypesMetadata` — list types in project | `discover_fields.py --fields-for-type` includes this | Tie |
| **Project listing** | `getVisibleJiraProjects` | Not supported (uses project key from config) | **MCP** |
| **User lookup** | `lookupJiraAccountId` — by name/email | Auto-resolves display name → accountId inline during updates | Tie |
| **Markdown → Jira markup** | Not supported (raw API) | Auto-converts markdown descriptions to Jira wiki markup | **Skill** |
| **Mermaid diagrams** | Not supported | Auto-renders ` ```mermaid ` blocks to PNG, uploads as attachments | **Skill** |
| **Diff local vs Jira** | Not supported | `diff_tickets.py` — local plan vs live issue comparison | **Skill** |
| **Estimate validation** | Not supported | `validate_estimates.py` — checks story points/time estimates | **Skill** |
| **Dry run** | Not supported | `--dry-run` on create, update, delete, bulk operations | **Skill** |
| **Auto-diagnosis** | Not supported | Hierarchy errors, field resolution failures → actionable fix suggestions | **Skill** |
| **Sprint management** | Not supported | `--sprint "Sprint 5"` on update/bulk update, board-based sprint listing | **Skill** |

**Jira totals: Skill wins 18, MCP wins 2, Tie 7**

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
| **Footer comments — create** | `createConfluenceFooterComment` (supports replies) | `page_comments.py add --page-id --body` | Tie (MCP supports replies) |
| **Inline comments — list** | `getConfluencePageInlineComments` | `page_comments.py list --page-id --inline` | Tie |
| **Inline comments — create** | `createConfluenceInlineComment` — tied to selected text | Not supported (requires selection context) | **MCP** |
| **List spaces** | `getConfluenceSpaces` | `list_spaces.py` with `--type` filter | Tie |
| **Pages in space** | `getPagesInConfluenceSpace` — filter by title/status/type | Not directly (uses manifest or discover) | **MCP** |
| **Page descendants** | `getConfluencePageDescendants` | `discover_pages.py` — walks tree, builds manifest | Tie |
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

**Confluence totals: Skill wins 17, MCP wins 2, Tie 8**

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
| **PR diff** | `bitbucketPullRequest.diff` | Not supported | **MCP** |
| **Approve PR** | `bitbucketPullRequest.approve` | Not supported | **MCP** |
| **Merge PR** | `bitbucketPullRequest.merge` | `pr_merge.py` — merge strategies (squash, fast-forward), precondition checks, `--dry-run` | **Skill** — strategies, preconditions |
| **Decline PR** | Not supported | `pr_decline.py` with `--dry-run` | **Skill** |
| **PR comment — add** | `bitbucketPullRequest.comment` | `pr_comment.py --body` — general, inline file-level, threaded replies | **Skill** — inline + replies |
| **PR comments — list** | `bitbucketPullRequest.comments` | `pr_comments.py` — threaded view, resolution status, filters (author, file, status, has-replies) | **Skill** — rich filtering |
| **PR comment — edit** | Not supported | `pr_comment.py --edit ID --body "..."` | **Skill** |
| **PR comment — delete** | Not supported | `pr_comment.py --delete ID [ID ...]` — bulk delete | **Skill** |
| **PR comment — resolve** | Not supported | `pr_comment.py --resolve ID [ID ...]` — bulk resolve | **Skill** |
| **PR build checks** | Not supported | `pr_checks.py --pr 42` | **Skill** |
| **Commit/branch build status** | Not supported | `build_status.py --commit X` / `--branch Y` | **Skill** |
| **Extract Jira issues from PR** | Not supported | `pr_jira.py --pr 42` — scans branch, title, description, commits | **Skill** |
| **Pipeline — list** | `bitbucketPipeline.list` | Not supported | **MCP** |
| **Pipeline — get** | `bitbucketPipeline.get` | Not supported | **MCP** |
| **Pipeline — run** | `bitbucketPipeline.run` | Not supported | **MCP** |
| **Pipeline — steps** | `bitbucketPipeline.steps` / `step.get` / `step.log` | Not supported | **MCP** |
| **Environments** | `bitbucketEnvironment` — list, get, create, update, delete | Not supported | **MCP** |
| **Deployments** | `bitbucketDeployment` — list, get | Not supported | **MCP** |
| **Dry run** | Not supported | `--dry-run` on create, update, merge, decline, comment, edit, delete | **Skill** |
| **Auto-detect repo from git** | Not supported (must specify) | Auto-detects workspace + repo from `git remote` | **Skill** |
| **Config defaults** | Not supported | Default reviewers, destination branch, workspace from `.bitbucket.json` | **Skill** |

**Bitbucket totals: Skill wins 12, MCP wins 13, Tie 3**

---

## Atlassian Platform (MCP-only products)

These are products/features exclusive to the MCP with no skill equivalent.

| Product | MCP Tools | Notes |
|---|---|---|
| **Jira Service Management** | `getJsmOpsAlerts`, `getJsmOpsScheduleInfo`, `getJsmOpsTeamInfo`, `updateJsmOpsAlert` | Operations alerts, on-call schedules, team management |
| **Compass** | `createCompassComponent`, `getCompassComponent`, `getCompassComponents`, `getCompassComponentLabels`, `getCompassComponentTypes`, `getCompassComponentsOwnedByMyTeams`, `getCompassComponentActivityEvents`, `createCompassComponentRelationship`, `deleteCompassComponent`, `deleteCompassComponentRelationship`, `createCompassCustomFieldDefinition`, `deleteCompassCustomFieldDefinition`, `getCompassCustomFieldDefinitions` | Service catalog, component relationships, custom fields |
| **Rovo Search** | `search` (beta) | Natural language search across Jira + Confluence (not CQL/JQL) |
| **Rovo Fetch** | `fetch` (beta) | Fetch any resource by Atlassian Resource Identifier (ARI) |
| **Teamwork Graph** | `getTeamworkGraphContext`, `getTeamworkGraphObject` | Cross-product context: linked PRs, builds, deployments, designs per issue/page/user |
| **User/site info** | `atlassianUserInfo`, `getAccessibleAtlassianResources` | Current user details, list accessible cloud sites |

---

## Cross-cutting Comparison

| Dimension | Atlassian MCP | DotSkills |
|---|---|---|
| **Product breadth** | 7 products in one server (Jira, Confluence, Bitbucket, JSM, Compass, Rovo, Teamwork Graph) | 3 products via 3 independent skills |
| **Depth per product** | Thin CRUD layer — basic get/create/edit/search/transition per product | Deep workflows — bulk ops, diffing, surgical edits, auto-diagnosis, markup conversion, mermaid rendering, field discovery, version management |
| **Setup** | Near-zero: cloud-hosted, OAuth 2.1 or API token | Python 3.10+, config file, API token per skill |
| **Dry run / preview** | None | Available on all write operations across all skills |
| **Bulk operations** | One item at a time | Bulk create, bulk update, batch publish, batch delete |
| **Error handling** | Standard HTTP errors | Auto-diagnosis with actionable fix suggestions (hierarchy errors, field resolution, transition resolution) |
| **Markdown support** | Confluence pages accept markdown body | Jira: auto-converts markdown → wiki markup. Confluence: full transform pipeline (mermaid, cross-links, attachments) |
| **Offline / air-gapped** | Cloud-only, requires internet | Local scripts, works air-gapped with any Jira/Confluence/Bitbucket instance |
| **Customization** | None — fixed tool set | Fully hackable Python scripts, config-driven |
| **AI-native features** | Rovo natural language search, Teamwork Graph cross-linking, ARI fetch | None (but designed for AI agents via SKILL.md prompt format) |
| **Auth model** | OAuth 2.1 (org-managed) or API token | API token (user-managed) |
| **Pipelines / CI** | Full pipeline management (list, get, run, steps, logs) | Build status checks only (no pipeline triggering) |
| **Deployment management** | Environments + Deployments CRUD | Not supported |

---

## Score Summary

| Product | Skill Wins | MCP Wins | Tie |
|---|---|---|---|
| Jira | **18** | 2 | 7 |
| Confluence | **17** | 2 | 8 |
| Bitbucket | 12 | **13** | 3 |
| Platform-only | 0 | **6 products** | 0 |

**Bottom line:** The skills dominate Jira and Confluence in depth (bulk ops, diffing, surgical edits, markup conversion, version management, field discovery). The MCP has broader Bitbucket coverage (pipelines, environments, deployments, repo content) and exclusive access to JSM, Compass, Rovo AI, and Teamwork Graph. For Bitbucket PR workflows specifically, the skill offers richer comment management (edit, delete, resolve, filter) and safety features (dry-run, precondition checks).
