"""Session export functionality for exporting chat history in various formats."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from src.storage.facade import Storage
from src.utils.constants import MAX_SESSION_LENGTH


class ExportFormat(Enum):
    """Supported export formats."""

    MARKDOWN = "markdown"
    JSON = "json"
    HTML = "html"


@dataclass
class ExportedSession:
    """Exported session data."""

    format: ExportFormat
    content: str
    filename: str
    mime_type: str
    size_bytes: int
    created_at: datetime


class SessionExporter:
    """Handles exporting chat sessions in various formats."""

    def __init__(self, storage: Storage):
        """Initialize exporter with storage dependency.

        Args:
            storage: Storage facade for session data access
        """
        self.storage = storage

    async def export_session(
        self,
        user_id: int,
        session_id: str,
        format: ExportFormat = ExportFormat.MARKDOWN,
    ) -> ExportedSession:
        """Export a session in the specified format.

        Args:
            user_id: User ID
            session_id: Session ID to export
            format: Export format (markdown, json, html)

        Returns:
            ExportedSession with exported content

        Raises:
            ValueError: If session not found or invalid format
        """
        # Get session data
        session = await self.storage.get_session(user_id, session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Get session messages
        messages = await self.storage.get_session_messages(
            session_id, limit=MAX_SESSION_LENGTH
        )

        # Export based on format
        if format == ExportFormat.MARKDOWN:
            content = await self._export_markdown(session, messages)
            mime_type = "text/markdown"
            extension = "md"
        elif format == ExportFormat.JSON:
            content = await self._export_json(session, messages)
            mime_type = "application/json"
            extension = "json"
        elif format == ExportFormat.HTML:
            content = await self._export_html(session, messages)
            mime_type = "text/html"
            extension = "html"
        else:
            raise ValueError(f"Unsupported export format: {format}")

        # Create filename
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"session_{session_id[:8]}_{timestamp}.{extension}"

        return ExportedSession(
            format=format,
            content=content,
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(content.encode()),
            created_at=datetime.now(UTC),
        )

    async def _export_markdown(self, session: dict, messages: list) -> str:
        """Export session as Markdown.

        Args:
            session: Session metadata
            messages: List of messages

        Returns:
            Markdown formatted content
        """
        lines = []

        # Header
        lines.append("# Claude Code Session Export")
        lines.append(f"\n**Session ID:** `{session['id']}`")
        lines.append(f"**Created:** {session['created_at']}")
        if session.get("updated_at"):
            lines.append(f"**Last Updated:** {session['updated_at']}")
        lines.append(f"**Message Count:** {len(messages)}")
        lines.append("\n---\n")

        # Messages
        for msg in messages:
            timestamp = msg["created_at"]
            role = "You" if msg["role"] == "user" else "Claude"
            content = msg["content"]

            lines.append(f"### {role} - {timestamp}")
            lines.append(f"\n{content}\n")
            lines.append("---\n")

        return "\n".join(lines)

    async def _export_json(self, session: dict, messages: list) -> str:
        """Export session as JSON.

        Args:
            session: Session metadata
            messages: List of messages

        Returns:
            JSON formatted content
        """
        export_data = {
            "session": {
                "id": session["id"],
                "user_id": session["user_id"],
                "created_at": session["created_at"].isoformat(),
                "updated_at": (
                    session.get("updated_at", "").isoformat()
                    if session.get("updated_at")
                    else None
                ),
                "message_count": len(messages),
            },
            "messages": [
                {
                    "id": msg["id"],
                    "role": msg["role"],
                    "content": msg["content"],
                    "created_at": msg["created_at"].isoformat(),
                }
                for msg in messages
            ],
        }

        return json.dumps(export_data, indent=2, ensure_ascii=False)

    async def _export_html(self, session: dict, messages: list) -> str:
        """Export session as HTML.

        Args:
            session: Session metadata
            messages: List of messages

        Returns:
            HTML formatted content
        """
        # Convert markdown content to HTML-safe format
        markdown_content = await self._export_markdown(session, messages)
        html_content = self._markdown_to_html(markdown_content)

        # HTML template
        template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Claude Code Session - {session['id'][:8]}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h3 {{
            color: #34495e;
            margin-top: 20px;
        }}
        code {{
            background-color: #f8f8f8;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
        }}
        pre {{
            background-color: #f8f8f8;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
            border: 1px solid #e1e4e8;
        }}
        .metadata {{
            background-color: #f0f7ff;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}
        .message {{
            margin: 20px 0;
            padding: 15px;
            border-left: 4px solid #3498db;
            background-color: #f9f9f9;
        }}
        .message.claude {{
            border-left-color: #2ecc71;
        }}
        .timestamp {{
            color: #7f8c8d;
            font-size: 0.9em;
        }}
        hr {{
            border: none;
            border-top: 1px solid #e1e4e8;
            margin: 30px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        {html_content}
    </div>
</body>
</html>"""

        return template

    def _markdown_to_html(self, markdown: str) -> str:
        """Convert markdown to HTML.

        Simple conversion for basic markdown elements.

        Args:
            markdown: Markdown content

        Returns:
            HTML content
        """
        html = markdown

        # Headers
        html = html.replace("# ", "<h1>").replace("\n\n", "</h1>\n\n", 1)
        html = html.replace("### ", "<h3>").replace("\n", "</h3>\n", 3)

        # Bold
        import re

        html = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", html)

        # Code blocks
        html = re.sub(r"`([^`]+)`", r"<code>\1</code>", html)

        # Line breaks and paragraphs
        html = html.replace("\n\n", "</p>\n<p>")
        html = f"<p>{html}</p>"

        # Clean up empty paragraphs
        html = html.replace("<p></p>", "")
        html = html.replace("<p><h", "<h")
        html = html.replace("</h1></p>", "</h1>")
        html = html.replace("</h3></p>", "</h3>")

        # Horizontal rules
        html = html.replace("<p>---</p>", "<hr>")

        return html
