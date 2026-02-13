"""Tests for webhook authentication."""

from src.api.auth import verify_github_signature, verify_shared_secret


class TestGitHubSignatureVerification:
    """Tests for GitHub webhook HMAC-SHA256 verification."""

    def test_valid_signature(self) -> None:
        """Valid HMAC-SHA256 signature passes."""
        import hashlib
        import hmac

        secret = "test-secret"
        payload = b'{"action": "push"}'
        sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        assert verify_github_signature(payload, sig, secret) is True

    def test_invalid_signature(self) -> None:
        """Wrong signature is rejected."""
        assert verify_github_signature(b"payload", "sha256=wrong", "secret") is False

    def test_missing_signature(self) -> None:
        """Missing signature header is rejected."""
        assert verify_github_signature(b"payload", None, "secret") is False

    def test_wrong_format(self) -> None:
        """Non-sha256 format is rejected."""
        assert verify_github_signature(b"payload", "sha1=abc", "secret") is False


class TestSharedSecretVerification:
    """Tests for shared secret Bearer token verification."""

    def test_valid_bearer_token(self) -> None:
        assert verify_shared_secret("Bearer my-secret", "my-secret") is True

    def test_invalid_token(self) -> None:
        assert verify_shared_secret("Bearer wrong", "my-secret") is False

    def test_missing_header(self) -> None:
        assert verify_shared_secret(None, "my-secret") is False

    def test_no_bearer_prefix(self) -> None:
        assert verify_shared_secret("my-secret", "my-secret") is False
