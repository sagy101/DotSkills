---
name: team-notify
description: >
  Send notifications to developers via Slack or Microsoft Teams incoming webhooks.
  Notify on build results, PR status changes, ticket transitions, deployment outcomes,
  and custom workflow milestones. Use when the agent needs to alert a developer or team
  about CI/CD events, code review status, test results, or any event requiring human attention.
license: MIT
metadata:
  author: sagy101
  version: "1.0"
compatibility: >
  Python 3.8+. Pure stdlib — no pip install required. Works with Slack incoming webhooks
  (requires a Slack App) or Microsoft Teams Power Automate Workflows URLs (Adaptive Card format),
  or both simultaneously.
---

# Team Notify

Send Slack or Teams notifications from any agent workflow. One script call, zero boilerplate.

**Shorthand used below:** `$S` = `<skill_dir>/scripts`

## When to use this skill

Use when the agent needs to:
- **Notify** a developer that a CI/CD build passed or failed
- **Alert** the team when a PR is approved, merged, or needs attention
- **Announce** a deployment result (success, rollback, failure)
- **Escalate** an error or exception that requires human intervention
- **Update** a team channel on a ticket transition or workflow milestone
- **Send** a custom one-off message to a Slack or Teams channel

## Prerequisites

1. **Config**: `.notify.json` in project root and/or `~/.notify.json` for global defaults (see [CONFIG.md](references/CONFIG.md))
2. **Credentials**: webhook URL(s) exported as environment variables (e.g. `SLACK_WEBHOOK_URL`)

**Slack setup** (~5 min, one-time):
1. Go to [api.slack.com/apps](https://api.slack.com/apps) → Create New App → From scratch
2. Features → Incoming Webhooks → toggle **On**
3. Click **Add New Webhook to Workspace** → pick channel → Allow
4. Copy the webhook URL (`https://hooks.slack.com/services/...`) and export it

**Teams setup** (~10 min, one-time):
1. In Teams: right-click channel → **Workflows** (or `...` menu → Workflows)
2. Select **"Post to a channel when a webhook request is received"**
3. Follow the setup wizard, copy the generated URL and export it

No venv or pip install needed — all scripts use Python stdlib only.

## Configuration

Minimal `~/.notify.json`:

```json
{
  "channels": {
    "slack": { "webhook_env": "SLACK_WEBHOOK_URL" }
  },
  "default_channel": "slack"
}
```

Multi-channel example with Teams:

```json
{
  "channels": {
    "slack": { "webhook_env": "SLACK_WEBHOOK_URL" },
    "teams": { "webhook_env": "TEAMS_WEBHOOK_URL" }
  },
  "default_channel": "slack",
  "developer_mention": "@here"
}
```

See [CONFIG.md](references/CONFIG.md) for the full schema.

## Pre-flight checks

Run once per session before sending any notifications:

```bash
python3 $S/notify_preflight.py
```

Checks performed:
1. **Python** — version >= 3.8
2. **HTTP client** — stdlib urllib available
3. **Config** — `.notify.json` found and valid JSON with channels section
4. **Default channel** — `default_channel` exists in channels (or omitted)
5. **Credentials** — all `webhook_env` variables are SET (values never printed)

Exits 0 if all pass; 1 if any fail with actionable error messages.

## Workflow

1. **Validate** — run `notify_preflight.py` and confirm all checks pass
2. **Determine message** — identify what event occurred (build failed, PR merged, etc.) and choose the appropriate `--level`
3. **Plan the notification** — compose `--message`, `--title`, and optionally `--link`; present the planned text to the user before sending
4. **Execute** — call `notify.py` with the determined arguments
5. **Verify** — confirm `[OK]` output; report any errors to the user

## Operations

### Send a notification

```bash
# Basic message to default channel
python3 $S/notify.py --message "Build #42 passed on main"

# With title and severity level
python3 $S/notify.py --message "Unit tests failed (3 failures)" \
  --title "Test Failure" --level error

# With a link to the CI run
python3 $S/notify.py --message "Deploy to staging complete" \
  --title "Deployment" --level success \
  --link "https://staging.example.com"

# Mention the team (@here or configured mention)
python3 $S/notify.py --message "Prod deploy needs approval" \
  --title "Action Required" --level warning --mention

# Send to a specific channel
python3 $S/notify.py --message "PR #88 approved" --level success --channel slack

# Send to all configured channels
python3 $S/notify.py --message "Critical: DB connection failed" \
  --level error --channel all --mention

# With explicit config path
python3 $S/notify.py --message "Hello" --config /path/to/.notify.json
```

### Run pre-flight

```bash
python3 $S/notify_preflight.py
python3 $S/notify_preflight.py --config /path/to/.notify.json
```

## Important rules

1. **Never print webhook URLs** — they are secrets. Only print the env var name.
2. **Show message before sending** — for any non-automated send, present the planned message text to the user and wait for confirmation.
3. **Use `--mention` sparingly** — only when the event genuinely needs human attention right away.
4. **Choose `--level` accurately** — `info` for routine updates, `success` for completions, `warning` for issues that don't block, `error` for failures requiring action.
5. **Exit codes are meaningful** — exit 0 = sent, exit 1 = HTTP/network error (retry or report), exit 2 = config/credential error (fix config first).

## Error handling

| Exit | Cause | Action |
|------|-------|--------|
| 0 | All messages sent | Continue |
| 1 | HTTP error (4xx/5xx) or network failure | Check webhook URL is valid and env var is correctly set; inspect error message |
| 2 | Config not found | Create `.notify.json` per CONFIG.md |
| 2 | `webhook_env` variable not set | Export the env var: `export SLACK_WEBHOOK_URL="..."` |
| 2 | Config is invalid JSON | Fix JSON syntax errors |
| 2 | `--channel` not in config | Add the channel to config or use a configured channel name |

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `[ERROR] teams: HTTP 400` | URL is not a Power Automate Workflows URL | Use a Workflows URL ("Post to a channel when a webhook request is received") |
| `[ERROR] slack: HTTP 403` | Webhook URL revoked or channel deleted | Regenerate the webhook URL in Slack App settings |
| `[ERROR] teams: HTTP 404` | Workflow URL expired or connector deleted | Recreate the workflow in Teams; update `TEAMS_WEBHOOK_URL` |
| Config not found | Wrong working directory | Run from project root, or pass `--config ~/.notify.json` |
| `[FAIL] Credentials` in preflight | Env var not exported in this shell | Run `export SLACK_WEBHOOK_URL="..."` or add to shell profile |
| Teams message sent but not visible | Workflow owner is inactive | Add a co-owner to the Power Automate workflow |
