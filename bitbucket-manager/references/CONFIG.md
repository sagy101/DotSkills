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
    "auth_mode": "basic",
    "email_env": "BITBUCKET_EMAIL",
    "token_env": "BITBUCKET_TOKEN"
  },
  "env_file": ".env",
  "repo_tokens": {
    "myworkspace/example-repo": {
      "token_env": "MY_REPO_BITBUCKET_TOKEN"
    }
  },
  "default_reviewers": ["user1-uuid", "user2-uuid"],
  "default_destination": "master"
}
```

## Field descriptions

| Field | Required | Default | Description |
|---|---|---|---|
| `workspace` | Yes | — | Bitbucket workspace slug |
| `credentials.auth_mode` | No | `"basic"` | Default auth mode. `"basic"` is the normal mode for Atlassian email + personal Bitbucket API token. `"bearer"` is kept as a legacy compatibility mode for a single direct bearer token. |
| `credentials.email_env` | No | `"BITBUCKET_EMAIL"` | Environment variable name for the Bitbucket email/username |
| `credentials.token_env` | No | `"BITBUCKET_TOKEN"` | Environment variable name for the API token |
| `env_file` | No | `null` | Optional path to a `.env` file. Absolute paths are used as-is (useful in global config). Relative paths resolve against project root (traversal-protected). If the file is missing, the skill warns and falls back to normal shell environment variables. |
| `repo_tokens` | No | `{}` | Optional map of `workspace/repo` to repository-token config. Used as a fallback when default `basic` auth is unavailable or Bitbucket rejects it. |
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
    "auth_mode": "basic",
    "email_env": "BITBUCKET_EMAIL",
    "token_env": "BITBUCKET_TOKEN"
  },
  "repo_tokens": {
    "myworkspace/example-repo": {
      "token_env": "MY_REPO_BITBUCKET_TOKEN"
    }
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

1. If `env_file` is set and exists, load variables from that file first
2. Then check OS environment variables
3. The variable names are taken from `credentials.email_env` and `credentials.token_env`

**Recommended**: export credentials globally in your shell profile rather than using per-project `.env` files:
- **zsh**: `echo 'export BITBUCKET_TOKEN="<value>"' >> ~/.zshrc && source ~/.zshrc`
- **bash**: `echo 'export BITBUCKET_TOKEN="<value>"' >> ~/.bashrc && source ~/.bashrc`
- **fish**: `set -Ux BITBUCKET_TOKEN '<value>'`

## API token setup

Prefer **Bitbucket Cloud API tokens** with the needed REST scopes. Atlassian is transitioning away from app passwords, so new setups should use API tokens unless you are maintaining an older legacy credential.

Create a Bitbucket API token at **Bitbucket Settings > Personal settings > API tokens**.

Recommended minimum scopes:
- `Repositories: Read` — for repository detection, PR repo metadata, and repository endpoints
- `Pull requests: Read` — for listing and reading PRs plus comment retrieval
- `Pipelines: Read` — for pipeline status, steps, logs, and checks-related visibility
- `Workspace: Read` — for workspace-scoped lookups used by some listing and discovery flows
- `Pull requests: Write` — for creating, updating, merging, declining PRs and posting comments

Not normally required for this skill's common workflows:
- `Repositories: Write`
- `Pipelines: Write`

If SSH git commands work but the REST scripts still return `401`, the most common causes are:
- the token is invalid or expired
- the token is the wrong credential type for Bitbucket Cloud REST auth
- the wrong email is paired with the token in Basic auth

If the REST scripts return `403`, the token was accepted but is missing one or more required scopes for that endpoint.

## Repository-token fallback

Prefer one personal Bitbucket API token with scopes for normal multi-repo use. If that path is blocked or broken in your Atlassian org, configure repository access tokens in `repo_tokens`.

Recommended pattern:

```json
{
  "workspace": "firelayers",
  "credentials": {
    "auth_mode": "basic",
    "email_env": "BITBUCKET_EMAIL",
    "token_env": "BITBUCKET_TOKEN"
  },
  "repo_tokens": {
    "firelayers/dotskills": {
      "token_env": "DOTSKILLS_BITBUCKET_TOKEN"
    }
  }
}
```

Notes:
- The skill tries default `basic` auth first, and that is the recommended normal setup.
- If Bitbucket rejects default `basic` auth for a repo, the skill checks `repo_tokens["workspace/repo"]`.
- Repository access tokens are scoped to a single repo, so preflight validates against the current target repo.
- If no repo token exists for the target repo, the skill should fail with an actionable message telling the agent to ask the human to configure one.

## Legacy direct bearer mode

For compatibility, the skill still accepts:

```json
{
  "workspace": "firelayers",
  "credentials": {
    "auth_mode": "bearer",
    "token_env": "BITBUCKET_TOKEN"
  }
}
```

Use this only when you intentionally want one bearer token as the primary auth path for the whole current repo context. Prefer `repo_tokens` for normal multi-repo setups.
