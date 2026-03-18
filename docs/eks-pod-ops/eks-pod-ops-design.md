# eks-pod-ops

A kubectl wrapper skill for AI agents that provides safe, redacted access to EKS pods.

## Why This Exists

AI agents need to read pod logs and debug Kubernetes issues, but raw kubectl output often contains secrets (tokens in logs, env vars via exec, connection strings in stack traces). This skill wraps kubectl with:

1. **Automatic secret redaction** — regex-based pattern matching strips tokens, keys, passwords, JWTs, and high-entropy strings before output reaches the agent's context
2. **Exec safety** — dangerous commands (`env`, `printenv`, `cat /secrets/...`) are blocked before execution
3. **Service-name resolution** — agents say "my-service" not "my-service-7b6bbbbb78-4wtsx"; the script resolves pods via label selectors
4. **Sidecar awareness** — auto-selects the app container, skipping sidecars (statsite, istio-proxy, envoy, etc.)
5. **Rancher Desktop compatibility** — detects and works around the Rancher Desktop kubectl proxy issue

## Architecture

```
User/Agent
    │
    ▼
eks_ops.py ─────── Interface: argparse + subcommand dispatch
    │
    ├── lib/config.py ──── Config discovery (~/.eks-config.json or project-level)
    │                       Environment resolution, kubeconfig path building
    │
    ├── lib/kubectl.py ─── kubectl binary discovery (Rancher Desktop workaround)
    │                       Execution with --kubeconfig flag, SSO error detection
    │
    ├── lib/redaction.py ── Regex pattern pipeline (Bearer, passwords, AWS keys, JWTs, etc.)
    │                        Exec blocklist (bare env, secret file reads)
    │                        Optional detect-secrets entropy detection
    │
    └── lib/pods.py ─────── Pod resolution (label selector → name prefix fallback)
                             Container selection (skip known sidecars)

eks_preflight.py ──── Standalone pre-flight checks (one command, all checks)
```

### Design Decisions

**`--kubeconfig=` flag instead of `KUBECONFIG` env var:**
When Rancher Desktop is installed, `~/.kube/config` contains a `rancher-desktop` context set as `current-context`. kubectl merges the env var config with the default config, and the Rancher context wins — routing all requests to localhost:8080. The `--kubeconfig=<absolute_path>` flag bypasses this.

**Regex for redaction instead of detect-secrets:**
`detect-secrets` (Yelp) is designed for scanning source code, not streaming log output. For log redaction, regex patterns are the industry standard (AWS CloudWatch, GCP DLP, etc.). The regex approach is zero-dependency, predictable, and fast. If `detect-secrets` is installed, it adds entropy-based detection as an extra layer.

**Exec blocklist:**
A bare `env` dumps every environment variable including injected secrets from Kubernetes Secrets, Vault, and AWS credential chains. Even with redaction, novel secret formats could slip through. Blocking at the source is safer. `env | grep -i KEYWORD` is just as useful.

**Global config by default:**
EKS clusters don't change per project — the same dev/stg/us1/eu2 environments exist regardless of which repo you're in. `~/.eks-config.json` is the primary location; project-level `.eks-config.json` exists only as an override.

## File Structure

```
eks-pod-ops/
├── SKILL.md                 # Agent-facing: how to use
├── README.md                # Human-facing: architecture, design decisions
├── scripts/
│   ├── eks_ops.py           # Main entry point (4 subcommands)
│   ├── eks_preflight.py         # Pre-flight checks (standalone)
│   └── lib/
│       ├── __init__.py
│       ├── config.py        # Config loading, env resolution
│       ├── kubectl.py       # kubectl discovery, execution
│       ├── redaction.py     # Secret redaction, exec blocklist
│       └── pods.py          # Pod resolution, container selection
└── references/
    ├── CONFIG.md            # Full config schema
    └── REDACTION.md         # Redaction patterns, exec blocklist
```

## Requirements

- Python 3.10+ (stdlib only, no pip install needed)
- kubectl
- AWS CLI with SSO profiles configured
- Kubeconfig files per environment (`~/.kube/config_<env>`)
- Optional: `stern` for multi-pod log tailing
- Optional: `detect-secrets` (`pip install detect-secrets`) for entropy-based redaction

## Recommended Extras

These are optional but improve the experience. Install once per machine.

**stern** — multi-pod log tailing. Without it, `--all-pods` falls back to sequential `kubectl logs` per pod. With it, you get parallel color-coded streaming across all replicas.

```bash
brew install stern
```

**detect-secrets** — Yelp's entropy-based secret detector. The skill already redacts known patterns (Bearer tokens, passwords, AWS keys, JWTs, etc.) via regex. Adding detect-secrets catches high-entropy strings that don't match any specific pattern — an extra safety net for novel secret formats leaking into agent context.

```bash
pip install detect-secrets
```

The preflight script shows whether each is installed:
```
  [OK] stern (optional) — /opt/homebrew/bin/stern
  [OK] detect-secrets (optional) — Entropy-based redaction enabled
```

## Setup

1. Ensure kubeconfigs exist per environment (`~/.kube/config_<env>`) and AWS CLI profiles are configured in `~/.aws/config`
2. Run preflight: `python3 scripts/eks_preflight.py` — it auto-discovers environments and generates `~/.eks-config.json`
3. Log in to AWS SSO: `aws sso login --sso-session <session>` (session name shown in preflight output)
4. Verify a specific env: `python3 scripts/eks_preflight.py --env stg`

## Quick Test

```bash
python3 scripts/eks_preflight.py --env stg
python3 scripts/eks_ops.py pods --env stg --service my-service
python3 scripts/eks_ops.py logs --env stg --service my-service --tail 10
```
