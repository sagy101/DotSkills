#!/usr/bin/env python3
"""EKS Pod Operations — kubectl wrapper with secret redaction and exec safety."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Allow imports from sibling lib/
sys.path.insert(0, str(Path(__file__).parent))

from lib.config import require_config, get_env_config, get_kubeconfig_path, die
from lib.kubectl import run_kubectl, stream_kubectl
from lib.redaction import redact_text, check_exec_allowed
from lib.pods import resolve_pods, resolve_single_pod, pick_app_container, print_pod_table

# ─── Subcommands ──────────────────────────────────────────────────────────────


def cmd_pods(args, config):
    if args.service:
        pods = resolve_pods(config, args.env, args.service)
        if not pods:
            die(f"No pods found for service '{args.service}' in {args.env}.")
        if args.describe:
            rc, output = run_kubectl(config, args.env, ["describe", "pod", pods[0]["name"]])
            print(output)
            return rc
        print_pod_table(pods, args.env)
    elif args.all:
        rc, output = run_kubectl(config, args.env, ["get", "pods", "-o", "wide"])
        print(output)
        return rc
    else:
        die("Specify --service <name> or --all.")
    return 0


def cmd_logs(args, config):
    kubectl_args = ["logs"]

    if args.pod:
        kubectl_args.append(args.pod)
    elif args.service:
        if args.all_pods:
            return _logs_all_pods(args, config)
        pod_name, container = resolve_single_pod(config, args.env, args.service)
        kubectl_args += [pod_name, "-c", container]
    else:
        die("Specify --service <name> or --pod <pod-name>.")

    if args.tail:
        kubectl_args += ["--tail", str(args.tail)]
    if args.since:
        kubectl_args += ["--since", args.since]
    if args.previous:
        kubectl_args.append("--previous")
    if args.follow:
        return stream_kubectl(config, args.env, kubectl_args)

    rc, output = run_kubectl(config, args.env, kubectl_args)
    print(output)
    return rc


def _logs_all_pods(args, config):
    stern = shutil.which("stern")
    env_cfg = get_env_config(config, args.env)
    kubeconfig = get_kubeconfig_path(config, args.env)
    namespace = env_cfg.get("namespace", "default")

    if stern:
        cmd = [stern, "-l", f"app={args.service}", "-n", namespace, f"--kubeconfig={kubeconfig}"]
        if args.since:
            cmd += ["--since", args.since]
        if args.tail:
            cmd += ["--tail", str(args.tail)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            print(redact_text(result.stdout + result.stderr, config))
            return result.returncode
        except subprocess.TimeoutExpired as e:
            output = (e.stdout or "") + (e.stderr or "")
            if output:
                print(redact_text(output, config))
            print("[stern timed out after 30s — partial output above]")
            return 0

    # Fallback: sequential kubectl logs per pod
    pods = resolve_pods(config, args.env, args.service)
    if not pods:
        die(f"No pods found for service '{args.service}' in {args.env}.")
    for pod in pods:
        container = pick_app_container(pod["containers"], args.service)
        kubectl_args = ["logs", pod["name"], "-c", container]
        if args.tail:
            kubectl_args += ["--tail", str(args.tail)]
        if args.since:
            kubectl_args += ["--since", args.since]
        print(f"── {pod['name']} ──")
        rc, output = run_kubectl(config, args.env, kubectl_args)
        print(output)
    return 0


def cmd_exec(args, config):
    if not args.command:
        die("No command specified. Usage: eks_ops.py exec --env <env> --service <name> -- <command>")

    cmd_str = " ".join(args.command)
    blocked = check_exec_allowed(cmd_str)
    if blocked:
        die(blocked)

    if args.pod:
        pod_name, container = args.pod, None
    else:
        if not args.service:
            die("Specify --service <name> or --pod <pod-name>.")
        pod_name, container = resolve_single_pod(config, args.env, args.service)

    kubectl_args = ["exec", pod_name]
    if container:
        kubectl_args += ["-c", container]
    kubectl_args += ["--"] + args.command

    rc, output = run_kubectl(config, args.env, kubectl_args)
    print(output)
    return rc


def cmd_restart(args, config):
    if not args.service:
        die("Specify --service <name> to restart.")

    rc, output = run_kubectl(config, args.env, ["rollout", "restart", f"deployment/{args.service}"])
    print(output)
    if rc != 0:
        return rc

    if args.watch:
        print("Watching rollout status...")
        rc, output = run_kubectl(config, args.env, ["rollout", "status", f"deployment/{args.service}", "--timeout=120s"])
        print(output)
    return rc


# ─── Argument Parsing ─────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="EKS Pod Operations — kubectl wrapper with secret redaction.",
    )
    sub = parser.add_subparsers(dest="action", required=True)

    p = sub.add_parser("pods", help="List or describe pods")
    p.add_argument("--env", required=True)
    p.add_argument("--service", help="Service/app name")
    p.add_argument("--all", action="store_true", help="List all pods")
    p.add_argument("--describe", action="store_true", help="Full pod description")

    p = sub.add_parser("logs", help="Get pod logs")
    p.add_argument("--env", required=True)
    p.add_argument("--service", help="Service/app name (auto-resolves pod)")
    p.add_argument("--pod", help="Specific pod name")
    p.add_argument("--tail", type=int, default=100, help="Lines to show (default: 100)")
    p.add_argument("--since", help="Time window: 1h, 30m, 2h30m")
    p.add_argument("--previous", action="store_true", help="Previous container instance")
    p.add_argument("--follow", action="store_true", help="Stream in real-time")
    p.add_argument("--all-pods", action="store_true", help="All replicas (uses stern if available)")

    p = sub.add_parser("exec", help="Execute command in a pod")
    p.add_argument("--env", required=True)
    p.add_argument("--service", help="Service/app name")
    p.add_argument("--pod", help="Specific pod name")
    p.add_argument("command", nargs=argparse.REMAINDER, help="Command (after --)")

    p = sub.add_parser("restart", help="Rollout restart a deployment")
    p.add_argument("--env", required=True)
    p.add_argument("--service", required=True)
    p.add_argument("--watch", action="store_true", help="Watch rollout progress")

    args = parser.parse_args()

    if args.action == "exec" and args.command and args.command[0] == "--":
        args.command = args.command[1:]

    _, config = require_config()

    handlers = {"pods": cmd_pods, "logs": cmd_logs, "exec": cmd_exec, "restart": cmd_restart}
    sys.exit(handlers[args.action](args, config) or 0)


if __name__ == "__main__":
    main()
