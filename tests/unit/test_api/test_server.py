"""Tests for the webhook API server."""

import hashlib
import hmac

from fastapi.testclient import TestClient

from src.api.server import create_api_app
from src.events.bus import EventBus


def make_settings(**overrides):  # type: ignore[no-untyped-def]
    """Create a minimal mock settings object."""
    from unittest.mock import MagicMock

    settings = MagicMock()
    settings.development_mode = True
    settings.github_webhook_secret = overrides.get("github_webhook_secret", "gh-secret")
    settings.webhook_api_secret = overrides.get(
        "webhook_api_secret", "default-api-secret"
    )
    settings.api_server_port = 8080
    settings.debug = False
    return settings


class TestWebhookAPI:
    """Tests for the FastAPI webhook endpoints."""

    def test_health_check(self) -> None:
        bus = EventBus()
        app = create_api_app(bus, make_settings())
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_github_webhook_valid_signature(self) -> None:
        """Valid GitHub webhook is accepted and event published."""
        bus = EventBus()
        secret = "gh-secret"
        settings = make_settings(github_webhook_secret=secret)
        app = create_api_app(bus, settings)
        client = TestClient(app)

        payload = b'{"action": "opened", "number": 1}'
        sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        response = client.post(
            "/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": "del-123",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert "event_id" in data

    def test_github_webhook_invalid_signature(self) -> None:
        """Invalid GitHub signature returns 401."""
        bus = EventBus()
        app = create_api_app(bus, make_settings())
        client = TestClient(app)

        response = client.post(
            "/webhooks/github",
            content=b'{"test": true}',
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=invalid",
                "X-GitHub-Event": "push",
            },
        )

        assert response.status_code == 401

    def test_generic_webhook_no_secret_configured_rejected(self) -> None:
        """Generic webhooks without configured secret return 500."""
        bus = EventBus()
        settings = make_settings(webhook_api_secret=None)
        app = create_api_app(bus, settings)
        client = TestClient(app)

        response = client.post(
            "/webhooks/custom",
            json={"event": "test"},
            headers={"X-Event-Type": "test.event"},
        )

        assert response.status_code == 500

    def test_generic_webhook_with_auth(self) -> None:
        """Generic webhooks with configured secret require Bearer token."""
        bus = EventBus()
        settings = make_settings(webhook_api_secret="my-api-secret")
        app = create_api_app(bus, settings)
        client = TestClient(app)

        # Without auth
        response = client.post(
            "/webhooks/custom",
            json={"data": "test"},
        )
        assert response.status_code == 401

        # With valid auth
        response = client.post(
            "/webhooks/custom",
            json={"data": "test"},
            headers={"Authorization": "Bearer my-api-secret"},
        )
        assert response.status_code == 200

    def test_github_webhook_no_secret_configured(self) -> None:
        """GitHub webhook without configured secret returns 500."""
        bus = EventBus()
        settings = make_settings(github_webhook_secret=None)
        app = create_api_app(bus, settings)
        client = TestClient(app)

        response = client.post(
            "/webhooks/github",
            json={"test": True},
            headers={"X-GitHub-Event": "push"},
        )

        assert response.status_code == 500

    def test_generic_webhook_wrong_token_rejected(self) -> None:
        """Generic webhook with wrong Bearer token returns 401."""
        bus = EventBus()
        settings = make_settings(webhook_api_secret="correct-secret")
        app = create_api_app(bus, settings)
        client = TestClient(app)

        response = client.post(
            "/webhooks/custom",
            json={"data": "test"},
            headers={"Authorization": "Bearer wrong-secret"},
        )

        assert response.status_code == 401
