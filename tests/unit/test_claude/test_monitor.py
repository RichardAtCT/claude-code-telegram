"""Test Claude tool monitor — especially bash directory boundary checking."""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.claude.monitor import (
    ToolMonitor,
    _is_claude_internal_path,
    check_bash_directory_boundary,
)
from src.config.settings import Settings
from src.security.validators import SecurityValidator


class TestCheckBashDirectoryBoundary:
    """Test the check_bash_directory_boundary function."""

    def setup_method(self) -> None:
        self.approved = Path("/root/projects")
        self.cwd = Path("/root/projects/myapp")

    def test_mkdir_outside_approved_directory(self) -> None:
        valid, error = check_bash_directory_boundary(
            "mkdir -p /root/web1", self.cwd, self.approved
        )
        assert not valid
        assert "directory boundary violation" in error.lower()
        assert "/root/web1" in error

    def test_mkdir_inside_approved_directory(self) -> None:
        valid, error = check_bash_directory_boundary(
            "mkdir -p /root/projects/newdir", self.cwd, self.approved
        )
        assert valid
        assert error is None

    def test_touch_outside_approved_directory(self) -> None:
        valid, error = check_bash_directory_boundary(
            "touch /tmp/evil.txt", self.cwd, self.approved
        )
        assert not valid
        assert "/tmp/evil.txt" in error

    def test_cp_outside_approved_directory(self) -> None:
        valid, error = check_bash_directory_boundary(
            "cp file.txt /etc/passwd", self.cwd, self.approved
        )
        assert not valid
        assert "/etc/passwd" in error

    def test_mv_outside_approved_directory(self) -> None:
        valid, error = check_bash_directory_boundary(
            "mv /root/projects/file.txt /tmp/file.txt", self.cwd, self.approved
        )
        assert not valid
        assert "/tmp/file.txt" in error

    def test_relative_paths_inside_approved_pass(self) -> None:
        valid, error = check_bash_directory_boundary(
            "mkdir -p subdir/nested", self.cwd, self.approved
        )
        assert valid
        assert error is None

    def test_relative_path_traversal_escaping_approved_dir(self) -> None:
        """mkdir ../../evil from /root/projects/myapp resolves to /root/evil."""
        valid, error = check_bash_directory_boundary(
            "mkdir ../../evil", self.cwd, self.approved
        )
        assert not valid
        assert "directory boundary violation" in error.lower()
        assert "../../evil" in error

    def test_relative_path_traversal_staying_inside_approved_dir(self) -> None:
        """mkdir ../sibling from /root/projects/myapp -> /root/projects/sibling (ok)."""
        valid, error = check_bash_directory_boundary(
            "mkdir ../sibling", self.cwd, self.approved
        )
        assert valid
        assert error is None

    def test_relative_path_dot_dot_at_boundary_root(self) -> None:
        """mkdir .. from approved root itself should be blocked."""
        cwd_at_root = Path("/root/projects")
        valid, error = check_bash_directory_boundary(
            "touch ../outside.txt", cwd_at_root, self.approved
        )
        assert not valid
        assert "directory boundary violation" in error.lower()

    def test_read_only_commands_pass(self) -> None:
        for cmd in ["cat /etc/hosts", "ls /tmp", "head /var/log/syslog"]:
            valid, error = check_bash_directory_boundary(cmd, self.cwd, self.approved)
            assert valid, f"Expected read-only command to pass: {cmd}"
            assert error is None

    def test_non_fs_commands_pass(self) -> None:
        """Commands not in the filesystem-modifying set pass through."""
        for cmd in ["python script.py", "node app.js", "cargo build"]:
            valid, error = check_bash_directory_boundary(cmd, self.cwd, self.approved)
            assert valid, f"Expected non-fs command to pass: {cmd}"
            assert error is None

    def test_empty_command(self) -> None:
        valid, error = check_bash_directory_boundary("", self.cwd, self.approved)
        assert valid
        assert error is None

    def test_flags_are_skipped(self) -> None:
        valid, error = check_bash_directory_boundary(
            "mkdir -p -v /root/projects/dir", self.cwd, self.approved
        )
        assert valid
        assert error is None

    def test_unparseable_command_passes_through(self) -> None:
        """Malformed quoting should pass through (sandbox catches it at OS level)."""
        valid, error = check_bash_directory_boundary(
            "mkdir 'unclosed quote", self.cwd, self.approved
        )
        assert valid
        assert error is None

    def test_rm_outside_approved_directory(self) -> None:
        valid, error = check_bash_directory_boundary(
            "rm /var/tmp/somefile", self.cwd, self.approved
        )
        assert not valid
        assert "/var/tmp/somefile" in error

    def test_ln_outside_approved_directory(self) -> None:
        valid, error = check_bash_directory_boundary(
            "ln -s /root/projects/file /tmp/link", self.cwd, self.approved
        )
        assert not valid
        assert "/tmp/link" in error

    # --- find command handling ---

    def test_find_without_mutating_flags_passes(self) -> None:
        """Plain find (read-only) should pass regardless of search path."""
        valid, error = check_bash_directory_boundary(
            "find /tmp -name '*.log'", self.cwd, self.approved
        )
        assert valid
        assert error is None

    def test_find_delete_outside_approved_dir(self) -> None:
        """find /tmp -delete should be blocked because /tmp is outside."""
        valid, error = check_bash_directory_boundary(
            "find /tmp -name '*.log' -delete", self.cwd, self.approved
        )
        assert not valid
        assert "directory boundary violation" in error.lower()
        assert "/tmp" in error

    def test_find_exec_outside_approved_dir(self) -> None:
        """find /var -exec rm {} ; should be blocked."""
        valid, error = check_bash_directory_boundary(
            "find /var -exec rm {} ;", self.cwd, self.approved
        )
        assert not valid
        assert "/var" in error

    def test_find_delete_inside_approved_dir(self) -> None:
        """find inside approved dir with -delete should pass."""
        valid, error = check_bash_directory_boundary(
            "find /root/projects/myapp -name '*.pyc' -delete",
            self.cwd,
            self.approved,
        )
        assert valid
        assert error is None

    def test_find_delete_relative_path_inside(self) -> None:
        """find . -delete from inside approved dir should pass."""
        valid, error = check_bash_directory_boundary(
            "find . -name '*.pyc' -delete", self.cwd, self.approved
        )
        assert valid
        assert error is None

    def test_find_execdir_outside_approved_dir(self) -> None:
        """find with -execdir outside approved dir should be blocked."""
        valid, error = check_bash_directory_boundary(
            "find /etc -execdir cat {} ;", self.cwd, self.approved
        )
        assert not valid
        assert "/etc" in error


