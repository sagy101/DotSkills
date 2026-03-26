# Configuration Reference

The `.jenkins.json` file configures the jenkins-manager skill with named Jenkins instances. It can live in:
- **Project root** — project-specific settings (e.g. `job_cache`, `default_branch`)
- **Home directory** (`~/.jenkins.json`) — global defaults (e.g. instances, credentials)

If both exist, they are **deep-merged** (project-level wins on conflicts).

## Full schema

```json
{
  "instances": {
    "ci": {
      "base_url": "https://jenkins-ci.us1.example.com",
      "description": "CI builds for all services",
      "credentials": {
        "username_env": "JENKINS_USER",
        "token_env": "JENKINS_TOKEN"
      },
      "job_cache": {
        "my-repo": "API/my-repo"
      },
      "default_branch": "master",
      "ssl_verify": true
    },
    "cd-stg": {
      "base_url": "https://jenkins-cd.stg.example.com",
      "description": "CD deployments to staging",
      "credentials": {
        "username_env": "JENKINS_USER",
        "token_env": "JENKINS_CD_TOKEN"
      }
    }
  },
  "default_instance": "ci",
  "env_file": "/absolute/path/to/.env"
}
```

## Top-level fields

| Field | Required | Default | Description |
|---|---|---|---|
| `instances` | Yes | — | Map of named Jenkins instances (see below) |
| `default_instance` | No | Auto (if only 1) | Name of the default instance to use when `--instance` is not provided |
| `env_file` | No | `null` | Shared `.env` file path for all instances (can be overridden per-instance) |

## Instance fields

Each instance under `instances` supports:

| Field | Required | Default | Description |
|---|---|---|---|
| `base_url` | Yes | — | Jenkins server URL (no trailing slash) |
| `description` | No | `""` | Human-readable description (shown in preflight, error messages, and agent context) |
| `credentials.username_env` | No | `"JENKINS_USER"` | Env var name for Jenkins username |
| `credentials.token_env` | No | `"JENKINS_TOKEN"` | Env var name for Jenkins API token |
| `env_file` | No | Top-level `env_file` | Optional `.env` file path. Overrides top-level `env_file` for this instance. |
| `job_cache` | No | `{}` | Map of repo name to `folder/job` path for fast lookups |
| `default_branch` | No | `null` | Default branch when not in a git repo |
| `default_username` | No | `null` | Fallback username when env var is not set |
| `ssl_verify` | No | `true` | Set `false` for self-signed certificates |

## Instance selection priority

1. `--instance` CLI flag
2. `JENKINS_INSTANCE` environment variable
3. `default_instance` from config
4. If only one instance exists, it is used automatically
5. If multiple instances and no default, error with available list

## Config resolution order

1. Walk up from CWD looking for `.jenkins.json` (project-level)
2. Check `~/.jenkins.json` (global defaults)
3. If both exist, deep-merge them (project-level wins, per-instance)
4. If neither exists, error with copy-pastable JSON template

## Global + per-project split (recommended)

Put shared settings in `~/.jenkins.json`:
```json
{
  "instances": {
    "ci": {
      "base_url": "https://jenkins-ci.us1.example.com",
      "description": "CI builds",
      "credentials": {
        "username_env": "JENKINS_USER",
        "token_env": "JENKINS_TOKEN"
      }
    },
    "cd-stg": {
      "base_url": "https://jenkins-cd.stg.example.com",
      "description": "STG deployments",
      "credentials": {
        "username_env": "JENKINS_USER",
        "token_env": "JENKINS_CD_TOKEN"
      }
    }
  },
  "default_instance": "ci",
  "env_file": "/path/to/.env"
}
```

Then each project only needs optional overrides in `.jenkins.json`:
```json
{
  "instances": {
    "ci": {
      "job_cache": {
        "my-service": "API/my-service"
      },
      "default_branch": "develop"
    }
  }
}
```

## Credential resolution order

1. If `env_file` is set (instance-level or top-level), load variables from that file first
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
1. Set `"ssl_verify": false` in the instance config (quick fix)
2. Or set the `SSL_CERT_FILE` environment variable to your CA bundle path (recommended)
