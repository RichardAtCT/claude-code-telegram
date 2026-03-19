"""Automated code review using Claude.

Analyzes PR/MR diffs and produces structured review results
with issues grouped by severity, suggestions, and approval recommendations.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

import structlog

from ...claude.facade import ClaudeIntegration

logger = structlog.get_logger()


class Severity(str, Enum):
    """Issue severity levels."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class ApprovalRecommendation(str, Enum):
    """Review approval recommendation."""

    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    COMMENT = "comment"


@dataclass
class Issue:
    """A single issue found during code review."""

    file: str
    line: int
    severity: Severity
    message: str


@dataclass
class ReviewResult:
    """Result of a code review analysis."""

    summary: str
    issues: List[Issue] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    approval_recommendation: ApprovalRecommendation = ApprovalRecommendation.COMMENT

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.INFO)

    def format_telegram_message(self) -> str:
        """Format the review result as a Telegram HTML message."""
        parts: List[str] = []

        # Header with recommendation icon
        rec_icon = {
            ApprovalRecommendation.APPROVE: "✅",
            ApprovalRecommendation.REQUEST_CHANGES: "🔴",
            ApprovalRecommendation.COMMENT: "💬",
        }
        icon = rec_icon.get(self.approval_recommendation, "💬")
        rec_label = self.approval_recommendation.value.replace("_", " ").title()
        parts.append(f"<b>{icon} Code Review — {rec_label}</b>\n")

        # Summary
        parts.append(f"<b>Summary:</b>\n{_escape_html(self.summary)}\n")

        # Issues grouped by severity
        if self.issues:
            parts.append(f"<b>Issues ({len(self.issues)}):</b>")

            for severity in (Severity.CRITICAL, Severity.WARNING, Severity.INFO):
                group = [i for i in self.issues if i.severity == severity]
                if not group:
                    continue

                sev_icon = {
                    Severity.CRITICAL: "🔴",
                    Severity.WARNING: "⚠️",
                    Severity.INFO: "ℹ️",
                }
                parts.append(
                    f"\n{sev_icon[severity]} <b>{severity.value.upper()}</b>"
                )
                for issue in group:
                    loc = f"{issue.file}"
                    if issue.line > 0:
                        loc += f":{issue.line}"
                    parts.append(
                        f"  • <code>{_escape_html(loc)}</code> "
                        f"— {_escape_html(issue.message)}"
                    )

        # Suggestions
        if self.suggestions:
            parts.append(f"\n<b>Suggestions:</b>")
            for suggestion in self.suggestions:
                parts.append(f"  • {_escape_html(suggestion)}")

        return "\n".join(parts)


def _escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# The review prompt template sent to Claude
_REVIEW_PROMPT = """\
You are an expert code reviewer. Analyze the following pull request diff and \
provide a structured review.

PR Title: {pr_title}
PR Description: {pr_description}

{diff_section}

Respond in EXACTLY this format (use these exact headers):

SUMMARY:
<1-3 sentence summary of what this PR does and your overall assessment>

ISSUES:
<one issue per line in format: FILE:LINE|SEVERITY|MESSAGE>
<SEVERITY must be one of: critical, warning, info>
<LINE should be a number, use 0 if not applicable>
<leave blank if no issues>

SUGGESTIONS:
<one suggestion per line, prefixed with "- ">
<leave blank if no suggestions>

RECOMMENDATION:
<exactly one of: approve, request_changes, comment>
"""


