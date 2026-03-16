# Redaction Reference

All output from `logs` and `exec` passes through a redaction pipeline before being displayed. Redacted values are replaced with `[REDACTED]` markers so it's clear content was removed.

## Built-in Patterns

These patterns are always active (unless `redaction.disabled` is set in config):

| Category | Pattern | Replacement |
|---|---|---|
| Bearer tokens | `Bearer <token>` | `Bearer [REDACTED]` |
| Authorization headers | `Authorization: <value>` | `Authorization: [REDACTED]` |
| Key-value secrets | `password=xxx`, `token: xxx`, `api_key=xxx`, `secret=xxx`, `client_secret=xxx`, `auth_token=xxx` | `password=[REDACTED]` |
| AWS secret key | `AWS_SECRET_ACCESS_KEY=xxx` | `AWS_SECRET_ACCESS_KEY=[REDACTED]` |
| AWS session token | `AWS_SESSION_TOKEN=xxx` | `AWS_SESSION_TOKEN=[REDACTED]` |
| AWS access key IDs | `AKIA...`, `ASIA...` (16+ chars) | `[REDACTED AWS KEY]` |
| Private keys | `-----BEGIN PRIVATE KEY-----...` | `[REDACTED PRIVATE KEY]` |  <!-- pragma: allowlist secret -->
| JWT tokens | `eyJ...eyJ...` (3-segment base64) | `[REDACTED JWT]` |
| Connection strings | `postgres://user:pass@host` | `postgres://user:[REDACTED]@host` |  <!-- pragma: allowlist secret -->
| Base64 blobs | 80+ character base64 strings | `[REDACTED BASE64]` |

## Custom Patterns

Add project-specific patterns in `.eks-config.json`:

```json
{
  "redaction": {
    "extra_patterns": [
      "COUCHBASE_PASSWORD=\\S+",
      "VAULT_TOKEN=\\S+"
    ]
  }
}
```

Each pattern is a Python regex. Matched text is replaced with `[REDACTED]`.

## Entropy-Based Detection (Optional)

If `detect-secrets` is installed (`pip install detect-secrets`), the script adds entropy-based detection on top of regex patterns. This catches high-entropy strings that look like secrets but don't match any specific pattern.

To disable entropy detection: set `"skip_entropy": true` in the redaction config.

## Exec Blocklist

These commands are blocked entirely inside `exec` (checked before execution):

| Blocked Command | Reason | Alternative |
|---|---|---|
| `env` (bare) | Dumps all env vars including secrets | `env \| grep -i <keyword>` |
| `printenv` (bare) | Same as env | `echo $SPECIFIC_VAR` |
| `set` (bare) | Dumps shell variables | Target specific variables |
| `cat /secrets/...` | Reads secret files | Describe what info you need |
| `cat /vault/...` | Reads vault secret files | Describe what info you need |
| `cat *.key`, `cat *.pem` | Reads key/cert files | Describe what info you need |
| `cat /proc/*/environ` | Dumps process environment | `echo $SPECIFIC_VAR` |
| `strings /proc/...` | May expose process memory | Use specific diagnostics |
