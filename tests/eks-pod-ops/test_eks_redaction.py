"""Tests for eks-pod-ops redaction and exec blocklist."""

import sys
from pathlib import Path

# Add scripts dir to path so we can import lib
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "eks-pod-ops" / "scripts"))

from lib.redaction import check_exec_allowed, redact_text

# ─── Redaction Tests ──────────────────────────────────────────────────────────


class TestBearerTokens:
    def test_bearer_redacted(self):
        assert "Bearer [REDACTED]" in redact_text("Bearer abc123secrettoken")

    def test_bearer_case_insensitive(self):
        assert "bearer [REDACTED]" in redact_text("bearer abc123secrettoken")

    def test_short_bearer_not_redacted(self):
        # Short tokens (<8 chars) are not redacted to avoid false positives
        assert redact_text("Bearer short") == "Bearer short"

    def test_authorization_header(self):
        assert "Authorization: [REDACTED]" in redact_text("Authorization: Basic dXNlcjpwYXNz")


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


class TestAWSCredentials:
    def test_aws_secret_key(self):
        assert "AWS_SECRET_ACCESS_KEY=[REDACTED]" in redact_text(
            "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        )

    def test_aws_session_token(self):
        assert "AWS_SESSION_TOKEN=[REDACTED]" in redact_text(
            "AWS_SESSION_TOKEN=FwoGZXIvYXdzEBYaDH..."
        )

    def test_aws_access_key_id(self):
        assert "[REDACTED AWS KEY]" in redact_text("AKIAIOSFODNN7EXAMPLE")

    def test_aws_temp_key(self):
        assert "[REDACTED AWS KEY]" in redact_text("ASIAXXX123456789012")


class TestJWT:
    def test_jwt_redacted(self):
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        assert "[REDACTED JWT]" in redact_text(jwt)


class TestPrivateKeys:
    def test_rsa_key(self):
        key = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----"
        assert "[REDACTED PRIVATE KEY]" in redact_text(key)

    def test_generic_private_key(self):
        key = "-----BEGIN PRIVATE KEY-----\ndata\n-----END PRIVATE KEY-----"
        assert "[REDACTED PRIVATE KEY]" in redact_text(key)


class TestConnectionStrings:
    def test_postgres(self):
        result = redact_text("postgres://user:secretpass@host:5432/db")
        assert "[REDACTED]" in result
        assert "secretpass" not in result

    def test_mysql(self):
        result = redact_text("mysql://root:password123@localhost/mydb")
        assert "[REDACTED]" in result
        assert "password123" not in result


class TestBase64Blobs:
    def test_long_base64_redacted(self):
        blob = "A" * 100
        assert "[REDACTED BASE64]" in redact_text(blob)

    def test_short_base64_preserved(self):
        blob = "A" * 50
        assert blob in redact_text(blob)


class TestNoFalsePositives:
    def test_normal_log_line(self):
        line = "2024-01-01 INFO Processing job_id=abc123 status=complete"
        assert line == redact_text(line)

    def test_uuid_not_redacted(self):
        line = "id: 550e8400-e29b-41d4-a716-446655440000"
        assert line == redact_text(line)

    def test_short_hash_not_redacted(self):
        line = "commit: a1b2c3d4e5f6"
        assert line == redact_text(line)


class TestCustomPatterns:
    def test_extra_patterns_from_config(self):
        config = {"redaction": {"extra_patterns": [r"COUCHBASE_PASS=\S+"]}}
        result = redact_text("COUCHBASE_PASS=mysecret123", config)
        assert "[REDACTED]" in result
        assert "mysecret123" not in result

    def test_disabled_redaction(self):
        config = {"redaction": {"disabled": True}}
        assert redact_text("password=hunter2", config) == "password=hunter2"


# ─── Exec Blocklist Tests ────────────────────────────────────────────────────


class TestExecBlocklist:
    def test_bare_env_blocked(self):
        assert check_exec_allowed("env") is not None

    def test_bare_printenv_blocked(self):
        assert check_exec_allowed("printenv") is not None

    def test_bare_set_blocked(self):
        assert check_exec_allowed("set") is not None

    def test_env_with_grep_allowed(self):
        assert check_exec_allowed("sh -c 'env | grep -i java'") is None

    def test_cat_vault_blocked(self):
        assert check_exec_allowed("cat /vault/secrets") is not None

    def test_cat_secret_file_blocked(self):
        assert check_exec_allowed("cat /etc/secret/token") is not None

    def test_cat_pem_blocked(self):
        assert check_exec_allowed("cat /app/cert.pem") is not None

    def test_cat_key_blocked(self):
        assert check_exec_allowed("cat /app/private.key") is not None

    def test_cat_proc_environ_blocked(self):
        assert check_exec_allowed("cat /proc/1/environ") is not None

    def test_strings_proc_blocked(self):
        assert check_exec_allowed("strings /proc/1/maps") is not None

    def test_ls_allowed(self):
        assert check_exec_allowed("ls /app") is None

    def test_cat_normal_file_allowed(self):
        assert check_exec_allowed("cat /app/conf/application.conf") is None

    def test_df_allowed(self):
        assert check_exec_allowed("df -h") is None

    def test_ps_allowed(self):
        assert check_exec_allowed("ps aux") is None

    def test_echo_var_allowed(self):
        assert check_exec_allowed("echo $JAVA_HOME") is None
