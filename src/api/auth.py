"""Webhook signature verification for external providers.

Each provider has its own signing mechanism:
- GitHub: HMAC-SHA256 with X-Hub-Signature-256 header
- Generic: shared secret in Authorization header
"""

import hashlib
import hmac
from typing import Optional

import structlog

logger = structlog.get_logger()


def verify_github_signature(
    payload_body: bytes,
    signature_header: Optional[str],
    secret: str,
) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature.

    GitHub sends the signature as: sha256=<hex_digest>
    """
    if not signature_header:
        logger.warning("GitHub webhook missing signature header")
        return False

    if not signature_header.startswith("sha256="):
        logger.warning("GitHub webhook signature has unexpected format")
        return False

    expected_signature = (
        "sha256="
        + hmac.new(
            secret.encode("utf-8"),
            payload_body,
            hashlib.sha256,
        ).hexdigest()
    )

    return hmac.compare_digest(expected_signature, signature_header)


def verify_shared_secret(
    authorization_header: Optional[str],
    secret: str,
) -> bool:
    """Verify a simple shared secret in the Authorization header.

    Expects: Bearer <secret>
    """
    if not authorization_header:
        return False

    if not authorization_header.startswith("Bearer "):
        return False

    token = authorization_header[7:]
    return hmac.compare_digest(token, secret)
