"""kubectl discovery and execution."""

import os
import shutil
import subprocess
from typing import Optional

from lib.config import get_env_config, get_kubeconfig_path, die
from lib.redaction import redact_text


def find_kubectl() -> str:
    """Find kubectl binary, preferring homebrew over Rancher Desktop."""
    homebrew = "/opt/homebrew/bin/kubectl"
    if os.path.isfile(homebrew) and os.access(homebrew, os.X_OK):
        default = shutil.which("kubectl")
        if default and os.path.realpath(default).startswith(
            ("/Applications/Rancher", os.path.expanduser("~/.rd"))
        ):
            return homebrew
    found = shutil.which("kubectl")
    if found:
        return found
    die("kubectl not found. Install: brew install kubectl")
    return ""


def run_kubectl(
    config: dict, env_name: str, args: list[str], redact: bool = True
) -> tuple[int, str]:
    """Run kubectl with proper kubeconfig. Returns (exit_code, output)."""
    kubeconfig = get_kubeconfig_path(config, env_name)
    if not os.path.isfile(kubeconfig):
        env_cfg = get_env_config(config, env_name)
        die(
            f"Kubeconfig not found: {kubeconfig}\n"
            f"Run: aws eks update-kubeconfig --profile {env_cfg.get('profile', env_name)} "
            f"--name {env_cfg.get('cluster', 'eks01-' + env_name)} "
            f"--kubeconfig {kubeconfig}"
        )

    env_cfg = get_env_config(config, env_name)
    namespace = env_cfg.get("namespace", "default")
    kubectl = find_kubectl()
    cmd = [kubectl, f"--kubeconfig={kubeconfig}", "-n", namespace] + args

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        die("kubectl timed out after 120s.")

    output = result.stdout + result.stderr

    if result.returncode != 0 and any(
        kw in output.lower() for kw in ("token", "expired", "unauthorized")
    ):
        sso_session = env_cfg.get("sso_session", "lab")
        die(
            f"Authentication failed. SSO session may be expired.\n"
            f"Run: aws sso login --sso-session {sso_session}"
        )

    if redact:
        output = redact_text(output, config)

    return result.returncode, output


def stream_kubectl(
    config: dict, env_name: str, args: list[str]
) -> int:
    """Stream kubectl output with real-time redaction. For --follow."""
    kubeconfig = get_kubeconfig_path(config, env_name)
    env_cfg = get_env_config(config, env_name)
    namespace = env_cfg.get("namespace", "default")
    kubectl = find_kubectl()
    cmd = [kubectl, f"--kubeconfig={kubeconfig}", "-n", namespace] + args

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for line in proc.stdout:
            print(redact_text(line.rstrip(), config))
    except KeyboardInterrupt:
        proc.terminate()
    return 0
