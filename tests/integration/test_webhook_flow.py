"""Integration tests for webhook verification and FastAPI server.

Uses httpx.AsyncClient against the real FastAPI app to exercise
GitHub, GitLab, and Bitbucket webhook endpoints end-to-end.
"""

import hashlib
import hmac
import json

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.server import create_api_app
from src.config.settings import Settings
from src.events.bus import EventBus
from src.storage.database import DatabaseManager


def _github_signature(body: bytes, secret: str) -> str:
    """Compute the X-Hub-Signature-256 header value."""
    return "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()


def _bitbucket_signature(body: bytes, secret: str) -> str:
    """Compute the X-Hub-Signature header value (Bitbucket format)."""
    return "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()


# ── GitHub Webhook ───────────────────────────────────────────────────


class TestGitHubWebhookVerification:
    """POST /webhooks/github with valid and invalid signatures."""

    async def test_valid_signature(
        self, event_bus: EventBus, mock_settings: Settings
    ):
        app = create_api_app(event_bus, mock_settings)
        transport = ASGITransport(app=app)

        payload = {"action": "opened", "number": 1}
        body = json.dumps(payload).encode()
        sig = _github_signature(body, mock_settings.github_webhook_secret)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhooks/github",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": sig,
                    "X-GitHub-Event": "pull_request",
                    "X-GitHub-Delivery": "delivery-001",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert "event_id" in data

    async def test_invalid_signature(
        self, event_bus: EventBus, mock_settings: Settings
    ):
        app = create_api_app(event_bus, mock_settings)
        transport = ASGITransport(app=app)

        payload = {"action": "opened"}
        body = json.dumps(payload).encode()

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhooks/github",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": "sha256=invalid",
                    "X-GitHub-Event": "push",
                    "X-GitHub-Delivery": "delivery-002",
                },
            )

        assert resp.status_code == 401

    async def test_missing_signature(
        self, event_bus: EventBus, mock_settings: Settings
    ):
        app = create_api_app(event_bus, mock_settings)
        transport = ASGITransport(app=app)

        body = b'{"action":"opened"}'

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhooks/github",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Event": "push",
                },
            )

        assert resp.status_code == 401


# ── GitLab Webhook ───────────────────────────────────────────────────


class TestGitLabWebhookVerification:
    """POST /webhooks/gitlab with valid and invalid tokens."""

    async def test_valid_token(
        self, event_bus: EventBus, mock_settings: Settings
    ):
        app = create_api_app(event_bus, mock_settings)
        transport = ASGITransport(app=app)

        payload = {"object_kind": "merge_request"}
        body = json.dumps(payload).encode()

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhooks/gitlab",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Gitlab-Token": mock_settings.gitlab_webhook_secret,
                    "X-Gitlab-Event": "Merge Request Hook",
                },
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    async def test_invalid_token(
        self, event_bus: EventBus, mock_settings: Settings
    ):
        app = create_api_app(event_bus, mock_settings)
        transport = ASGITransport(app=app)

        body = b'{"object_kind":"push"}'

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhooks/gitlab",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Gitlab-Token": "wrong_token",
                    "X-Gitlab-Event": "Push Hook",
                },
            )

        assert resp.status_code == 401

    async def test_missing_token(
        self, event_bus: EventBus, mock_settings: Settings
    ):
        app = create_api_app(event_bus, mock_settings)
        transport = ASGITransport(app=app)

        body = b'{"object_kind":"push"}'

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhooks/gitlab",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Gitlab-Event": "Push Hook",
                },
            )

        assert resp.status_code == 401


# ── Bitbucket Webhook ────────────────────────────────────────────────


class TestBitbucketWebhookVerification:
    """POST /webhooks/bitbucket with valid and invalid signatures."""

    async def test_valid_signature(
        self, event_bus: EventBus, mock_settings: Settings
    ):
        app = create_api_app(event_bus, mock_settings)
        transport = ASGITransport(app=app)

        payload = {"push": {"changes": []}}
        body = json.dumps(payload).encode()
        sig = _bitbucket_signature(body, mock_settings.bitbucket_webhook_secret)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhooks/bitbucket",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature": sig,
                    "X-Event-Key": "repo:push",
                    "X-Request-UUID": "uuid-001",
                },
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    async def test_invalid_signature(
        self, event_bus: EventBus, mock_settings: Settings
    ):
        app = create_api_app(event_bus, mock_settings)
        transport = ASGITransport(app=app)

        body = b'{"push":{}}'

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhooks/bitbucket",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature": "sha256=bad",
                    "X-Event-Key": "repo:push",
                },
            )

        assert resp.status_code == 401

    async def test_missing_signature(
        self, event_bus: EventBus, mock_settings: Settings
    ):
        app = create_api_app(event_bus, mock_settings)
        transport = ASGITransport(app=app)

        body = b'{"push":{}}'

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhooks/bitbucket",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Event-Key": "repo:push",
                },
            )

        assert resp.status_code == 401


# ── Health endpoint ──────────────────────────────────────────────────


class TestHealthEndpoint:
    """Smoke-test the /health route."""

    async def test_health_ok(
        self, event_bus: EventBus, mock_settings: Settings
    ):
        app = create_api_app(event_bus, mock_settings)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
