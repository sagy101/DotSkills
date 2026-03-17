---
name: eks-pod-ops
description: >
  Read pod logs, list pods, execute commands in pods, and restart deployments on EKS clusters.
  Use when the user asks to check logs, debug a pod, exec into a container, find pods, restart
  a service, or interact with Kubernetes/EKS in any way.
metadata:
  author: sashlag
  version: "1.1"
---

# EKS Pod Operations

Read logs, find pods, exec into containers, and restart deployments across EKS environments.

## When to use this skill

Use this skill when the user wants to:
- View logs from a pod or service
- List or find pods in an EKS environment
- Execute a command inside a running pod
- Restart (rollout restart) a deployment
- Debug a pod (describe, check status, view previous logs)
- Check if a service is running in a specific environment

## Prerequisites

1. **kubectl**: installed and available in PATH
2. **AWS CLI**: installed with SSO profiles configured per environment
3. **Kubeconfigs**: generated per environment at `~/.kube/config_<env>`
4. **Config**: `~/.eks-config.json` — auto-generated on first run by scanning kubeconfigs and AWS profiles. See [CONFIG.md](references/CONFIG.md) for manual setup.

## Pre-flight checks

Run the pre-flight script before the first operation in a conversation:

```bash
python3 <skill_dir>/scripts/preflight.py
```

To also verify a specific environment (kubeconfig + SSO):

```bash
python3 <skill_dir>/scripts/preflight.py --env stg
```

If SSO is expired, tell the user: `aws sso login --sso-session <session>` (session name is in the preflight output).

## Operations

### pods — List or describe pods

```bash
# Find pods for a service
python3 <skill_dir>/scripts/eks_ops.py pods --env stg --service my-service

# List all pods in environment
python3 <skill_dir>/scripts/eks_ops.py pods --env stg --all

# Describe a pod (events, conditions, mounts)
python3 <skill_dir>/scripts/eks_ops.py pods --env stg --service my-service --describe
```

### logs — Read pod logs

```bash
# Last 100 lines (default)
python3 <skill_dir>/scripts/eks_ops.py logs --env stg --service my-service

# Custom tail size and time window
python3 <skill_dir>/scripts/eks_ops.py logs --env stg --service my-service --tail 500 --since 1h

# Previous container (after crash/restart)
python3 <skill_dir>/scripts/eks_ops.py logs --env stg --service my-service --previous

# All replicas at once (uses stern if installed)
python3 <skill_dir>/scripts/eks_ops.py logs --env stg --service my-service --all-pods

# Stream logs in real-time
python3 <skill_dir>/scripts/eks_ops.py logs --env stg --service my-service --follow

# Specific pod by name (skip service resolution)
python3 <skill_dir>/scripts/eks_ops.py logs --env stg --pod my-service-abc123-xyz --tail 200
```

### exec — Run a command inside a pod

**Show the exact command to the user and get approval before running.**

```bash
python3 <skill_dir>/scripts/eks_ops.py exec --env dev --service my-service -- ls /app/conf
python3 <skill_dir>/scripts/eks_ops.py exec --env dev --service my-service -- cat /app/conf/application.conf
python3 <skill_dir>/scripts/eks_ops.py exec --env stg --service my-service -- env | grep -i heap
python3 <skill_dir>/scripts/eks_ops.py exec --env stg --service my-service -- df -h
```

### restart — Rollout restart a deployment

**Show the restart command to the user and get approval before running.**

```bash
python3 <skill_dir>/scripts/eks_ops.py restart --env dev --service my-service
python3 <skill_dir>/scripts/eks_ops.py restart --env dev --service my-service --watch
```

## Important rules

1. **`exec` and `restart` require explicit user approval.** Show the exact command and wait for confirmation.
2. **`pods` and `logs` are read-only.** Run them directly without approval.
3. All output is automatically redacted — secrets, tokens, keys, and credentials are replaced with `[REDACTED]`. See [references/REDACTION.md](references/REDACTION.md).
4. Bare `env`, `printenv`, or `set` commands are blocked inside `exec`. Use `env | grep -i <keyword>` instead.
5. Reading files under `/secrets/`, `/vault/`, or credential paths is blocked inside `exec`.
6. If `[REDACTED]` appears in output, do not attempt to retrieve the original value.
7. The script auto-selects the app container in multi-container pods (skips sidecars like statsite, istio-proxy).
8. **Multiple replicas**: when a service has multiple pods, `--service` picks the first running one. If the user wants a specific replica, run `pods --env <env> --service <name>` first to list all replicas, ask the user which one, then use `--pod <pod-name>` instead of `--service`.
9. Prefer Grafana or Splunk for production log investigation — use this skill as a complement.
10. Developers typically have read-only EKS access — `restart` may fail on production clusters.

## Error handling

| Error | Cause | Fix |
|---|---|---|
| `SSO session may be expired` | AWS SSO token expired | `aws sso login --sso-session <session>` |
| `Kubeconfig not found` | Missing kubeconfig file | `aws eks update-kubeconfig --profile <env> --name <cluster> --kubeconfig ~/.kube/config_<env>` |
| `No pods found for service` | Wrong service name or no pods running | `pods --env <env> --all` to see available pods |
| `Blocked: Dumps all environment variables` | Exec blocklist triggered | Use `env \| grep -i <keyword>` instead |
| `connection refused localhost:8080` | Rancher Desktop kubectl conflict | Script auto-detects this. If persists, check `which kubectl` |

## Troubleshooting

| Problem | Fix |
|---|---|
| `kubectl: command not found` | `brew install kubectl` |
| `aws: command not found` | `brew install awscli` |
| Config not found | Create `~/.eks-config.json` — see Prerequisites |
| Wrong namespace | Set `namespace` in environment config |
| Logs empty | Try `--previous` for crashed containers, or increase `--since` |
| `stern` not found | `brew install stern` (optional — falls back to sequential kubectl) |
