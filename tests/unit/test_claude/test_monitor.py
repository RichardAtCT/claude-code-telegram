"""Test Claude tool monitor — especially bash directory boundary checking."""

from pathlib import Path

import pytest

from src.claude.monitor import ToolMonitor, check_bash_directory_boundary
from src.config.settings import Settings


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

    def test_relative_paths_always_pass(self) -> None:
        valid, error = check_bash_directory_boundary(
            "mkdir -p subdir/nested", self.cwd, self.approved
        )
        assert valid
        assert error is None

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


class TestToolMonitorBashBoundary:
    """Test that validate_tool_call wires up the bash directory boundary check."""

    @pytest.fixture
    def config(self, tmp_path: Path) -> Settings:
        return Settings(
            telegram_bot_token="test:token",
            telegram_bot_username="testbot",
            approved_directory=tmp_path,
            use_sdk=True,
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
