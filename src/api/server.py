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
from ..events.middleware import WebhookFilter
from ..events.types import WebhookEvent
from ..storage.database import DatabaseManager
from .auth import verify_github_signature, verify_shared_secret

logger = structlog.get_logger()


def create_api_app(
    event_bus: EventBus,
    settings: Settings,
    db_manager: Optional[DatabaseManager] = None,
    webhook_filter: Optional[WebhookFilter] = None,
) -> FastAPI:
    """Create the FastAPI application."""

    app = FastAPI(
        title="Claude Code Telegram - Webhook API",
        version="0.1.0",
        docs_url="/docs" if settings.development_mode else None,
        redoc_url=None,
    )

    # Per-app filter+stats. The filter is always on with hardcoded rules
    # tuned for the pager; tests can inject a custom one for coverage.
    if webhook_filter is None:
        webhook_filter = WebhookFilter()
    app.state.webhook_filter = webhook_filter
    app.state.webhook_stats = webhook_filter.stats

    @app.get("/health")
    async def health_check() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/webhooks/health")
    async def webhook_health() -> Dict[str, Any]:
        """Webhook subsystem health + drop/escalate counters.

        Counters are process-lifetime and in-memory (reset on restart).
        Loopback-only by default (see api_server_host doc); no auth.
        """
        return app.state.webhook_stats.snapshot()

    @app.post("/webhooks/{provider}")
    async def receive_webhook(
        provider: str,
        request: Request,
        x_hub_signature_256: Optional[str] = Header(None),
        x_github_event: Optional[str] = Header(None),
        x_github_delivery: Optional[str] = Header(None),
        authorization: Optional[str] = Header(None),
    ) -> Dict[str, Any]:
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
            # Generic provider auth policy:
            #
            #   public bind (host != 127.0.0.1) -> WEBHOOK_API_SECRET MUST be
            #     set, every request MUST carry a matching Bearer. This is
            #     the original fail-closed behavior; misconfiguration must
            #     be loud, not silent.
            #
            #   loopback bind (host == 127.0.0.1) -> WEBHOOK_API_SECRET is
            #     optional. The kernel guarantees only local processes can
            #     reach the socket, so the trust boundary is enforced at
            #     the network layer. Operators who want defense-in-depth
            #     can still set the secret; when set, the Bearer check
            #     runs as before. When unset, the request is accepted.
            #
            # See tests/unit/test_api/test_server.py for the three cases.
            secret = settings.webhook_api_secret
            host = getattr(settings, "api_server_host", "127.0.0.1")
            loopback_only = host == "127.0.0.1"
            if not secret:
                if not loopback_only:
                    raise HTTPException(
                        status_code=500,
                        detail=(
                            "Webhook API secret not configured. "
                            "Set WEBHOOK_API_SECRET to accept webhooks "
                            "from this provider on a non-loopback bind."
                        ),
                    )
                # Loopback + no secret: accept, kernel is the trust boundary.
            else:
                if not verify_shared_secret(authorization, secret):
                    raise HTTPException(status_code=401, detail="Invalid authorization")
            event_type_name = request.headers.get("X-Event-Type", "unknown")
            delivery_id = request.headers.get("X-Delivery-ID", str(uuid.uuid4()))

        # Parse JSON payload
        try:
            payload: Dict[str, Any] = await request.json()
        except Exception:
            payload = {"raw_body": body.decode("utf-8", errors="replace")[:5000]}

        # Pre-bus noise filter. Drops housekeeping events (queued runs,
        # branch deletes, ping handshakes, retries) before they wake the
        # agent. See src/events/middleware.py for rules.
        escalate, reason = webhook_filter.should_escalate(
            event_type_name, payload, delivery_id
        )
        if not escalate:
            logger.info(
                "Webhook dropped by filter",
                provider=provider,
                event_type=event_type_name,
                delivery_id=delivery_id,
                reason=reason,
            )
            return {
                "status": "dropped",
                "reason": reason,
                "delivery_id": delivery_id,
            }

        # Atomic dedupe: attempt INSERT first, only publish if new
        if db_manager and delivery_id:
            is_new = await _try_record_webhook(
                db_manager,
                event_id=str(uuid.uuid4()),
                provider=provider,
                event_type=event_type_name,
                delivery_id=delivery_id,
                payload=payload,
            )
            if not is_new:
                logger.info(
                    "Duplicate webhook delivery ignored",
                    provider=provider,
                    delivery_id=delivery_id,
                )
                return {
                    "status": "duplicate",
                    "delivery_id": delivery_id,
                }

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


async def _try_record_webhook(
    db_manager: DatabaseManager,
    event_id: str,
    provider: str,
    event_type: str,
    delivery_id: str,
    payload: Dict[str, Any],
) -> bool:
    """Atomically insert a webhook event, returning whether it was new.

    Uses INSERT OR IGNORE on the unique delivery_id column.
    If the row already exists the insert is a no-op and changes() == 0.
    Returns True if the event is new (inserted), False if duplicate.
    """
    import json

    async with db_manager.get_connection() as conn:
        await conn.execute(
            """
            INSERT OR IGNORE INTO webhook_events
            (event_id, provider, event_type, delivery_id, payload,
             processed)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (
                event_id,
                provider,
                event_type,
                delivery_id,
                json.dumps(payload),
            ),
        )
        cursor = await conn.execute("SELECT changes()")
        row = await cursor.fetchone()
        inserted = row[0] > 0 if row else False
        await conn.commit()
        return inserted


async def run_api_server(
    event_bus: EventBus,
    settings: Settings,
    db_manager: Optional[DatabaseManager] = None,
) -> None:
    """Run the FastAPI server using uvicorn."""
    import uvicorn

    app = create_api_app(event_bus, settings, db_manager)

    config = uvicorn.Config(
        app=app,
        host=getattr(settings, "api_server_host", "127.0.0.1"),
        port=settings.api_server_port,
        log_level="info" if not settings.debug else "debug",
    )
    server = uvicorn.Server(config)
    await server.serve()