class TestToolMonitorBashBoundary:
    """Test that validate_tool_call wires up the bash directory boundary check."""

    @pytest.fixture
    def config(self, tmp_path: Path) -> Settings:
        return Settings(
            telegram_bot_token="test:token",
            telegram_bot_username="testbot",
            approved_directory=tmp_path,
        )

    @pytest.fixture
    def monitor(self, config: Settings) -> ToolMonitor:
        return ToolMonitor(config)

    async def test_bash_directory_violation_recorded(
        self, monitor: ToolMonitor, tmp_path: Path
    ) -> None:
        """Bash command writing outside approved dir is caught by validate_tool_call."""
        valid, error = await monitor.validate_tool_call(
            tool_name="Bash",
            tool_input={"command": "mkdir -p /tmp/evil"},
            working_directory=tmp_path,
            user_id=123,
        )
        assert not valid
        assert "directory boundary violation" in error.lower()
        assert len(monitor.security_violations) == 1
        assert monitor.security_violations[0]["type"] == "directory_boundary_violation"

    async def test_bash_inside_approved_dir_passes(
        self, monitor: ToolMonitor, tmp_path: Path
    ) -> None:
        """Bash command within approved dir passes validation."""
        subdir = tmp_path / "subdir"
        valid, error = await monitor.validate_tool_call(
            tool_name="Bash",
            tool_input={"command": f"mkdir -p {subdir}"},
            working_directory=tmp_path,
            user_id=123,
        )
        assert valid
        assert error is None

    async def test_dangerous_pattern_still_checked_first(
        self, monitor: ToolMonitor, tmp_path: Path
    ) -> None:
        """Dangerous patterns are still caught before directory boundary check."""
        valid, error = await monitor.validate_tool_call(
            tool_name="Bash",
            tool_input={"command": "sudo mkdir /tmp/test"},
            working_directory=tmp_path,
            user_id=123,
        )
        assert not valid
        assert "dangerous command pattern" in error.lower()


class TestIsClaudeInternalPath:
    """Test the _is_claude_internal_path helper function."""

    def test_plan_file_is_internal(self, tmp_path: Path) -> None:
        """~/.claude/plans/some-plan.md should be recognised as internal."""
        with patch("src.claude.monitor.Path.home", return_value=tmp_path):
            (tmp_path / ".claude" / "plans").mkdir(parents=True)
            plan_file = tmp_path / ".claude" / "plans" / "my-plan.md"
            plan_file.touch()
            assert _is_claude_internal_path(str(plan_file)) is True

    def test_todo_file_is_internal(self, tmp_path: Path) -> None:
        """~/.claude/todos/todo.md should be recognised as internal."""
        with patch("src.claude.monitor.Path.home", return_value=tmp_path):
            (tmp_path / ".claude" / "todos").mkdir(parents=True)
            todo_file = tmp_path / ".claude" / "todos" / "todo.md"
            todo_file.touch()
            assert _is_claude_internal_path(str(todo_file)) is True

    def test_settings_json_is_internal(self, tmp_path: Path) -> None:
        """~/.claude/settings.json should be recognised as internal."""
        with patch("src.claude.monitor.Path.home", return_value=tmp_path):
            (tmp_path / ".claude").mkdir(parents=True)
            settings_file = tmp_path / ".claude" / "settings.json"
            settings_file.touch()
            assert _is_claude_internal_path(str(settings_file)) is True

    def test_arbitrary_file_under_claude_dir_rejected(self, tmp_path: Path) -> None:
        """Files directly under ~/.claude/ (not in known subdirs) are rejected."""
        with patch("src.claude.monitor.Path.home", return_value=tmp_path):
            (tmp_path / ".claude").mkdir(parents=True)
            secret = tmp_path / ".claude" / "credentials.json"
            secret.touch()
            assert _is_claude_internal_path(str(secret)) is False

    def test_path_outside_claude_dir_rejected(self, tmp_path: Path) -> None:
        """Paths outside ~/.claude/ entirely are rejected."""
        with patch("src.claude.monitor.Path.home", return_value=tmp_path):
            assert _is_claude_internal_path("/etc/passwd") is False
            assert _is_claude_internal_path("/tmp/evil.txt") is False

    def test_empty_path_rejected(self, tmp_path: Path) -> None:
        """Empty paths are rejected."""
        assert _is_claude_internal_path("") is False

    def test_unknown_subdir_rejected(self, tmp_path: Path) -> None:
        """Unknown subdirectories under ~/.claude/ are rejected."""
        with patch("src.claude.monitor.Path.home", return_value=tmp_path):
            (tmp_path / ".claude" / "secrets").mkdir(parents=True)
            bad_file = tmp_path / ".claude" / "secrets" / "key.pem"
            bad_file.touch()
            assert _is_claude_internal_path(str(bad_file)) is False


