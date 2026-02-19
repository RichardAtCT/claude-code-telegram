"""Git integration for safe repository operations."""

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set, Tuple

from src.config.settings import Settings
from src.exceptions import SecurityError

logger = logging.getLogger(__name__)


class GitError(Exception):
    """Git operation error."""


@dataclass
class GitStatus:
    """Git repository status."""

    branch: str
    modified: List[str]
    added: List[str]
    deleted: List[str]
    untracked: List[str]
    ahead: int
    behind: int

    @property
    def is_clean(self) -> bool:
        """Check if working directory is clean."""
        return not any([self.modified, self.added, self.deleted, self.untracked])


@dataclass
class CommitInfo:
    """Git commit information."""

    hash: str
    author: str
    date: datetime
    message: str
    files_changed: int
    insertions: int
    deletions: int


class GitIntegration:
    """Safe git integration for repositories."""

    # Safe git commands allowed
    SAFE_COMMANDS: Set[str] = {
        "status",
        "log",
        "diff",
        "branch",
        "remote",
        "show",
        "ls-files",
        "ls-tree",
        "rev-parse",
        "rev-list",
        "describe",
    }

    # Dangerous patterns to block
    DANGEROUS_PATTERNS = [
        r"--exec",
        r"--upload-pack",
        r"--receive-pack",
        r"-c\s*core\.gitProxy",
        r"-c\s*core\.sshCommand",
    ]

    def __init__(self, settings: Settings):
        """Initialize git integration.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self.approved_dir = Path(settings.approved_directory)

    async def execute_git_command(
        self, command: List[str], cwd: Path
    ) -> Tuple[str, str]:
        """Execute safe git command.

        Args:
            command: Git command parts
            cwd: Working directory

        Returns:
            Tuple of (stdout, stderr)

        Raises:
            SecurityError: If command is unsafe
            GitError: If git command fails
        """
        # Validate command safety
        if not command or command[0] != "git":
            raise SecurityError("Only git commands allowed")

        if len(command) < 2 or command[1] not in self.SAFE_COMMANDS:
            raise SecurityError(f"Unsafe git command: {command[1]}")

        # Check for dangerous patterns
        cmd_str = " ".join(command)
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, cmd_str, re.IGNORECASE):
                raise SecurityError(f"Dangerous pattern detected: {pattern}")

        # Validate working directory
        try:
            cwd = cwd.resolve()
            if not cwd.is_relative_to(self.approved_dir):
                raise SecurityError("Repository outside approved directory")
        except Exception:
            raise SecurityError("Invalid repository path")

        # Execute command
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                raise GitError(f"Git command failed: {stderr.decode()}")

            return stdout.decode(), stderr.decode()

        except asyncio.TimeoutError:
            raise GitError("Git command timed out")
        except Exception as e:
            logger.error(f"Git command error: {e}")
            raise GitError(f"Failed to execute git command: {e}")

    async def get_status(self, repo_path: Path) -> GitStatus:
        """Get repository status.

        Args:
            repo_path: Repository path

        Returns:
            Git status information
        """
        # Get branch and tracking info
        branch_out, _ = await self.execute_git_command(
            ["git", "branch", "--show-current"], repo_path
        )
        branch = branch_out.strip() or "HEAD"

        # Get file status
        status_out, _ = await self.execute_git_command(
            ["git", "status", "--porcelain=v1"], repo_path
        )

        modified = []
        added = []
        deleted = []
        untracked = []

        for line in status_out.strip().split("\n"):
            if not line:
                continue

            status = line[:2]
            filename = line[3:]

            if status == "??":
                untracked.append(filename)
            elif "M" in status:
                modified.append(filename)
            elif "A" in status:
                added.append(filename)
            elif "D" in status:
                deleted.append(filename)

        # Get ahead/behind counts
        ahead = behind = 0
        try:
            # Try to get upstream tracking info
            rev_out, _ = await self.execute_git_command(
                ["git", "rev-list", "--count", "--left-right", "HEAD...@{upstream}"],
                repo_path,
            )
            if rev_out.strip():
                parts = rev_out.strip().split("\t")
                if len(parts) == 2:
                    ahead = int(parts[0])
                    behind = int(parts[1])
        except GitError:
            # No upstream configured
            pass

        return GitStatus(
            branch=branch,
            modified=modified,
            added=added,
            deleted=deleted,
            untracked=untracked,
            ahead=ahead,
            behind=behind,
        )

    async def get_diff(
        self, repo_path: Path, staged: bool = False, file_path: Optional[str] = None
    ) -> str:
        """Get repository diff.

        Args:
            repo_path: Repository path
            staged: Show staged changes
            file_path: Specific file to diff

        Returns:
            Formatted diff output
        """
        command = ["git", "diff"]

        if staged:
            command.append("--staged")

        # Add formatting options
        command.extend(["--no-color", "--minimal"])

        if file_path:
            # Validate file path
            file_path_obj = (repo_path / file_path).resolve()
            if not file_path_obj.is_relative_to(repo_path):
                raise SecurityError("File path outside repository")
            command.append(file_path)

        diff_out, _ = await self.execute_git_command(command, repo_path)

        if not diff_out.strip():
            return "No changes to show"

        # Format diff with indicators
        lines = []
        for line in diff_out.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                lines.append(f"➕ {line[1:]}")
            elif line.startswith("-") and not line.startswith("---"):
                lines.append(f"➖ {line[1:]}")
            elif line.startswith("@@"):
                lines.append(f"📍 {line}")
            else:
                lines.append(line)

        return "\n".join(lines)

    async def get_file_history(
        self, repo_path: Path, file_path: str, limit: int = 10
    ) -> List[CommitInfo]:
        """Get file commit history.

        Args:
            repo_path: Repository path
            file_path: File to get history for
            limit: Maximum commits to return

        Returns:
            List of commit information
        """
        # Validate file path
        file_path_obj = (repo_path / file_path).resolve()
        if not file_path_obj.is_relative_to(repo_path):
            raise SecurityError("File path outside repository")

        # Get commit log with stats
        log_out, _ = await self.execute_git_command(
            [
                "git",
                "log",
                f"--max-count={limit}",
                "--pretty=format:%H|%an|%aI|%s",
                "--numstat",
                "--",
                file_path,
            ],
            repo_path,
        )

        commits = []
        current_commit = None

        for line in log_out.strip().split("\n"):
            if not line:
                continue

            if "|" in line and len(line.split("|")) == 4:
                # Commit info line
                parts = line.split("|")

                if current_commit:
                    commits.append(current_commit)

                current_commit = CommitInfo(
                    hash=parts[0][:8],  # Short hash
                    author=parts[1],
                    date=datetime.fromisoformat(parts[2].replace("Z", "+00:00")),
                    message=parts[3],
                    files_changed=0,
                    insertions=0,
                    deletions=0,
                )
            elif current_commit and "\t" in line:
                # Numstat line
                parts = line.split("\t")
                if len(parts) == 3:
                    try:
                        insertions = int(parts[0]) if parts[0] != "-" else 0
                        deletions = int(parts[1]) if parts[1] != "-" else 0
                        current_commit.insertions += insertions
                        current_commit.deletions += deletions
                        current_commit.files_changed += 1
                    except ValueError:
                        pass

        if current_commit:
            commits.append(current_commit)

        return commits

    def format_status(self, status: GitStatus) -> str:
        """Format git status for display.

        Args:
            status: Git status object

        Returns:
            Formatted status string
        """
        lines = [f"🌿 Branch: {status.branch}"]

        # Add tracking info
        if status.ahead or status.behind:
            tracking = []
            if status.ahead:
                tracking.append(f"↑{status.ahead}")
            if status.behind:
                tracking.append(f"↓{status.behind}")
            lines.append(f"📊 Tracking: {' '.join(tracking)}")

        if status.is_clean:
            lines.append("✅ Working tree clean")
        else:
            if status.modified:
                lines.append(f"📝 Modified: {len(status.modified)} files")
                for f in status.modified[:5]:  # Show first 5
                    lines.append(f"  • {f}")
                if len(status.modified) > 5:
                    lines.append(f"  ... and {len(status.modified) - 5} more")

            if status.added:
                lines.append(f"➕ Added: {len(status.added)} files")
                for f in status.added[:5]:
                    lines.append(f"  • {f}")
                if len(status.added) > 5:
                    lines.append(f"  ... and {len(status.added) - 5} more")

            if status.deleted:
                lines.append(f"➖ Deleted: {len(status.deleted)} files")
                for f in status.deleted[:5]:
                    lines.append(f"  • {f}")
                if len(status.deleted) > 5:
                    lines.append(f"  ... and {len(status.deleted) - 5} more")

            if status.untracked:
                lines.append(f"❓ Untracked: {len(status.untracked)} files")
                for f in status.untracked[:5]:
                    lines.append(f"  • {f}")
                if len(status.untracked) > 5:
                    lines.append(f"  ... and {len(status.untracked) - 5} more")

        return "\n".join(lines)

    def format_history(self, commits: List[CommitInfo]) -> str:
        """Format commit history for display.

        Args:
            commits: List of commits

        Returns:
            Formatted history string
        """
        if not commits:
            return "No commit history found"

        lines = ["📜 Commit History:"]

        for commit in commits:
            lines.append(
                f"\n🔹 {commit.hash} - {commit.date.strftime('%Y-%m-%d %H:%M')}"
            )
            lines.append(f"   👤 {commit.author}")
            lines.append(f"   💬 {commit.message}")

            if commit.files_changed:
                stats = []
                if commit.insertions:
                    stats.append(f"+{commit.insertions}")
                if commit.deletions:
                    stats.append(f"-{commit.deletions}")
                lines.append(
                    f"   📊 {commit.files_changed} files changed, {' '.join(stats)}"
                )

        return "\n".join(lines)
