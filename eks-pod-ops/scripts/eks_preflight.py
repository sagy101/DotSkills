#!/usr/bin/env python3
"""Pre-flight checks for eks-pod-ops. Run before first operation in a conversation."""

import configparser
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Allow imports from sibling lib/
sys.path.insert(0, str(Path(__file__).parent))

from lib.config import find_config, get_env_config, get_kubeconfig_path, load_config


def check(label: str, ok: bool, detail: str = "") -> bool:
    status = "OK" if ok else "FAIL"
    msg = f"  [{status}] {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    return ok


# ─── Auto-Discovery ──────────────────────────────────────────────────────────


def discover_environments() -> dict[str, dict[str, str]]:
    """Scan ~/.kube/config_* and ~/.aws/config to build environment map."""
    kube_dir = Path.home() / ".kube"
    aws_profiles = _parse_aws_profiles()
    environments: dict[str, dict[str, str]] = {}

    for kc_path in sorted(kube_dir.glob("config_*")):
        env_name = kc_path.name.removeprefix("config_")
        if not env_name or env_name.startswith("."):
            continue

        cluster = _extract_cluster_name(kc_path)
        namespace = _extract_namespace(kc_path)
        profile_info = aws_profiles.get(env_name, {})

        environments[env_name] = {
            "profile": profile_info.get("profile", env_name),
            "cluster": cluster or f"eks01-{env_name}",
            "sso_session": profile_info.get("sso_session", "default"),
            "namespace": namespace or "default",
        }

    return environments


def _extract_cluster_name(kc_path: Path) -> str:
    """Extract EKS cluster name from kubeconfig file."""
    try:
        with open(kc_path) as f:
            for line in f:
                # Match cluster ARN or name like eks01-dev
                match = re.search(r"cluster/([^\s\"']+)", line)
                if match:
                    return match.group(1)
    except OSError:
        pass
    return ""


def _extract_namespace(kc_path: Path) -> str:
    """Extract default namespace from kubeconfig if set."""
    try:
        with open(kc_path) as f:
            content = f.read()
            match = re.search(r"namespace:\s*(\S+)", content)
            if match:
                return match.group(1)
    except OSError:
        pass
    return ""


def _parse_aws_profiles() -> dict[str, dict[str, str]]:
    """Parse ~/.aws/config to map profile names to SSO sessions."""
    aws_config = Path.home() / ".aws" / "config"
    if not aws_config.is_file():
        return {}

    parser = configparser.ConfigParser()
    parser.read(aws_config)

    profiles: dict[str, dict[str, str]] = {}
    for section in parser.sections():
        if section.startswith("profile "):
            name = section.removeprefix("profile ")
            profiles[name] = {
                "profile": name,
                "sso_session": parser.get(section, "sso_session", fallback="default"),
            }
    return profiles


def auto_generate_config(output_path: Path, environments: dict[str, dict[str, str]]) -> None:
    """Write discovered environments to config file."""
    config = {"environments": environments}
    with open(output_path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def _list_sso_sessions() -> list[str]:
    """List SSO session names from ~/.aws/config."""
    aws_config = Path.home() / ".aws" / "config"
    if not aws_config.is_file():
        return []
    parser = configparser.ConfigParser()
    parser.read(aws_config)
    sessions = [
        section.removeprefix("sso-session ")
        for section in parser.sections()
        if section.startswith("sso-session ")
    ]
    return sorted(set(sessions))


def check_environment(config: dict, env_name: str, *, has_aws: bool) -> bool:
    """Check kubeconfig and SSO session for a specific environment."""
    all_ok = True
    print(f"\nEnvironment: {env_name}")
    try:
        env_cfg = get_env_config(config, env_name)
    except SystemExit:
        return check(f"Environment '{env_name}'", False, "Not in config")

    kc_path = get_kubeconfig_path(config, env_name)
    if os.path.isfile(kc_path):
        all_ok &= check("Kubeconfig", True, kc_path)
    else:
        profile = env_cfg.get("profile", env_name)
        cluster = env_cfg.get("cluster", f"eks01-{env_name}")
        all_ok &= check(
            "Kubeconfig",
            False,
            f"Not found: {kc_path}\n"
            f"           Run: aws eks update-kubeconfig --profile {profile} "
            f"--name {cluster} --kubeconfig {kc_path}",
        )

    if has_aws:
        profile = env_cfg.get("profile", env_name)
        try:
            result = subprocess.run(
                ["aws", "sts", "get-caller-identity", "--profile", profile],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                all_ok &= check("SSO session", True, f"Profile '{profile}' authenticated")
            else:
                sso_session = env_cfg.get("sso_session", "")
                if sso_session:
                    hint = f"Expired. Run: aws sso login --sso-session {sso_session}"
                else:
                    available = _list_sso_sessions()
                    if available:
                        hint = (
                            f"Expired. Run: aws sso login --sso-session <session>\n"
                            f"           Available sessions: {', '.join(available)}"
                        )
                    else:
                        hint = "Expired. Run: aws sso login --sso-session <your-sso-session>"
                all_ok &= check("SSO session", False, hint)
        except subprocess.TimeoutExpired:
            all_ok &= check("SSO session", False, "Timed out checking credentials")

    return all_ok


# ─── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
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
    if kubectl:
        real = os.path.realpath(kubectl)
        is_rancher = real.startswith(("/Applications/Rancher", os.path.expanduser("~/.rd")))
        homebrew = "/opt/homebrew/bin/kubectl"
        if is_rancher and os.path.isfile(homebrew):
            all_ok &= check("kubectl", True, f"Rancher Desktop detected, will use {homebrew}")
        elif is_rancher:
            all_ok &= check(
                "kubectl",
                False,
                "Rancher Desktop kubectl found but no homebrew fallback. Run: brew install kubectl",
            )
        else:
            all_ok &= check("kubectl", True, kubectl)
    else:
        all_ok &= check("kubectl", False, "Not found. Run: brew install kubectl")

    # 3. AWS CLI
    aws = shutil.which("aws")
    all_ok &= check("AWS CLI", bool(aws), aws or "Not found. Run: brew install awscli")

    # 4. Config file — auto-discover if missing
    config_path = find_config()
    if config_path:
        all_ok &= check("Config", True, str(config_path))
        config = load_config(config_path)
    else:
        # Auto-discover from kubeconfigs + AWS profiles
        discovered = discover_environments()
        if discovered:
            output = Path.home() / ".eks-config.json"
            auto_generate_config(output, discovered)
            all_ok &= check(
                "Config",
                True,
                f"Auto-discovered {len(discovered)} environments → {output}",
            )
            config = load_config(output)
        else:
            all_ok &= check(
                "Config",
                False,
                "No ~/.kube/config_* files found. Cannot auto-discover environments.",
            )
            config = None

    if config:
        envs = sorted(config.get("environments", {}).keys())
        print(f"         Environments: {', '.join(envs)}")

    # 5. Optional: stern
    stern = shutil.which("stern")
    check(
        "stern (optional)",
        bool(stern),
        stern or "Not installed. Run: brew install stern (for --all-pods)",
    )

    # 6. Optional: detect-secrets
    try:
        __import__("detect_secrets")
        check("detect-secrets (optional)", True, "Entropy-based redaction enabled")
    except ImportError:
        check(
            "detect-secrets (optional)",
            True,
            "Not installed — regex redaction only (fine for most cases)",
        )

    # 7. Environment-specific checks
    if args.env and config:
        all_ok &= check_environment(config, args.env, has_aws=bool(aws))

    print(f"\n{'All checks passed.' if all_ok else 'Some checks failed — see above.'}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
