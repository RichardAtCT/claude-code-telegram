"""FastAPI webhook server + dashboard API.

Runs in the same process as the bot, sharing the event loop.
Receives external webhooks and publishes them as events on the bus.
Serves a real-time dashboard for monitoring all Claude activity.
"""

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ..config.settings import Settings
from ..events.bus import EventBus
from ..events.types import WebhookEvent
from ..storage.database import DatabaseManager
from ..storage.facade import Storage
from .auth import verify_github_signature, verify_shared_secret

logger = structlog.get_logger()


def create_api_app(
    event_bus: EventBus,
    settings: Settings,
    db_manager: Optional[DatabaseManager] = None,
    storage: Optional[Storage] = None,
) -> FastAPI:
    """Create the FastAPI application."""

    app = FastAPI(
        title="Claude Code Telegram - Dashboard & API",
        version="0.2.0",
        docs_url="/docs" if settings.development_mode else None,
        redoc_url=None,
    )

    # Serve static dashboard files
    dashboard_dir = Path(__file__).parent / "dashboard"
    if dashboard_dir.exists():
        app.mount("/static", StaticFiles(directory=str(dashboard_dir)), name="static")

    @app.get("/health")
    async def health_check() -> Dict[str, str]:
        return {"status": "ok"}

    # ── Dashboard HTML ───────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    async def dashboard_page() -> HTMLResponse:
        """Serve the main dashboard page."""
        html_path = Path(__file__).parent / "dashboard" / "index.html"
        if html_path.exists():
            return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
        return HTMLResponse(
            content="<h1>Dashboard not found. Run the setup.</h1>",
            status_code=404,
        )

    # ── Dashboard API endpoints ──────────────────────────────────
    @app.get("/api/dashboard")
    async def get_dashboard() -> Dict[str, Any]:
        """Full admin dashboard data."""
        if not storage:
            raise HTTPException(status_code=503, detail="Storage not available")
        return await storage.get_admin_dashboard()

    @app.get("/api/dashboard/user/{user_id}")
    async def get_user_dashboard(user_id: int) -> Dict[str, Any]:
        """User-specific dashboard data."""
        if not storage:
            raise HTTPException(status_code=503, detail="Storage not available")
        data = await storage.get_user_dashboard(user_id)
        if not data:
            raise HTTPException(status_code=404, detail="User not found")
        return data

    @app.get("/api/sessions")
    async def list_sessions(user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """List sessions, optionally filtered by user."""
        if not storage:
            raise HTTPException(status_code=503, detail="Storage not available")
        if user_id:
            sessions = await storage.sessions.get_user_sessions(
                user_id, active_only=False
            )
        else:
            # Get all users and their sessions
            users = await storage.users.get_all_users()
            sessions = []
            for u in users:
                user_sessions = await storage.sessions.get_user_sessions(
                    u.user_id, active_only=False
                )
                sessions.extend(user_sessions)
        return [s.to_dict() for s in sessions]

    @app.get("/api/sessions/{session_id}")
    async def get_session_detail(session_id: str) -> Dict[str, Any]:
        """Detailed session history with messages and tools."""
        if not storage:
            raise HTTPException(status_code=503, detail="Storage not available")
        data = await storage.get_session_history(session_id)
        if not data:
            raise HTTPException(status_code=404, detail="Session not found")
        return data

    @app.get("/api/messages/recent")
    async def get_recent_messages(hours: int = 24) -> List[Dict[str, Any]]:
        """Recent messages across all users."""
        if not storage:
            raise HTTPException(status_code=503, detail="Storage not available")
        messages = await storage.messages.get_recent_messages(hours)
        return [m.to_dict() for m in messages]

    @app.get("/api/tools/stats")
    async def get_tool_stats() -> List[Dict[str, Any]]:
        """Tool usage statistics."""
        if not storage:
            raise HTTPException(status_code=503, detail="Storage not available")
        return await storage.tools.get_tool_stats()

    @app.get("/api/audit")
    async def get_audit_log(hours: int = 24) -> List[Dict[str, Any]]:
        """Recent audit log entries."""
        if not storage:
            raise HTTPException(status_code=503, detail="Storage not available")
        entries = await storage.audit.get_recent_audit_log(hours)
        return [e.to_dict() for e in entries]

    @app.get("/api/costs")
    async def get_costs(days: int = 30) -> List[Dict[str, Any]]:
        """Cost tracking data."""
        if not storage:
            raise HTTPException(status_code=503, detail="Storage not available")
        return await storage.costs.get_total_costs(days)

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
            # Generic provider — require auth (fail-closed)
            secret = settings.webhook_api_secret
            if not secret:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Webhook API secret not configured. "
                        "Set WEBHOOK_API_SECRET to accept "
                        "webhooks from this provider."
                    ),
                )
            if not verify_shared_secret(authorization, secret):
                raise HTTPException(status_code=401, detail="Invalid authorization")
            event_type_name = request.headers.get("X-Event-Type", "unknown")
            delivery_id = request.headers.get("X-Delivery-ID", str(uuid.uuid4()))

        # Parse JSON payload
        try:
            payload: Dict[str, Any] = await request.json()
        except Exception:
            payload = {"raw_body": body.decode("utf-8", errors="replace")[:5000]}

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
    storage: Optional[Storage] = None,
) -> None:
    """Run the FastAPI server using uvicorn."""
    import uvicorn

    app = create_api_app(event_bus, settings, db_manager, storage)

    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=settings.api_server_port,
        log_level="info" if not settings.debug else "debug",
    )
    server = uvicorn.Server(config)
    await server.serve()
