"""Event handlers that bridge the event bus to Claude and Telegram.

AgentHandler: translates events into ClaudeIntegration.run_command() calls.
NotificationHandler: subscribes to AgentResponseEvent and delivers to Telegram.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List

import structlog

from ..claude.facade import ClaudeIntegration
from .bus import Event, EventBus
from .types import AgentResponseEvent, ScheduledEvent, WebhookEvent

logger = structlog.get_logger()


# ---- Webhook payload formatters -------------------------------------------
#
# GitHub webhook payloads are huge — most of the volume is API URL templates
# (forks_url, keys_url, hooks_url, …) all derivable from full_name. Per-
# event formatters extract only signal fields so the agent prompt stays
# small. Each takes the raw payload dict and returns a short multi-line
# string. On any unexpected shape they may raise — _summarize_payload
# catches and falls back to the generic flattener.

_NOISE_KEY_SUFFIXES = ("_url",)
_NOISE_KEYS = {"node_id", "id", "url", "html_url", "private", "fork"}


def _short(s: Any, n: int = 7) -> str:
    return (str(s) if s else "")[:n]


def _first_line(s: Any, max_chars: int = 200) -> str:
    if not s:
        return ""
    text = str(s)
    line = text.splitlines()[0] if text.splitlines() else ""
    return line[:max_chars]


def _is_noise_key(key: str) -> bool:
    if key in _NOISE_KEYS:
        return True
    return any(key.endswith(suffix) for suffix in _NOISE_KEY_SUFFIXES)


def _fmt_push(p: Dict[str, Any]) -> str:
    repo = (p.get("repository") or {}).get("full_name") or "?"
    ref = (p.get("ref") or "").removeprefix("refs/heads/").removeprefix("refs/tags/")
    before = _short(p.get("before"))
    after = _short(p.get("after"))
    pusher = (
        (p.get("pusher") or {}).get("name")
        or (p.get("sender") or {}).get("login")
        or "?"
    )

    if before == "0000000":
        action = f"created {ref}"
    elif after == "0000000":
        action = f"deleted {ref}"
    else:
        action = f"{ref}  {before} -> {after}"

    commits = p.get("commits") or []
    n = len(commits)
    lines = [
        f"push {repo} {action}",
        f"by {pusher} ({n} commit{'' if n == 1 else 's'})",
    ]

    if commits:
        for c in commits[:5]:
            lines.append(f"  {_short(c.get('id'))} {_first_line(c.get('message'))}")
        if n > 5:
            lines.append(f"  ... +{n - 5} more")
    else:
        head_msg = _first_line((p.get("head_commit") or {}).get("message"))
        if head_msg:
            lines.append(f"  {head_msg}")

    return "\n".join(lines)


def _fmt_workflow_run(p: Dict[str, Any]) -> str:
    action = p.get("action") or "?"
    wr = p.get("workflow_run") or {}
    name = wr.get("name") or "?"
    run_n = wr.get("run_number")
    status = wr.get("status") or "?"
    conclusion = wr.get("conclusion")
    sha = _short(wr.get("head_sha"))
    branch = wr.get("head_branch") or "?"
    trigger = wr.get("event") or "?"
    title = wr.get("display_title") or ""
    url = wr.get("html_url") or ""
    repo = (p.get("repository") or {}).get("full_name") or "?"

    duration = ""
    started = wr.get("run_started_at") or wr.get("created_at")
    updated = wr.get("updated_at")
    if action == "completed" and started and updated:
        try:
            s = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
            u = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
            secs = int((u - s).total_seconds())
            duration = f"{secs}s" if secs < 60 else f"{secs // 60}m{secs % 60:02d}s"
        except Exception:
            pass

    head = f"workflow_run {action} {name}"
    if run_n is not None:
        head += f" #{run_n}"
    if conclusion:
        head += f" {conclusion}"
    elif status and action != "completed":
        head += f" {status}"

    detail = f"{repo} {sha} on {branch} via {trigger}"
    if duration:
        detail += f" ({duration})"

    lines = [head, detail]
    if title and title != name:
        lines.append(f'"{_first_line(title)}"')
    if url:
        lines.append(url)
    return "\n".join(lines)


def _fmt_ping(p: Dict[str, Any]) -> str:
    hook = p.get("hook") or {}
    org = (p.get("organization") or {}).get("login")
    repo = (p.get("repository") or {}).get("full_name")
    sender = (p.get("sender") or {}).get("login") or "?"
    scope = f"org {org}" if org else (f"repo {repo}" if repo else "?")
    hook_id = hook.get("id") or "?"
    hook_type = hook.get("type") or "?"
    events = hook.get("events") or []
    lines = [
        f"ping {scope} (hook {hook_id}, type {hook_type})",
        f"by {sender}",
    ]
    if events:
        ev_str = ", ".join(events[:10])
        if len(events) > 10:
            ev_str += f", ... +{len(events) - 10}"
        lines.append(f"events: {ev_str}")
    return "\n".join(lines)


def _fmt_pull_request(p: Dict[str, Any]) -> str:
    action = p.get("action") or "?"
    pr = p.get("pull_request") or {}
    repo = (p.get("repository") or {}).get("full_name") or "?"
    num = p.get("number") or pr.get("number") or "?"
    title = pr.get("title") or ""
    user = (pr.get("user") or {}).get("login") or "?"
    base = (pr.get("base") or {}).get("ref") or "?"
    head = (pr.get("head") or {}).get("ref") or "?"
    additions = pr.get("additions")
    deletions = pr.get("deletions")
    files = pr.get("changed_files")
    merged = pr.get("merged")

    head_line = f"pull_request {action} {repo} #{num} by {user}"
    if action == "closed" and merged:
        head_line += " (merged)"
    lines = [head_line]
    if title:
        lines.append(f'"{_first_line(title)}"')
    detail = f"{base} <- {head}"
    if additions is not None and deletions is not None:
        detail += f"  +{additions}/-{deletions}"
        if files is not None:
            detail += f" ({files} file{'' if files == 1 else 's'})"
    lines.append(detail)
    return "\n".join(lines)


def _fmt_issues(p: Dict[str, Any]) -> str:
    action = p.get("action") or "?"
    issue = p.get("issue") or {}
    repo = (p.get("repository") or {}).get("full_name") or "?"
    num = issue.get("number") or "?"
    title = issue.get("title") or ""
    user = (issue.get("user") or {}).get("login") or "?"
    labels = [lbl.get("name") for lbl in (issue.get("labels") or []) if lbl.get("name")]
    lines = [f"issues {action} {repo} #{num} by {user}"]
    if title:
        lines.append(f'"{_first_line(title)}"')
    if labels:
        lines.append(f"labels: {', '.join(labels)}")
    return "\n".join(lines)


def _fmt_issue_comment(p: Dict[str, Any]) -> str:
    action = p.get("action") or "?"
    issue = p.get("issue") or {}
    comment = p.get("comment") or {}
    repo = (p.get("repository") or {}).get("full_name") or "?"
    num = issue.get("number") or "?"
    user = (comment.get("user") or {}).get("login") or "?"
    body = _first_line(comment.get("body"))
    lines = [f"issue_comment {action} {repo} #{num} by {user}"]
    if body:
        lines.append(f'"{body}"')
    return "\n".join(lines)


def _fmt_check_run(p: Dict[str, Any]) -> str:
    action = p.get("action") or "?"
    cr = p.get("check_run") or {}
    repo = (p.get("repository") or {}).get("full_name") or "?"
    name = cr.get("name") or "?"
    status = cr.get("status") or "?"
    conclusion = cr.get("conclusion")
    sha = _short(cr.get("head_sha"))
    head = f"check_run {action} {name}"
    if conclusion:
        head += f" {conclusion}"
    elif status:
        head += f" {status}"
    return f"{head}\n{repo} @ {sha}"


def _fmt_check_suite(p: Dict[str, Any]) -> str:
    action = p.get("action") or "?"
    cs = p.get("check_suite") or {}
    repo = (p.get("repository") or {}).get("full_name") or "?"
    status = cs.get("status") or "?"
    conclusion = cs.get("conclusion")
    sha = _short(cs.get("head_sha"))
    branch = cs.get("head_branch") or "?"
    head = f"check_suite {action}"
    if conclusion:
        head += f" {conclusion}"
    elif status:
        head += f" {status}"
    return f"{head}\n{repo} {branch} @ {sha}"


_FORMATTERS: Dict[str, Callable[[Dict[str, Any]], str]] = {
    "push": _fmt_push,
    "workflow_run": _fmt_workflow_run,
    "ping": _fmt_ping,
    "pull_request": _fmt_pull_request,
    "issues": _fmt_issues,
    "issue_comment": _fmt_issue_comment,
    "check_run": _fmt_check_run,
    "check_suite": _fmt_check_suite,
}


class AgentHandler:
    """Translates incoming events into Claude agent executions.

    Webhook and scheduled events are converted into prompts and sent
    to ClaudeIntegration.run_command(). The response is published
    back as an AgentResponseEvent for delivery.
    """

    def __init__(
        self,
        event_bus: EventBus,
        claude_integration: ClaudeIntegration,
        default_working_directory: Path,
        default_user_id: int = 0,
    ) -> None:
        self.event_bus = event_bus
        self.claude = claude_integration
        self.default_working_directory = default_working_directory
        self.default_user_id = default_user_id

    def register(self) -> None:
        """Subscribe to events that need agent processing."""
        self.event_bus.subscribe(WebhookEvent, self.handle_webhook)
        self.event_bus.subscribe(ScheduledEvent, self.handle_scheduled)

    async def handle_webhook(self, event: Event) -> None:
        """Process a webhook event through Claude."""
        if not isinstance(event, WebhookEvent):
            return

        logger.info(
            "Processing webhook event through agent",
            provider=event.provider,
            event_type=event.event_type_name,
            delivery_id=event.delivery_id,
        )

        prompt = self._build_webhook_prompt(event)

        try:
            response = await self.claude.run_command(
                prompt=prompt,
                working_directory=self.default_working_directory,
                user_id=self.default_user_id,
            )

            if response.content:
                # We don't know which chat to send to from a webhook alone.
                # The notification service needs configured target chats.
                # Publish with chat_id=0 — the NotificationService
                # will broadcast to configured notification_chat_ids.
                await self.event_bus.publish(
                    AgentResponseEvent(
                        chat_id=0,
                        text=response.content,
                        originating_event_id=event.id,
                    )
                )
        except Exception:
            logger.exception(
                "Agent execution failed for webhook event",
                provider=event.provider,
                event_id=event.id,
            )

    async def handle_scheduled(self, event: Event) -> None:
        """Process a scheduled event through Claude."""
        if not isinstance(event, ScheduledEvent):
            return

        logger.info(
            "Processing scheduled event through agent",
            job_id=event.job_id,
            job_name=event.job_name,
        )

        prompt = event.prompt
        if event.skill_name:
            prompt = (
                f"/{event.skill_name}\n\n{prompt}" if prompt else f"/{event.skill_name}"
            )

        working_dir = event.working_directory or self.default_working_directory

        try:
            response = await self.claude.run_command(
                prompt=prompt,
                working_directory=working_dir,
                user_id=self.default_user_id,
            )

            if response.content:
                for chat_id in event.target_chat_ids:
                    await self.event_bus.publish(
                        AgentResponseEvent(
                            chat_id=chat_id,
                            text=response.content,
                            originating_event_id=event.id,
                        )
                    )

                # Also broadcast to default chats if no targets specified
                if not event.target_chat_ids:
                    await self.event_bus.publish(
                        AgentResponseEvent(
                            chat_id=0,
                            text=response.content,
                            originating_event_id=event.id,
                        )
                    )
        except Exception:
            logger.exception(
                "Agent execution failed for scheduled event",
                job_id=event.job_id,
                event_id=event.id,
            )

    def _build_webhook_prompt(self, event: WebhookEvent) -> str:
        """Build a Claude prompt from a webhook event."""
        payload_summary = self._summarize_payload(
            event.payload, event_type=event.event_type_name
        )

        return (
            f"A {event.provider} webhook event occurred.\n"
            f"Event type: {event.event_type_name}\n"
            f"Payload summary:\n{payload_summary}\n\n"
            f"Analyze this event and provide a concise summary. "
            f"Highlight anything that needs my attention."
        )

    def _summarize_payload(
        self,
        payload: Dict[str, Any],
        event_type: str = "",
        max_depth: int = 2,
    ) -> str:
        """Create a readable summary of a webhook payload.

        Dispatches to a per-event-type formatter that extracts only signal
        fields (commits, authors, conclusions, durations, URLs). Falls back
        to a generic flattener for unknown event types or if a formatter
        raises. The fallback skips noise keys (`*_url`, `node_id`, IDs).
        """
        formatter = _FORMATTERS.get(event_type)
        if formatter is not None:
            try:
                summary = formatter(payload)
                if summary:
                    return summary
            except Exception:
                logger.warning(
                    "payload formatter raised, falling back to flattener",
                    event_type=event_type,
                    exc_info=True,
                )

        # Generic fallback: flatten the dict, filter noise.
        lines: List[str] = []
        self._flatten_dict(payload, lines, max_depth=max_depth)
        summary = "\n".join(lines)
        if len(summary) > 2000:
            summary = summary[:2000] + "\n... (truncated)"
        return summary

    def _flatten_dict(
        self,
        data: Any,
        lines: list,
        prefix: str = "",
        depth: int = 0,
        max_depth: int = 2,
    ) -> None:
        """Flatten a nested dict into key: value lines, skipping noise keys."""
        if depth >= max_depth:
            lines.append(f"{prefix}: ...")
            return

        if isinstance(data, dict):
            for key, value in data.items():
                if _is_noise_key(key):
                    continue
                full_key = f"{prefix}.{key}" if prefix else key
                if isinstance(value, (dict, list)):
                    self._flatten_dict(value, lines, full_key, depth + 1, max_depth)
                else:
                    val_str = str(value)
                    if len(val_str) > 200:
                        val_str = val_str[:200] + "..."
                    lines.append(f"{full_key}: {val_str}")
        elif isinstance(data, list):
            lines.append(f"{prefix}: [{len(data)} items]")
            for i, item in enumerate(data[:3]):  # Show first 3 items
                self._flatten_dict(item, lines, f"{prefix}[{i}]", depth + 1, max_depth)
        else:
            lines.append(f"{prefix}: {data}")
