# Error Handling & Troubleshooting

**Read this file when a delegation fails or returns unexpected results.**

## Exit Code Reference

| Exit Code | Contains | Action |
|---|---|---|
| 0 + output exists | — | Success: read output file |
| 0 + output empty/missing | — | Anomaly: retry once, then report |
| 1 | "rate limit" | Exponential backoff: 30s then 60s, max 2 retries |
| 1 | "auth" / "login" | Offer to run `codex login` |
| 1 | "model" / "unavailable" | Retry with fallback model |
| 1 | other | Read output for partial result; report error |
| 2 | wrapper rejection | Check stderr for "BLOCKED" or "ERROR" with usage guidance |
| 101 | Rust panic | Do NOT retry; report to user |
| 124 | timeout | Re-launch with next timeout tier |
| 127 | — | `codex` not installed — offer to install |
| 137 | OOM/SIGKILL | Resource exhaustion — retry simpler or report |
| 143 | SIGTERM | Check output for partial result |

## Retry Strategy

- Max 2 retries per delegation
- On timeout with `--persist`: resume with next tier. Without persist: fresh run with next tier.
- On rate limit: exponential backoff (30s, 60s)
- On unknown error: don't retry, report to user

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `codex: command not found` | CLI not installed | `npm i -g @openai/codex` |
| Version too old | Below v0.106.0 | `npm i -g @openai/codex` |
| `401` / auth error | Not logged in | `codex login` |
| Wrapper rejects flag | Raw codex flag used | Use wrapper flags instead (see Wrapper flags table in SKILL.md) |
| Timeout | Task too complex for tier | Re-run with next timeout tier |
| Empty output file | Codex failed silently | Check exit code and stderr; retry once |
| Git worktree failure | Uncommitted changes or locks | Commit/stash changes, then retry |
| Rate limit | API quota exceeded | Wait 30-60s, retry max 2 times |
