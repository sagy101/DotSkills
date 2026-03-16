# Configuration Reference

The script loads config from `.eks-config.json` (project root, searched upward) or `~/.eks-config.json` (global fallback).

## Full Schema

```json
{
  "environments": {
    "<env_name>": {
      "profile": "<aws_profile_name>",
      "cluster": "<eks_cluster_name>",
      "sso_session": "<aws_sso_session_name>",
      "namespace": "<kubernetes_namespace>",
      "alias": "<optional_alias>"
    }
  },
  "kubeconfig_dir": "~/.kube",
  "kubeconfig_pattern": "config_{env}",
  "redaction": {
    "extra_patterns": ["<regex_pattern>"],
    "skip_entropy": false,
    "disabled": false
  }
}
```

## Field Reference

### environments (required)

Map of environment name → environment config. The environment name is used in `--env` flags.

| Field | Required | Default | Description |
|---|---|---|---|
| `profile` | Yes | — | AWS CLI profile name for this environment |
| `cluster` | Yes | — | EKS cluster name (e.g., `eks01-dev`) |
| `sso_session` | Yes | — | AWS SSO session name (e.g., `lab`, `prod`) |
| `namespace` | No | `default` | Kubernetes namespace for pod operations |
| `alias` | No | — | Alternative name (e.g., `staging` → `stg`) |

### kubeconfig_dir (optional)

Directory containing kubeconfig files. Default: `~/.kube`.

### kubeconfig_pattern (optional)

Filename pattern for kubeconfig files. `{env}` is replaced with the environment name. Default: `config_{env}`.

Example: `config_{env}` → `~/.kube/config_stg`

### redaction (optional)

| Field | Default | Description |
|---|---|---|
| `extra_patterns` | `[]` | Additional regex patterns to redact (matched text replaced with `[REDACTED]`) |
| `skip_entropy` | `false` | Skip entropy-based detection even if detect-secrets is installed |
| `disabled` | `false` | Disable all redaction (for debugging only — do not use in normal operation) |

## Example Configs

### Multi-environment (lab + prod SSO sessions)

```json
{
  "environments": {
    "dev": { "profile": "dev", "cluster": "eks01-dev", "sso_session": "lab",  "namespace": "default" },
    "stg": { "profile": "stg", "cluster": "eks01-stg", "sso_session": "lab",  "namespace": "default" },
    "us1": { "profile": "us1", "cluster": "eks01-us1", "sso_session": "prod", "namespace": "default" },
    "eu2": { "profile": "eu2", "cluster": "eks01-eu2", "sso_session": "prod", "namespace": "default" }
  }
}
```

### Minimal (single environment)

```json
{
  "environments": {
    "dev": { "profile": "dev", "cluster": "my-cluster", "sso_session": "default", "namespace": "my-app" }
  }
}
```