class CodeReviewManager:
    """Manages code review using Claude."""

    def __init__(self, claude_integration: ClaudeIntegration) -> None:
        self.claude = claude_integration

    async def review_pr(
        self,
        repo_path: Path,
        pr_diff: Optional[str] = None,
        pr_title: str = "",
        pr_description: str = "",
    ) -> ReviewResult:
        """Review a pull request diff using Claude.

        Args:
            repo_path: Working directory for the review session.
            pr_diff: The diff content. If None, a generic review is performed.
            pr_title: Pull request title.
            pr_description: Pull request description.

        Returns:
            Structured ReviewResult.
        """
        if pr_diff:
            # Cap diff at 15000 chars to stay within reasonable prompt size
            if len(pr_diff) > 15000:
                pr_diff = pr_diff[:15000] + "\n... (diff truncated)"
            diff_section = f"Diff:\n```\n{pr_diff}\n```"
        else:
            diff_section = (
                "(No diff provided — review based on title and description only)"
            )

        prompt = _REVIEW_PROMPT.format(
            pr_title=pr_title,
            pr_description=pr_description or "(none)",
            diff_section=diff_section,
        )

        logger.info(
            "Running code review",
            pr_title=pr_title,
            diff_length=len(pr_diff) if pr_diff else 0,
        )

        response = await self.claude.run_command(
            prompt=prompt,
            working_directory=repo_path,
            user_id=0,
        )

        return self._parse_review_response(response.content or "")

    def _parse_review_response(self, text: str) -> ReviewResult:
        """Parse Claude's structured review response into a ReviewResult."""
        summary = ""
        issues: List[Issue] = []
        suggestions: List[str] = []
        recommendation = ApprovalRecommendation.COMMENT

        current_section = ""

        for line in text.splitlines():
            stripped = line.strip()

            # Detect section headers
            if stripped.startswith("SUMMARY:"):
                current_section = "summary"
                # Handle inline content after header
                inline = stripped[len("SUMMARY:"):].strip()
                if inline:
                    summary = inline
                continue
            elif stripped.startswith("ISSUES:"):
                current_section = "issues"
                continue
            elif stripped.startswith("SUGGESTIONS:"):
                current_section = "suggestions"
                continue
            elif stripped.startswith("RECOMMENDATION:"):
                current_section = "recommendation"
                inline = stripped[len("RECOMMENDATION:"):].strip().lower()
                if inline:
                    recommendation = self._parse_recommendation(inline)
                continue

            if not stripped:
                continue

            if current_section == "summary":
                summary = f"{summary} {stripped}".strip() if summary else stripped

            elif current_section == "issues":
                issue = self._parse_issue_line(stripped)
                if issue:
                    issues.append(issue)

            elif current_section == "suggestions":
                suggestion = stripped.lstrip("- ").strip()
                if suggestion:
                    suggestions.append(suggestion)

            elif current_section == "recommendation":
                recommendation = self._parse_recommendation(stripped)

        return ReviewResult(
            summary=summary or "No summary provided.",
            issues=issues,
            suggestions=suggestions,
            approval_recommendation=recommendation,
        )

    @staticmethod
    def _parse_issue_line(line: str) -> Optional[Issue]:
        """Parse a single issue line: FILE:LINE|SEVERITY|MESSAGE."""
        parts = line.split("|", 2)
        if len(parts) < 3:
            return None

        file_line = parts[0].strip()
        severity_str = parts[1].strip().lower()
        message = parts[2].strip()

        # Split file:line
        if ":" in file_line:
            file_part, line_part = file_line.rsplit(":", 1)
            try:
                line_num = int(line_part)
            except ValueError:
                file_part = file_line
                line_num = 0
        else:
            file_part = file_line
            line_num = 0

        try:
            severity = Severity(severity_str)
        except ValueError:
            severity = Severity.INFO

        return Issue(
            file=file_part,
            line=line_num,
            severity=severity,
            message=message,
        )

    @staticmethod
    def _parse_recommendation(text: str) -> ApprovalRecommendation:
        """Parse recommendation text into enum."""
        text = text.strip().lower()
        if "approve" in text and "request" not in text:
            return ApprovalRecommendation.APPROVE
        if "request" in text or "changes" in text:
            return ApprovalRecommendation.REQUEST_CHANGES
        return ApprovalRecommendation.COMMENT
