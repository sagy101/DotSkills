#!/usr/bin/env python3
"""Pre-flight checks for eks-pod-ops. Run before first operation in a conversation."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Allow imports from sibling lib/
sys.path.insert(0, str(Path(__file__).parent))

from lib.config import find_config, load_config, get_env_config, get_kubeconfig_path


def check(label: str, ok: bool, detail: str = ""):
    status = "OK" if ok else "FAIL"
    msg = f"  [{status}] {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    return ok


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Pre-flight checks for EKS pod operations.")
    parser.add_argument("--env", help="Also check kubeconfig and SSO for this environment.")
    args = parser.parse_args()

    print("EKS Pod Ops — Pre-flight Checks\n")
    all_ok = True

    # 1. Python version
    v = sys.version_info
    all_ok &= check("Python 3.10+", v >= (3, 10), f"{v.major}.{v.minor}.{v.micro}")

    # 2. kubectl
    kubectl = shutil.which("kubectl")
    rancher_issue = False
    if kubectl:
        real = os.path.realpath(kubectl)
        rancher_issue = real.startswith(("/Applications/Rancher", os.path.expanduser("~/.rd")))
        homebrew = "/opt/homebrew/bin/kubectl"
        if rancher_issue and os.path.isfile(homebrew):
            all_ok &= check("kubectl", True, f"Rancher Desktop detected, will use {homebrew}")
        elif rancher_issue:
            all_ok &= check("kubectl", False, "Rancher Desktop kubectl found but no homebrew fallback. Run: brew install kubectl")
        else:
            all_ok &= check("kubectl", True, kubectl)
    else:
        all_ok &= check("kubectl", False, "Not found. Run: brew install kubectl")

    # 3. AWS CLI
    aws = shutil.which("aws")
    all_ok &= check("AWS CLI", bool(aws), aws or "Not found. Run: brew install awscli")

    # 4. Config file
    config_path = find_config()
    if config_path:
        all_ok &= check("Config", True, str(config_path))
        config = load_config(config_path)
        envs = sorted(config.get("environments", {}).keys())
        print(f"         Environments: {', '.join(envs)}")
    else:
        all_ok &= check("Config", False, "Create ~/.eks-config.json or .eks-config.json in project root")
        config = None

    # 5. Optional: stern
    stern = shutil.which("stern")
    check("stern (optional)", bool(stern), stern or "Not installed. Run: brew install stern (for --all-pods)")

    # 6. Optional: detect-secrets
    try:
        import detect_secrets
        check("detect-secrets (optional)", True, "Entropy-based redaction enabled")
    except ImportError:
        check("detect-secrets (optional)", True, "Not installed — regex redaction only (fine for most cases)")

    # 7. Environment-specific checks
    if args.env and config:
        print(f"\nEnvironment: {args.env}")
        try:
            env_cfg = get_env_config(config, args.env)
        except SystemExit:
            all_ok &= check(f"Environment '{args.env}'", False, "Not in config")
            sys.exit(1 if not all_ok else 0)

        # Kubeconfig
        kc_path = get_kubeconfig_path(config, args.env)
        kc_exists = os.path.isfile(kc_path)
        if kc_exists:
            all_ok &= check("Kubeconfig", True, kc_path)
        else:
            profile = env_cfg.get("profile", args.env)
            cluster = env_cfg.get("cluster", f"eks01-{args.env}")
            all_ok &= check("Kubeconfig", False,
                f"Not found: {kc_path}\n"
                f"           Run: aws eks update-kubeconfig --profile {profile} --name {cluster} --kubeconfig {kc_path}")

        # SSO session
        if aws:
            profile = env_cfg.get("profile", args.env)
            try:
                result = subprocess.run(
                    ["aws", "sts", "get-caller-identity", "--profile", profile],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    all_ok &= check("SSO session", True, f"Profile '{profile}' authenticated")
                else:
                    sso_session = env_cfg.get("sso_session", "lab")
                    all_ok &= check("SSO session", False,
                        f"Expired. Run: aws sso login --sso-session {sso_session}")
            except subprocess.TimeoutExpired:
                all_ok &= check("SSO session", False, "Timed out checking credentials")

    print(f"\n{'All checks passed.' if all_ok else 'Some checks failed — see above.'}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
