# Configuration Reference

The `.jenkins.json` file configures the jenkins-manager skill. It can live in:
- **Project root** — project-specific settings (e.g. `job_cache`, `default_branch`)
- **Home directory** (`~/.jenkins.json`) — global defaults (e.g. `base_url`, `credentials`)

If both exist, they are **deep-merged** (project-level wins on conflicts).

## Full schema

```json
{
  "base_url": "https://your-jenkins-instance.example.com",
  "credentials": {
    "username_env": "JENKINS_USER",
    "token_env": "JENKINS_TOKEN"
  },
  "env_file": "/absolute/path/to/.env",
  "job_cache": {
    "my-repo": "MyFolder/my-repo",
    "another-repo": "AnotherFolder/another-repo"
  },
  "default_branch": "main",
  "ssl_verify": true
}
```

## Field descriptions

| Field | Required | Default | Description |
|---|---|---|---|
| `base_url` | Yes | — | Jenkins server URL (no trailing slash) |
| `credentials.username_env` | No | `"JENKINS_USER"` | Environment variable name for the Jenkins username |
| `credentials.token_env` | No | `"JENKINS_TOKEN"` | Environment variable name for the Jenkins API token |
| `env_file` | No | `null` | Optional path to a `.env` file. Can be at top level or under `credentials`. Absolute paths are used as-is (useful in global config). Relative paths resolve against project root (traversal-protected). |
| `job_cache` | No | `{}` | Map of repo name → `folder/job` path for fast pipeline lookups. Avoids API search on every run. |
| `default_branch` | No | `null` | Default branch for status lookups when not in a git repo. Auto-detects from current git branch if not set. |
| `default_username` | No | `null` | Fallback username when `JENKINS_USER` env var is not set. Useful for shared configs where the username is the same for all users. |
| `ssl_verify` | No | `true` | Set `false` for self-signed certificates or on-prem instances with custom CAs. |

## Config resolution order

1. Walk up from CWD looking for `.jenkins.json` (project-level)
2. Check `~/.jenkins.json` (global defaults)
3. If both exist, deep-merge them (project-level wins)
4. If neither exists, error with copy-pastable JSON template

## Global + per-project split (recommended)

Put shared settings in `~/.jenkins.json`:
```json
{
  "base_url": "https://your-jenkins-instance.example.com",
  "credentials": {
    "username_env": "JENKINS_USER",
    "token_env": "JENKINS_TOKEN"
  }
}
```

Then each project only needs optional overrides in `.jenkins.json`:
```json
{
  "job_cache": {
    "my-service": "API/my-service"
  },
  "default_branch": "develop"
}
```

## Credential resolution order

1. If `env_file` is set, load variables from that file first
2. Then check OS environment variables
3. The variable names are taken from `credentials.username_env` and `credentials.token_env`

**Recommended**: export credentials globally in your shell profile rather than using per-project `.env` files:
- **zsh**: `echo 'export JENKINS_TOKEN="<value>"' >> ~/.zshrc && source ~/.zshrc`
- **bash**: `echo 'export JENKINS_TOKEN="<value>"' >> ~/.bashrc && source ~/.bashrc`
- **fish**: `set -Ux JENKINS_TOKEN '<value>'`

## API token setup

Create a Jenkins API token at **Jenkins > Your Name (top-right) > Configure > API Token > Add new Token**.

The token is used with your Jenkins username for Basic authentication. The username is typically your email or login ID — the same one you use to sign in to Jenkins.

## Job cache

The `job_cache` maps repository names to their Jenkins folder/job paths. This avoids an API search across all folders every time you check a build.

**How to populate**: Run `jenkins_preflight.py` — if a matching job is found, it will print the `job_cache` entry to add.

**Format**: `"repo-name": "folder/job-name"`. For top-level jobs (not in a folder), use `"repo-name": "repo-name"`.

## SSL verification

For on-premises Jenkins instances with self-signed certificates:
1. Set `"ssl_verify": false` in config (quick fix)
2. Or set the `SSL_CERT_FILE` environment variable to your CA bundle path (recommended)
