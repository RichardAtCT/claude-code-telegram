"""Test bash directory boundary checking."""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.claude.monitor import (
    _is_claude_internal_path,
    check_bash_directory_boundary,
)


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

    # --- cd and command chaining handling ---

    def test_cd_outside_approved_directory(self) -> None:
        """cd to an outside directory should be blocked."""
        valid, error = check_bash_directory_boundary("cd /tmp", self.cwd, self.approved)
        assert not valid
        assert "directory boundary violation" in error.lower()
        assert "/tmp" in error

    def test_cd_inside_approved_directory(self) -> None:
        """cd to an inside directory should pass."""
        valid, error = check_bash_directory_boundary(
            "cd subdir", self.cwd, self.approved
        )
        assert valid
        assert error is None

    def test_chained_commands_outside_blocked(self) -> None:
        """Any command in a chain targeting outside should be blocked."""
        # Chained with &&
        valid, error = check_bash_directory_boundary(
            "ls && rm /etc/passwd", self.cwd, self.approved
        )
        assert not valid
        assert "/etc/passwd" in error

        # Chained with ;
        valid, error = check_bash_directory_boundary(
            "mkdir newdir; mv file.txt /tmp/", self.cwd, self.approved
        )
        assert not valid
        assert "/tmp/" in error

    def test_chained_commands_inside_pass(self) -> None:
        """Chain of valid commands should pass."""
        valid, error = check_bash_directory_boundary(
            "cd subdir && touch file.txt && ls -la", self.cwd, self.approved
        )
        assert valid
        assert error is None

    def test_chained_cd_outside_blocked(self) -> None:
        """cd /tmp && something should be blocked."""
        valid, error = check_bash_directory_boundary(
            "cd /tmp && ls", self.cwd, self.approved
        )
        assert not valid
        assert "/tmp" in error


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
