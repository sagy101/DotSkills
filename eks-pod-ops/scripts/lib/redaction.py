"""Secret redaction and exec safety."""

import contextlib
import re
from typing import Any, NamedTuple

# ─── Redaction Patterns ───────────────────────────────────────────────────────

REDACTION_PATTERNS = [
    # Auth headers and tokens
    (re.compile(r"(Bearer\s+)\S{8,}", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(Authorization:\s*)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    # Key-value secrets
    (
        re.compile(
            r"((?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|"
            r"private[_-]?key|secret[_-]?key|client[_-]?secret|auth[_-]?token)"
            r"[=:]\s*)\S+",
            re.IGNORECASE,
        ),
        r"\1[REDACTED]",
    ),
    # AWS credentials
    (re.compile(r"(AWS_SECRET_ACCESS_KEY[=:]\s*)\S+"), r"\1[REDACTED]"),
    (re.compile(r"(AWS_SESSION_TOKEN[=:]\s*)\S+"), r"\1[REDACTED]"),
    (re.compile(r"((?:AKID|AKIA|AIDA|AROA|ASIA)[A-Z0-9]{12,})"), "[REDACTED AWS KEY]"),
    # Private keys
    (
        re.compile(r"-----BEGIN[^-]*PRIVATE\s+KEY-----[\s\S]*?-----END[^-]*PRIVATE\s+KEY-----"),
        "[REDACTED PRIVATE KEY]",
    ),
    # JWT tokens
    (
        re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"),
        "[REDACTED JWT]",
    ),
    # Connection strings with embedded passwords
    (
        re.compile(
            r"((?:mysql|postgres|postgresql|mongodb|redis|amqp|mssql)"
            r"://[^:]+:)\S+(@)",
            re.IGNORECASE,
        ),
        r"\1[REDACTED]\2",
    ),
    # Base64 blobs >80 chars (likely certs/keys)
    (
        re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{80,}={0,2}(?![A-Za-z0-9+/=])"),
        "[REDACTED BASE64]",
    ),
]

# Optional: detect-secrets entropy detection
_detect_secrets_available = False
try:
    from detect_secrets.core.scan import scan_line
    from detect_secrets.settings import transient_settings

    _detect_secrets_available = True
except ImportError:
    pass

# ─── Exec Blocklist ──────────────────────────────────────────────────────────


class _ExecRule(NamedTuple):
    pattern: re.Pattern[str]
    reason: str
    suggest: str


EXEC_BLOCKLIST = [
    _ExecRule(
        re.compile(r"^\s*(env|printenv|set)\s*$"),
        "Dumps all environment variables including secrets.",
        "env | grep -i <KEYWORD>",
    ),
    _ExecRule(
        re.compile(r"cat\s+.*(secret|vault|credential|\.key|\.pem)", re.I),
        "Reads secret/credential files directly.",
        "Describe what information you need from the pod.",
    ),
    _ExecRule(
        re.compile(r"cat\s+/proc/\d+/environ"),
        "Dumps process environment including secrets.",
        "echo $SPECIFIC_VAR_NAME",
    ),
    _ExecRule(
        re.compile(r"strings\s+/proc/"),
        "May expose secrets from process memory.",
        "Use specific diagnostic commands.",
    ),
]


def redact_text(text: str, config: dict[str, Any] | None = None) -> str:
    """Apply redaction patterns to text. Returns redacted text."""
    if config and config.get("redaction", {}).get("disabled"):
        return text

    for pattern, replacement in REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)

    # Custom patterns from config
    if config:
        for p in config.get("redaction", {}).get("extra_patterns", []):
            with contextlib.suppress(re.error):
                text = re.sub(p, "[REDACTED]", text)

    # Optional entropy scan
    if _detect_secrets_available and (
        not config or not config.get("redaction", {}).get("skip_entropy")
    ):
        text = _entropy_redact(text)

    return text


def _entropy_redact(text: str) -> str:
    """Use detect-secrets to find high-entropy strings."""
    try:
        with transient_settings(
            {
                "plugins_used": [
                    {"name": "HexHighEntropyString", "limit": 4.0},
                    {"name": "Base64HighEntropyString", "limit": 5.0},
                ]
            }
        ):
            lines = text.split("\n")
            for i, line in enumerate(lines):
                secrets = scan_line(line)
                if secrets:
                    for secret in secrets:
                        val = secret.secret_value
                        if val and len(val) > 16:
                            lines[i] = lines[i].replace(val, "[REDACTED HIGH-ENTROPY]")
            return "\n".join(lines)
    except Exception:
        return text


def check_exec_allowed(cmd_str: str) -> str | None:
    """Check if exec command is blocked. Returns error message or None if allowed."""
    for rule in EXEC_BLOCKLIST:
        if rule.pattern.search(cmd_str):
            return f"Blocked: {rule.reason}\nTry instead: {rule.suggest}"
    return None
