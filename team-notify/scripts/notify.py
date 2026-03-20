#!/usr/bin/env python3
"""Send a notification to Slack and/or Microsoft Teams via incoming webhooks.

Usage:
    python3 notify.py --message "Build #42 failed" [OPTIONS]

Exit codes:
    0 = all messages sent successfully
    1 = HTTP/network error
    2 = config or credential error
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIG_FILENAME = ".notify.json"

SLACK_COLORS = {
    "info": "#439FE0",
    "success": "good",
    "warning": "warning",
    "error": "danger",
}

TEAMS_COLORS = {
    "info": "0076D7",
    "success": "107C10",
    "warning": "FF8C00",
    "error": "D83B01",
}

LEVEL_EMOJI = {
    "info": "ℹ️",
    "success": "✅",
    "warning": "⚠️",
    "error": "❌",
}

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _find_project_config() -> Path | None:
    here = Path.cwd()
    for directory in [here, *here.parents]:
        candidate = directory / CONFIG_FILENAME
        if candidate.exists():
            return candidate
    return None


def _find_global_config() -> Path | None:
    candidate = Path.home() / CONFIG_FILENAME
    return candidate if candidate.exists() else None


def _load_config(config_override: str | None = None) -> dict:
    if config_override:
        p = Path(config_override)
        if not p.exists():
            print(f"[ERROR] Config file not found: {config_override}", file=sys.stderr)
            sys.exit(2)
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"[ERROR] Invalid JSON in {config_override}: {e}", file=sys.stderr)
            sys.exit(2)

    project_cfg = _find_project_config()
    global_cfg = _find_global_config()

    if not project_cfg and not global_cfg:
        print(
            f"[ERROR] No config found. Create {CONFIG_FILENAME} in project root or ~/.notify.json\n"
            "  Minimal example:\n"
            + json.dumps(
                {"channels": {"slack": {"webhook_env": "SLACK_WEBHOOK_URL"}}, "default_channel": "slack"},
                indent=2,
            ),
            file=sys.stderr,
        )
        sys.exit(2)

    global_raw = json.loads(global_cfg.read_text(encoding="utf-8")) if global_cfg else {}
    project_raw = json.loads(project_cfg.read_text(encoding="utf-8")) if project_cfg else {}
    return _deep_merge(global_raw, project_raw)


def _resolve_webhook_url(channel_cfg: dict, channel_name: str) -> str:
    env_var = channel_cfg.get("webhook_env", "")
    if not env_var:
        print(f"[ERROR] channels.{channel_name}.webhook_env is not set in config", file=sys.stderr)
        sys.exit(2)
    url = os.environ.get(env_var, "")
    if not url:
        print(
            f"[ERROR] Environment variable {env_var!r} is not set.\n"
            f"  Export it: export {env_var}=\"https://hooks.slack.com/services/...\"",
            file=sys.stderr,
        )
        sys.exit(2)
    return url


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------


def _build_slack_payload(message: str, title: str | None, level: str, link: str | None, mention: str | None) -> dict:
    parts = []
    if mention:
        parts.append(mention)
    if title:
        parts.append(f"*{title}*")
    parts.append(message)
    if link:
        parts.append(f"<{link}|View details>")

    return {
        "attachments": [
            {
                "color": SLACK_COLORS.get(level, "#439FE0"),
                "text": "\n".join(parts),
                "mrkdwn_in": ["text"],
                "fallback": f"{title + ': ' if title else ''}{message}",
            }
        ]
    }


def _build_teams_messagecard_payload(message: str, title: str | None, level: str, link: str | None, mention: str | None) -> dict:
    text_parts = []
    if mention:
        text_parts.append(mention)
    text_parts.append(message)

    payload: dict = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "themeColor": TEAMS_COLORS.get(level, "0076D7"),
        "summary": title or message[:80],
        "title": f"{LEVEL_EMOJI.get(level, '')} {title}" if title else LEVEL_EMOJI.get(level, ""),
        "text": " ".join(text_parts),
    }
    if link:
        payload["potentialAction"] = [
            {
                "@type": "OpenUri",
                "name": "View details",
                "targets": [{"os": "default", "uri": link}],
            }
        ]
    return payload


def _build_teams_adaptive_payload(message: str, title: str | None, level: str, link: str | None, mention: str | None) -> dict:
    body = []
    display_title = f"{LEVEL_EMOJI.get(level, '')} {title}".strip() if title else LEVEL_EMOJI.get(level, "")
    if display_title:
        body.append({"type": "TextBlock", "text": display_title, "weight": "Bolder", "size": "Medium"})

    text = f"{mention} {message}".strip() if mention else message
    body.append({"type": "TextBlock", "text": text, "wrap": True})

    actions = []
    if link:
        actions.append({"type": "Action.OpenUrl", "title": "View details", "url": link})

    card: dict = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.2",
        "body": body,
    }
    if actions:
        card["actions"] = actions

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card,
            }
        ],
    }


# ---------------------------------------------------------------------------
# HTTP send
# ---------------------------------------------------------------------------


def _send(url: str, payload: dict, platform: str) -> bool:
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=15) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[ERROR] {platform}: HTTP {e.code} — {body[:200]}", file=sys.stderr)
        return False
    except URLError as e:
        print(f"[ERROR] {platform}: Network error — {e.reason}", file=sys.stderr)
        return False

    if status != 200 or body not in ("ok", "1", ""):
        # Slack returns "ok", Teams Workflows returns "1", old Teams connector returns ""
        if status == 200 and platform == "teams" and body == "1":
            return True
        if status == 200 and platform == "slack" and body == "ok":
            return True
        if status == 200 and platform == "teams" and body == "":
            return True
        # Some Teams endpoints return 200 with non-"1" body on success too
        if status == 200:
            return True
        print(f"[ERROR] {platform}: Unexpected response {status} — {body[:200]}", file=sys.stderr)
        return False

    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send a notification to Slack and/or Microsoft Teams."
    )
    parser.add_argument("--message", "-m", required=True, help="Notification message body")
    parser.add_argument("--title", "-t", help="Optional title / heading")
    parser.add_argument(
        "--level",
        "-l",
        choices=["info", "success", "warning", "error"],
        default="info",
        help="Severity level (default: info)",
    )
    parser.add_argument("--link", help="Optional URL attached to the notification")
    parser.add_argument(
        "--channel",
        "-c",
        choices=["slack", "teams", "all"],
        help="Target channel (overrides default_channel from config)",
    )
    parser.add_argument(
        "--mention",
        action="store_true",
        help="Prepend developer_mention from config (e.g. @here)",
    )
    parser.add_argument("--config", help="Path to .notify.json config file")
    args = parser.parse_args()

    config = _load_config(args.config)
    channels_cfg = config.get("channels", {})
    default_channel = config.get("default_channel", "slack")
    developer_mention = config.get("developer_mention", "") if args.mention else None

    target = args.channel or default_channel
    if target == "all":
        targets = list(channels_cfg.keys())
    else:
        targets = [target]

    if not targets:
        print("[ERROR] No channels configured and no --channel specified.", file=sys.stderr)
        sys.exit(2)

    errors = []
    for ch in targets:
        if ch not in channels_cfg:
            print(f"[ERROR] Channel '{ch}' not found in config. Available: {list(channels_cfg.keys())}", file=sys.stderr)
            errors.append(ch)
            continue

        ch_cfg = channels_cfg[ch]
        webhook_url = _resolve_webhook_url(ch_cfg, ch)

        if ch == "slack":
            payload = _build_slack_payload(args.message, args.title, args.level, args.link, developer_mention)
        elif ch == "teams":
            fmt = ch_cfg.get("format", "messagecard")
            if fmt == "adaptive":
                payload = _build_teams_adaptive_payload(args.message, args.title, args.level, args.link, developer_mention)
            else:
                payload = _build_teams_messagecard_payload(args.message, args.title, args.level, args.link, developer_mention)
        else:
            print(f"[ERROR] Unknown channel type '{ch}'. Supported: slack, teams.", file=sys.stderr)
            errors.append(ch)
            continue

        ok = _send(webhook_url, payload, ch)
        if ok:
            print(f"[OK] {ch}: notification sent")
        else:
            errors.append(ch)

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
