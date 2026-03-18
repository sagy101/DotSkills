"""Tests for jenkins-manager secret redaction.

Mirrors eks-pod-ops test_redaction.py — same patterns, ensures Jenkins log
output is scrubbed before the agent sees it.
"""

import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent.parent / "jenkins-manager" / "scripts")
)

from jenkins_redaction import redact_line, redact_text

# ─── Bearer / Auth Tokens ───────────────────────────────────────────────────


class TestBearerTokens:
    def test_bearer_redacted(self):
        assert "Bearer [REDACTED]" in redact_text("Bearer abc123secrettoken")

    def test_bearer_case_insensitive(self):
        assert "bearer [REDACTED]" in redact_text("bearer abc123secrettoken")

    def test_short_bearer_not_redacted(self):
        assert redact_text("Bearer short") == "Bearer short"

    def test_authorization_header(self):
        assert "Authorization: [REDACTED]" in redact_text("Authorization: Basic dXNlcjpwYXNz")


# ─── Key-Value Secrets ───────────────────────────────────────────────────────


class TestKeyValueSecrets:
    def test_password_equals(self):
        assert "password=[REDACTED]" in redact_text("password=hunter2")

    def test_password_colon(self):
        assert "password: [REDACTED]" in redact_text("password: hunter2")

    def test_token_equals(self):
        assert "token=[REDACTED]" in redact_text("token=abc123")

    def test_api_key(self):
        assert "api_key=[REDACTED]" in redact_text("api_key=sk-1234567890")

    def test_api_hyphen_key(self):
        assert "api-key=[REDACTED]" in redact_text("api-key=sk-1234567890")

    def test_secret_key(self):
        assert "secret_key=[REDACTED]" in redact_text("secret_key=mysecret")

    def test_client_secret(self):
        assert "client_secret=[REDACTED]" in redact_text("client_secret=xyz789")

    def test_case_insensitive(self):
        assert "PASSWORD=[REDACTED]" in redact_text("PASSWORD=hunter2")

    def test_preserves_surrounding_text(self):
        result = redact_text("connecting with password=hunter2 to database")
        assert "connecting with password=[REDACTED]" in result
        assert "to database" in result


# ─── AWS Credentials ────────────────────────────────────────────────────────


class TestAWSCredentials:
    def test_aws_secret_key(self):
        assert (
            "AWS_SECRET_ACCESS_KEY=[REDACTED]"
            in redact_text(
                "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"  # pragma: allowlist secret
            )
        )

    def test_aws_session_token(self):
        assert "AWS_SESSION_TOKEN=[REDACTED]" in redact_text(
            "AWS_SESSION_TOKEN=FwoGZXIvYXdzEBYaDH..."
        )

    def test_aws_access_key_id(self):
        assert "[REDACTED AWS KEY]" in redact_text(
            "AKIAIOSFODNN7EXAMPLE"  # pragma: allowlist secret
        )

    def test_aws_temp_key(self):
        assert "[REDACTED AWS KEY]" in redact_text("ASIAXXX123456789012")


# ─── JWT ─────────────────────────────────────────────────────────────────────


class TestJWT:
    def test_jwt_redacted(self):
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"  # pragma: allowlist secret
        assert "[REDACTED JWT]" in redact_text(jwt)


# ─── Private Keys ────────────────────────────────────────────────────────────


class TestPrivateKeys:
    def test_rsa_key(self):
        key = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----"  # pragma: allowlist secret
        assert "[REDACTED PRIVATE KEY]" in redact_text(key)

    def test_generic_private_key(self):
        key = "-----BEGIN PRIVATE KEY-----\ndata\n-----END PRIVATE KEY-----"  # pragma: allowlist secret
        assert "[REDACTED PRIVATE KEY]" in redact_text(key)


# ─── Connection Strings ─────────────────────────────────────────────────────


class TestConnectionStrings:
    def test_postgres(self):
        result = redact_text("postgres://user:secretpass@host:5432/db")
        assert "[REDACTED]" in result
        assert "secretpass" not in result

    def test_mysql(self):
        result = redact_text("mysql://root:password123@localhost/mydb")
        assert "[REDACTED]" in result
        assert "password123" not in result

    def test_jdbc(self):
        result = redact_text("jdbc://admin:s3cret@db.corp:3306/prod")
        assert "[REDACTED]" in result
        assert "s3cret" not in result


# ─── Base64 Blobs ───────────────────────────────────────────────────────────


class TestBase64Blobs:
    def test_long_base64_redacted(self):
        blob = "A" * 100
        assert "[REDACTED BASE64]" in redact_text(blob)

    def test_short_base64_preserved(self):
        blob = "A" * 50
        assert blob in redact_text(blob)


# ─── No False Positives ─────────────────────────────────────────────────────


class TestNoFalsePositives:
    def test_normal_log_line(self):
        line = "[Pipeline] stage (Build)"
        assert line == redact_text(line)

    def test_jenkins_pipeline_output(self):
        line = "[Pipeline] // stage"
        assert line == redact_text(line)

    def test_build_step_output(self):
        line = "Finished: SUCCESS"
        assert line == redact_text(line)

    def test_uuid_not_redacted(self):
        line = "id: 550e8400-e29b-41d4-a716-446655440000"
        assert line == redact_text(line)

    def test_short_hash_not_redacted(self):
        line = "commit: a1b2c3d4e5f6"
        assert line == redact_text(line)

    def test_maven_output(self):
        line = "[INFO] BUILD SUCCESS"
        assert line == redact_text(line)


# ─── redact_line alias ──────────────────────────────────────────────────────


class TestRedactLine:
    def test_single_line(self):
        assert "password=[REDACTED]" in redact_line("password=hunter2")

    def test_preserves_clean_line(self):
        line = "Step 1/10: Building image"
        assert redact_line(line) == line
