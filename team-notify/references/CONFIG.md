# Configuration Reference

The `.notify.json` file configures the team-notify skill. It can live in:
- **Project root** — project-specific settings (e.g. `default_channel`, `developer_mention`)
- **Home directory** (`~/.notify.json`) — global defaults with webhook env var names

If both exist, they are **deep-merged** (project-level wins on conflicts).

## Full schema

```json
{
  "channels": {
    "slack": {
      "webhook_env": "SLACK_WEBHOOK_URL"
    },
    "teams": {
      "webhook_env": "TEAMS_WEBHOOK_URL"
    }
  },
  "default_channel": "slack",
  "developer_mention": "@here"
}
```

## Field descriptions

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `channels` | Yes | — | Map of channel name → channel config. Keys `slack` and `teams` are the supported types. |
| `channels.<name>.webhook_env` | Yes | — | Name of the environment variable that holds the webhook URL. Never put the URL itself here. |
| `default_channel` | No | `"slack"` | Channel used when `--channel` is not passed. Use `"all"` to send to every configured channel by default. |
| `developer_mention` | No | `""` | Text prepended to messages when `--mention` flag is used. E.g. `"@here"`, `"@channel"`, `"@jane"`. |

## Config resolution order

1. Walk up from CWD looking for `.notify.json` (project-level)
2. Check `~/.notify.json` (global defaults)
3. If both exist, deep-merge them (project-level wins)
4. If neither exists, error with copy-pastable JSON template

## Global + per-project split (recommended)

Put webhook references in `~/.notify.json` so they apply everywhere:
```json
{
  "channels": {
    "slack": { "webhook_env": "SLACK_WEBHOOK_URL" },
    "teams": { "webhook_env": "TEAMS_WEBHOOK_URL" }
  },
  "developer_mention": "@here"
}
```

Then each project can override just what it needs in `.notify.json`:
```json
{
  "default_channel": "teams"
}
```

## Credential setup

Webhook URLs must be exported as environment variables **before** running the scripts:

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T.../B.../xxx"
export TEAMS_WEBHOOK_URL="https://prod-xx.westeurope.logic.azure.com/..."
```

**Recommended**: add these exports to your shell profile (`~/.zshrc`, `~/.bashrc`) so they persist across sessions.

The `webhook_env` config field only stores the **name** of the env var, never the URL value. This keeps credentials out of config files.

## Getting webhook URLs

### Slack
1. Go to [api.slack.com/apps](https://api.slack.com/apps) → Create New App → From scratch
2. Features → **Incoming Webhooks** → toggle **On**
3. Click **Add New Webhook to Workspace** → pick channel → Allow
4. Copy URL: `https://hooks.slack.com/services/T.../B.../xxx`

Treat this URL as a password — anyone with it can post to your channel.

### Teams — Power Automate Workflows
1. In Teams: right-click channel → **Workflows** (or `...` menu → Workflows)
2. Select **"Post to a channel when a webhook request is received"**
3. Follow the setup wizard, copy the generated URL
