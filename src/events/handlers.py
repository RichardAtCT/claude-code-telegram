"""Event handlers that bridge the event bus to Claude and Telegram.

AgentHandler: translates events into ClaudeIntegration.run_command() calls.
NotificationHandler: subscribes to AgentResponseEvent and delivers to Telegram.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from ..claude.facade import ClaudeIntegration
from ..config.settings import Settings
from .bus import Event, EventBus
from .types import AgentResponseEvent, ScheduledEvent, WebhookEvent

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Prompt templates for GitLab events
# ---------------------------------------------------------------------------

_GITLAB_TEMPLATES: Dict[str, str] = {
    "Merge Request Hook": (
        "A GitLab merge request event occurred.\n"
        "Action: {action}\n"
        "Title: {title}\n"
        "Author: {author}\n"
        "Source branch: {source_branch} -> Target branch: {target_branch}\n"
        "URL: {url}\n\n"
        "Description:\n{description}\n\n"
        "Analyze this merge request and provide a concise summary. "
        "Highlight anything that needs attention."
    ),
    "Push Hook": (
        "A GitLab push event occurred.\n"
        "Ref: {ref}\n"
        "User: {user_name}\n"
        "Commits: {commit_count}\n"
        "Project: {project_name}\n\n"
        "Recent commits:\n{commits_summary}\n\n"
        "Summarize the changes pushed."
    ),
    "Pipeline Hook": (
        "A GitLab pipeline event occurred.\n"
        "Status: {status}\n"
        "Ref: {ref}\n"
        "Project: {project_name}\n"
        "Pipeline ID: {pipeline_id}\n"
        "URL: {pipeline_url}\n\n"
        "Stages:\n{stages_summary}\n\n"
        "Analyze this pipeline result. If it failed, highlight the failure details."
    ),
}

# ---------------------------------------------------------------------------
# Prompt templates for Bitbucket events
# ---------------------------------------------------------------------------

_BITBUCKET_TEMPLATES: Dict[str, str] = {
    "pullrequest:created": (
        "A Bitbucket pull request was created.\n"
        "Title: {title}\n"
        "Author: {author}\n"
        "Source: {source_branch} -> Destination: {dest_branch}\n"
        "URL: {url}\n\n"
        "Description:\n{description}\n\n"
        "Analyze this pull request and provide a concise summary."
    ),
    "pullrequest:updated": (
        "A Bitbucket pull request was updated.\n"
        "Title: {title}\n"
        "Author: {author}\n"
        "Source: {source_branch} -> Destination: {dest_branch}\n"
        "URL: {url}\n\n"
        "Analyze the update and highlight any notable changes."
    ),
    "repo:push": (
        "A Bitbucket push event occurred.\n"
        "Repository: {repo_name}\n"
        "Actor: {actor}\n"
        "Changes:\n{changes_summary}\n\n"
        "Summarize the changes pushed."
    ),
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
        settings: Optional[Settings] = None,
    ) -> None:
        self.event_bus = event_bus
        self.claude = claude_integration
        self.default_working_directory = default_working_directory
        self.default_user_id = default_user_id
        self.settings = settings
        self._code_review_manager: Optional[Any] = None

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

        # Check if this is a PR/MR event eligible for auto code review
        if await self._try_auto_code_review(event):
            return

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

    async def _try_auto_code_review(self, event: WebhookEvent) -> bool:
        """Attempt auto code review for PR/MR webhook events.

        Returns True if auto-review was triggered (caller should skip
        normal prompt handling), False otherwise.
        """
        if not self.settings:
            return False
        if not (self.settings.enable_code_review and self.settings.code_review_auto):
            return False

        # Detect PR/MR events across providers
        is_pr_event = False
        pr_diff: Optional[str] = None
        pr_title = ""
        pr_description = ""

        if event.provider == "github" and event.event_type_name == "pull_request":
            action = event.payload.get("action", "")
            if action in ("opened", "synchronize"):
                is_pr_event = True
                pr = event.payload.get("pull_request", {})
                pr_title = pr.get("title", "")
                pr_description = pr.get("body", "") or ""

        elif event.provider == "gitlab" and event.event_type_name in (
            "Merge Request Hook",
            "merge_request",
        ):
            attrs = event.payload.get("object_attributes", {})
            action = attrs.get("action", "")
            if action in ("open", "update"):
                is_pr_event = True
                pr_title = attrs.get("title", "")
                pr_description = attrs.get("description", "") or ""

        elif event.provider == "bitbucket" and event.event_type_name in (
            "pullrequest:created",
            "pullrequest:updated",
        ):
            is_pr_event = True
            pr = event.payload.get("pullrequest", {})
            pr_title = pr.get("title", "")
            pr_description = pr.get("description", "") or ""

        if not is_pr_event:
            return False

        logger.info(
            "Auto code review triggered for PR/MR webhook",
            provider=event.provider,
            pr_title=pr_title,
        )

        try:
            from ..bot.features.code_review import CodeReviewManager

            if self._code_review_manager is None:
                self._code_review_manager = CodeReviewManager(self.claude)

            result = await self._code_review_manager.review_pr(
                repo_path=self.default_working_directory,
                pr_diff=pr_diff,
                pr_title=pr_title,
                pr_description=pr_description,
            )

            formatted = result.format_telegram_message()
            await self.event_bus.publish(
                AgentResponseEvent(
                    chat_id=0,
                    text=formatted,
                    originating_event_id=event.id,
                )
            )
            return True

        except Exception:
            logger.exception(
                "Auto code review failed, falling back to normal handling",
                provider=event.provider,
            )
            return False

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
        # Try provider-specific templates first
        if event.provider == "gitlab":
            prompt = self._build_gitlab_prompt(event)
            if prompt:
                return prompt

        if event.provider == "bitbucket":
            prompt = self._build_bitbucket_prompt(event)
            if prompt:
                return prompt

        # Fallback to generic prompt
        payload_summary = self._summarize_payload(event.payload)

        return (
            f"A {event.provider} webhook event occurred.\n"
            f"Event type: {event.event_type_name}\n"
            f"Payload summary:\n{payload_summary}\n\n"
            f"Analyze this event and provide a concise summary. "
            f"Highlight anything that needs my attention."
        )

    def _build_gitlab_prompt(self, event: WebhookEvent) -> Optional[str]:
        """Build a prompt from a GitLab webhook event."""
        template = _GITLAB_TEMPLATES.get(event.event_type_name)
        if not template:
            return None

        payload = event.payload
        if event.event_type_name == "Merge Request Hook":
            attrs = payload.get("object_attributes", {})
            return template.format(
                action=attrs.get("action", "unknown"),
                title=attrs.get("title", ""),
                author=payload.get("user", {}).get("name", "unknown"),
                source_branch=attrs.get("source_branch", ""),
                target_branch=attrs.get("target_branch", ""),
                url=attrs.get("url", ""),
                description=attrs.get("description", "") or "(none)",
            )
        elif event.event_type_name == "Push Hook":
            commits = payload.get("commits", [])
            commits_summary = "\n".join(
                f"  - {c.get('message', '').splitlines()[0]}"
                for c in commits[:5]
            ) or "(no commits)"
            return template.format(
                ref=payload.get("ref", ""),
                user_name=payload.get("user_name", "unknown"),
                commit_count=payload.get("total_commits_count", len(commits)),
                project_name=payload.get("project", {}).get("name", ""),
                commits_summary=commits_summary,
            )
        elif event.event_type_name == "Pipeline Hook":
            attrs = payload.get("object_attributes", {})
            builds = payload.get("builds", [])
            stages_summary = "\n".join(
                f"  - {b.get('stage', '?')}: {b.get('status', '?')}"
                for b in builds[:10]
            ) or "(no stage details)"
            return template.format(
                status=attrs.get("status", "unknown"),
                ref=attrs.get("ref", ""),
                project_name=payload.get("project", {}).get("name", ""),
                pipeline_id=attrs.get("id", ""),
                pipeline_url=attrs.get("url", ""),
                stages_summary=stages_summary,
            )
        return None

    def _build_bitbucket_prompt(self, event: WebhookEvent) -> Optional[str]:
        """Build a prompt from a Bitbucket webhook event."""
        template = _BITBUCKET_TEMPLATES.get(event.event_type_name)
        if not template:
            return None

        payload = event.payload
        if event.event_type_name in (
            "pullrequest:created",
            "pullrequest:updated",
        ):
            pr = payload.get("pullrequest", {})
            return template.format(
                title=pr.get("title", ""),
                author=pr.get("author", {}).get("display_name", "unknown"),
                source_branch=pr.get("source", {})
                .get("branch", {})
                .get("name", ""),
                dest_branch=pr.get("destination", {})
                .get("branch", {})
                .get("name", ""),
                url=pr.get("links", {}).get("html", {}).get("href", ""),
                description=pr.get("description", "") or "(none)",
            )
        elif event.event_type_name == "repo:push":
            changes = payload.get("push", {}).get("changes", [])
            changes_summary = "\n".join(
                f"  - {c.get('new', {}).get('name', '?')}: "
                f"{c.get('new', {}).get('type', '?')}"
                for c in changes[:5]
            ) or "(no change details)"
            return template.format(
                repo_name=payload.get("repository", {}).get("full_name", ""),
                actor=payload.get("actor", {}).get("display_name", "unknown"),
                changes_summary=changes_summary,
            )
        return None

    def _summarize_payload(self, payload: Dict[str, Any], max_depth: int = 2) -> str:
        """Create a readable summary of a webhook payload."""
        lines: List[str] = []
        self._flatten_dict(payload, lines, max_depth=max_depth)
        # Cap at 2000 chars to keep prompt reasonable
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
        """Flatten a nested dict into key: value lines."""
        if depth >= max_depth:
            lines.append(f"{prefix}: ...")
            return

        if isinstance(data, dict):
            for key, value in data.items():
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
