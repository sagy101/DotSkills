"""Pod resolution and container selection."""

import json

from lib.config import die
from lib.kubectl import run_kubectl

KNOWN_SIDECARS = frozenset(
    {
        "statsite",
        "istio-proxy",
        "envoy",
        "datadog-agent",
        "fluentd",
        "fluentbit",
        "fluent-bit",
        "aws-otel-collector",
        "xray-daemon",
        "vault-agent",
        "vault-agent-init",
    }
)


def resolve_pods(config: dict, env_name: str, service: str) -> list[dict]:
    """Find pods for a service by label or name prefix."""
    # Try label selector first
    rc, output = run_kubectl(
        config,
        env_name,
        ["get", "pods", "-l", f"app={service}", "-o", "json"],
        redact=False,
    )
    pods = _parse_pod_list(output) if rc == 0 else []

    # Fallback: name prefix match
    if not pods:
        rc, output = run_kubectl(config, env_name, ["get", "pods", "-o", "json"], redact=False)
        if rc == 0:
            try:
                data = json.loads(output)
                pods = [
                    _parse_pod(item)
                    for item in data.get("items", [])
                    if item["metadata"]["name"].startswith(service)
                ]
            except (json.JSONDecodeError, KeyError):
                pass

    return pods


def resolve_single_pod(config: dict, env_name: str, service: str) -> tuple[str, str]:
    """Resolve to one running pod name and its app container."""
    pods = resolve_pods(config, env_name, service)
    if not pods:
        die(f"No pods found for service '{service}' in {env_name}.")
    running = [p for p in pods if p["status"] == "Running"]
    pod = running[0] if running else pods[0]
    container = pick_app_container(pod["containers"], service)
    return pod["name"], container


def pick_app_container(containers: list[str], service: str) -> str:
    """Pick the app container, skipping known sidecars."""
    for c in containers:
        if c == service:
            return c
    for c in containers:
        if c not in KNOWN_SIDECARS:
            return c
    return containers[0] if containers else ""


def print_pod_table(pods: list[dict], env_name: str):
    print(f"Pods in {env_name}:")
    print(f"{'NAME':<60} {'STATUS':<12} {'READY':<8} {'RESTARTS':<10} {'CONTAINERS'}")
    print("\u2500" * 120)
    for p in pods:
        containers = ", ".join(p["containers"])
        print(f"{p['name']:<60} {p['status']:<12} {p['ready']:<8} {p['restarts']:<10} {containers}")


def _parse_pod_list(output: str) -> list[dict]:
    try:
        data = json.loads(output)
        return [_parse_pod(item) for item in data.get("items", [])]
    except (json.JSONDecodeError, KeyError):
        return []


def _parse_pod(item: dict) -> dict:
    meta = item.get("metadata", {})
    spec = item.get("spec", {})
    status = item.get("status", {})
    containers = [c["name"] for c in spec.get("containers", [])]
    container_statuses = status.get("containerStatuses", [])
    ready = sum(1 for cs in container_statuses if cs.get("ready"))
    return {
        "name": meta.get("name", ""),
        "status": status.get("phase", "Unknown"),
        "containers": containers,
        "ready": f"{ready}/{len(containers)}",
        "restarts": sum(cs.get("restartCount", 0) for cs in container_statuses),
    }
