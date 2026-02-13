"""FastAPI webhook server.

Runs in the same process as the bot, sharing the event loop.
Receives external webhooks and publishes them as events on the bus.
"""

import uuid
from typing import Any, Dict, Optional

import structlog
from fastapi import FastAPI, Header, HTTPException, Request

from ..config.settings import Settings
from ..events.bus import EventBus
from ..events.types import WebhookEvent
from .auth import verify_github_signature, verify_shared_secret

logger = structlog.get_logger()


def create_api_app(
    event_bus: EventBus,
    settings: Settings,
) -> FastAPI:
    """Create the FastAPI application."""

    app = FastAPI(
        title="Claude Code Telegram - Webhook API",
        version="0.1.0",
        docs_url="/docs" if settings.development_mode else None,
        redoc_url=None,
    )

    @app.get("/health")
    async def health_check() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/webhooks/{provider}")
    async def receive_webhook(
        provider: str,
        request: Request,
        x_hub_signature_256: Optional[str] = Header(None),
        x_github_event: Optional[str] = Header(None),
        x_github_delivery: Optional[str] = Header(None),
        authorization: Optional[str] = Header(None),
    ) -> Dict[str, str]:
        """Receive and validate webhook from an external provider."""
        body = await request.body()

        # Verify signature based on provider
        if provider == "github":
            secret = settings.github_webhook_secret
            if not secret:
                raise HTTPException(
                    status_code=500,
                    detail="GitHub webhook secret not configured",
                )
            if not verify_github_signature(body, x_hub_signature_256, secret):
                logger.warning(
                    "GitHub webhook signature verification failed",
                    delivery_id=x_github_delivery,
                )
                raise HTTPException(status_code=401, detail="Invalid signature")

            event_type_name = x_github_event or "unknown"
            delivery_id = x_github_delivery or str(uuid.uuid4())
        else:
            # Generic provider — use shared secret
            secret = settings.webhook_api_secret
            if secret and not verify_shared_secret(authorization, secret):
                raise HTTPException(status_code=401, detail="Invalid authorization")
            event_type_name = request.headers.get("X-Event-Type", "unknown")
            delivery_id = request.headers.get("X-Delivery-ID", str(uuid.uuid4()))

        # Parse JSON payload
        try:
            payload: Dict[str, Any] = await request.json()
        except Exception:
            payload = {"raw_body": body.decode("utf-8", errors="replace")[:5000]}

        # Publish event to the bus
        event = WebhookEvent(
            provider=provider,
            event_type_name=event_type_name,
            payload=payload,
            delivery_id=delivery_id,
        )

        await event_bus.publish(event)

        logger.info(
            "Webhook received and published",
            provider=provider,
            event_type=event_type_name,
            delivery_id=delivery_id,
            event_id=event.id,
        )

        return {"status": "accepted", "event_id": event.id}

    return app


async def run_api_server(
    event_bus: EventBus,
    settings: Settings,
) -> None:
    """Run the FastAPI server using uvicorn."""
    import uvicorn

    app = create_api_app(event_bus, settings)

    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=settings.api_server_port,
        log_level="info" if not settings.debug else "debug",
    )
    server = uvicorn.Server(config)
    await server.serve()
