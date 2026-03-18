"""Secret redaction for Jenkins console log output.

Mirrors eks-pod-ops redaction pattern. Always-on by default.
"""

import re

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
            r"((?:mysql|postgres|postgresql|mongodb|redis|amqp|mssql|jdbc)"
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


def redact_text(text: str) -> str:
    """Apply redaction patterns to text. Returns redacted text.

    Always-on — no config toggle. Safety by default.
    """
    for pattern, replacement in REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)

    # Optional entropy scan
    if _detect_secrets_available:
        text = _entropy_redact(text)

    return text


def redact_line(line: str) -> str:
    """Apply redaction patterns to a single line."""
    return redact_text(line)


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
                if "[REDACTED" in line:
                    continue  # already handled by pattern-based redaction
                secrets = scan_line(line)
                if secrets:
                    for secret in secrets:
                        val = secret.secret_value
                        if val and len(val) > 60:
                            lines[i] = lines[i].replace(val, "[REDACTED HIGH-ENTROPY]")
            return "\n".join(lines)
    except Exception:
        return text
