# Configuration Reference

The `.bitbucket.json` file configures the bitbucket-manager skill. It can live in:
- **Project root** — project-specific settings (e.g. `default_reviewers`, `default_destination`)
- **Home directory** (`~/.bitbucket.json`) — global defaults (e.g. `workspace`, `credentials`)

If both exist, they are **deep-merged** (project-level wins on conflicts).

## Full schema

```json
{
  "workspace": "myworkspace",
  "credentials": {
    "email_env": "BITBUCKET_EMAIL",
    "token_env": "BITBUCKET_TOKEN"
  },
  "env_file": ".env",
  "default_reviewers": ["user1-uuid", "user2-uuid"],
  "default_destination": "master"
}
```

## Field descriptions

| Field | Required | Default | Description |
|---|---|---|---|
| `workspace` | Yes | — | Bitbucket workspace slug |
| `credentials.email_env` | No | `"BITBUCKET_EMAIL"` | Environment variable name for the Bitbucket email/username |
| `credentials.token_env` | No | `"BITBUCKET_TOKEN"` | Environment variable name for the app password |
| `env_file` | No | `null` | Optional path to a `.env` file. Absolute paths are used as-is (useful in global config). Relative paths resolve against project root (traversal-protected). |
| `default_reviewers` | No | `[]` | List of reviewer UUIDs added to new PRs when `--reviewers` is omitted |
| `default_destination` | No | `"master"` | Default destination branch for new PRs when `--destination` is omitted |

## Config resolution order

1. Walk up from CWD looking for `.bitbucket.json` (project-level)
2. Check `~/.bitbucket.json` (global defaults)
3. If both exist, deep-merge them (project-level wins)
4. If neither exists, error with copy-pastable JSON template

## Global + per-project split (recommended)

Put shared settings in `~/.bitbucket.json`:
```json
{
  "workspace": "myworkspace",
  "credentials": {
    "email_env": "BITBUCKET_EMAIL",
    "token_env": "BITBUCKET_TOKEN"
  }
}
```

Then each project only needs optional overrides in `.bitbucket.json`:
```json
{
  "default_reviewers": ["user1-uuid", "user2-uuid"],
  "default_destination": "develop"
}
```

## Credential resolution order

1. If `env_file` is set, load variables from that file first
2. Then check OS environment variables
3. The variable names are taken from `credentials.email_env` and `credentials.token_env`

**Recommended**: export credentials globally in your shell profile rather than using per-project `.env` files:
- **zsh**: `echo 'export BITBUCKET_TOKEN="<value>"' >> ~/.zshrc && source ~/.zshrc`
- **bash**: `echo 'export BITBUCKET_TOKEN="<value>"' >> ~/.bashrc && source ~/.bashrc`
- **fish**: `set -Ux BITBUCKET_TOKEN '<value>'`

## App password setup

Create a Bitbucket app password at **Bitbucket Settings > Personal settings > App passwords**.

Required scopes:
- `Repositories: Read` — for listing repos and reading PR details
- `Repositories: Write` — for build status operations
- `Pull requests: Read` — for listing and reading PRs
- `Pull requests: Write` — for creating, updating, merging, declining PRs and posting comments