class TestToolMonitorClaudeInternalPaths:
    """Test that validate_tool_call allows Claude internal paths."""

    @pytest.fixture
    def config(self, tmp_path: Path) -> Settings:
        return Settings(
            telegram_bot_token="test:token",
            telegram_bot_username="testbot",
            approved_directory=tmp_path,
        )

    @pytest.fixture
    def security_validator(self, config: Settings) -> SecurityValidator:
        return SecurityValidator(config.approved_directory)

    @pytest.fixture
    def monitor(
        self, config: Settings, security_validator: SecurityValidator
    ) -> ToolMonitor:
        return ToolMonitor(config, security_validator=security_validator)

    async def test_read_plan_file_allowed(
        self, monitor: ToolMonitor, tmp_path: Path
    ) -> None:
        """Read tool targeting a plan file in ~/.claude/plans/ should pass."""
        with patch("src.claude.monitor.Path.home", return_value=tmp_path):
            (tmp_path / ".claude" / "plans").mkdir(parents=True)
            plan_path = str(tmp_path / ".claude" / "plans" / "my-plan.md")
            valid, error = await monitor.validate_tool_call(
                tool_name="Read",
                tool_input={"file_path": plan_path},
                working_directory=tmp_path / "project",
                user_id=123,
            )
            assert valid
            assert error is None

    async def test_write_plan_file_allowed(
        self, monitor: ToolMonitor, tmp_path: Path
    ) -> None:
        """Write tool targeting a plan file in ~/.claude/plans/ should pass."""
        with patch("src.claude.monitor.Path.home", return_value=tmp_path):
            (tmp_path / ".claude" / "plans").mkdir(parents=True)
            plan_path = str(tmp_path / ".claude" / "plans" / "new-plan.md")
            valid, error = await monitor.validate_tool_call(
                tool_name="Write",
                tool_input={"file_path": plan_path},
                working_directory=tmp_path / "project",
                user_id=123,
            )
            assert valid
            assert error is None

    async def test_edit_plan_file_allowed(
        self, monitor: ToolMonitor, tmp_path: Path
    ) -> None:
        """Edit tool targeting a plan file in ~/.claude/plans/ should pass."""
        with patch("src.claude.monitor.Path.home", return_value=tmp_path):
            (tmp_path / ".claude" / "plans").mkdir(parents=True)
            plan_path = str(tmp_path / ".claude" / "plans" / "my-plan.md")
            valid, error = await monitor.validate_tool_call(
                tool_name="Edit",
                tool_input={"file_path": plan_path},
                working_directory=tmp_path / "project",
                user_id=123,
            )
            assert valid
            assert error is None

    async def test_file_outside_both_approved_and_claude_still_blocked(
        self, monitor: ToolMonitor, tmp_path: Path
    ) -> None:
        """Files outside both approved dir and ~/.claude/ are still blocked."""
        with patch("src.claude.monitor.Path.home", return_value=tmp_path):
            valid, error = await monitor.validate_tool_call(
                tool_name="Read",
                tool_input={"file_path": "/etc/passwd"},
                working_directory=tmp_path,
                user_id=123,
            )
            assert not valid
            assert error is not None

    async def test_no_security_violations_for_claude_internal(
        self, monitor: ToolMonitor, tmp_path: Path
    ) -> None:
        """Accessing Claude internal paths should not record security violations."""
        with patch("src.claude.monitor.Path.home", return_value=tmp_path):
            (tmp_path / ".claude" / "plans").mkdir(parents=True)
            plan_path = str(tmp_path / ".claude" / "plans" / "my-plan.md")
            await monitor.validate_tool_call(
                tool_name="Read",
                tool_input={"file_path": plan_path},
                working_directory=tmp_path / "project",
                user_id=123,
            )
            assert len(monitor.security_violations) == 0
