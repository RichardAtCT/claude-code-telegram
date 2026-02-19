"""Tests for git worktree manager."""

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.claude.worktree import WorktreeError, WorktreeManager
from src.config.settings import Settings


def _make_settings(tmp_path: Path, **overrides) -> Settings:
    """Create minimal Settings for worktree testing."""
    defaults = dict(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(tmp_path),
        enable_worktrees=True,
        worktree_base_dir=str(tmp_path / ".worktrees"),
        worktree_branch_prefix="session",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _init_git_repo(path: Path) -> None:
    """Initialise a bare-bones git repo with one commit."""
    env = {
        "HOME": str(path),  # Isolate from global git config
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "PATH": subprocess.os.environ.get("PATH", "/usr/bin"),
    }
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True, env=env)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(path),
        check=True,
        capture_output=True,
        env=env,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(path),
        check=True,
        capture_output=True,
        env=env,
    )
    # Disable GPG signing for test commits
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"],
        cwd=str(path),
        check=True,
        capture_output=True,
        env=env,
    )
    # Create an initial commit so branches can be created
    (path / "README.md").write_text("# test repo\n")
    subprocess.run(
        ["git", "add", "."], cwd=str(path), check=True, capture_output=True, env=env
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(path),
        check=True,
        capture_output=True,
        env=env,
    )


# ------------------------------------------------------------------
# Unit tests (mocked git)
# ------------------------------------------------------------------


class TestWorktreeManagerUnit:
    """Unit tests using mocked git commands."""

    def test_worktree_path_for(self, tmp_path: Path) -> None:
        cfg = _make_settings(tmp_path)
        mgr = WorktreeManager(cfg)

        result = mgr.worktree_path_for("abc-123")
        assert result == tmp_path / ".worktrees" / "abc-123"

    def test_worktree_path_sanitises_slashes(self, tmp_path: Path) -> None:
        cfg = _make_settings(tmp_path)
        mgr = WorktreeManager(cfg)

        result = mgr.worktree_path_for("a/../b")
        assert ".." not in result.name

    def test_branch_name_for(self, tmp_path: Path) -> None:
        cfg = _make_settings(tmp_path)
        mgr = WorktreeManager(cfg)

        assert mgr.branch_name_for("sess-1") == "session/sess-1"

    def test_default_base_dir(self, tmp_path: Path) -> None:
        cfg = _make_settings(tmp_path, worktree_base_dir=None)
        mgr = WorktreeManager(cfg)
        assert mgr.base_dir == tmp_path / ".worktrees"

    @pytest.mark.asyncio
    async def test_is_git_repo_true(self, tmp_path: Path) -> None:
        cfg = _make_settings(tmp_path)
        mgr = WorktreeManager(cfg)

        with patch.object(mgr, "_run_git", new_callable=AsyncMock) as mock_git:
            mock_git.return_value = ".git"
            assert await mgr.is_git_repo(tmp_path) is True
            mock_git.assert_called_once_with("rev-parse", "--git-dir", cwd=tmp_path)

    @pytest.mark.asyncio
    async def test_is_git_repo_false(self, tmp_path: Path) -> None:
        cfg = _make_settings(tmp_path)
        mgr = WorktreeManager(cfg)

        with patch.object(mgr, "_run_git", new_callable=AsyncMock) as mock_git:
            mock_git.side_effect = WorktreeError("not a repo")
            assert await mgr.is_git_repo(tmp_path) is False

    @pytest.mark.asyncio
    async def test_get_worktree_returns_none_when_missing(self, tmp_path: Path) -> None:
        cfg = _make_settings(tmp_path)
        mgr = WorktreeManager(cfg)

        result = await mgr.get_worktree("nonexistent-session")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_worktree_returns_path_when_exists(self, tmp_path: Path) -> None:
        cfg = _make_settings(tmp_path)
        mgr = WorktreeManager(cfg)

        # Create the directory so it looks like a worktree
        wt_dir = tmp_path / ".worktrees" / "my-session"
        wt_dir.mkdir(parents=True)

        result = await mgr.get_worktree("my-session")
        assert result == wt_dir

    @pytest.mark.asyncio
    async def test_count_user_worktrees(self, tmp_path: Path) -> None:
        cfg = _make_settings(tmp_path)
        mgr = WorktreeManager(cfg)

        # Create two worktree directories
        (tmp_path / ".worktrees" / "s1").mkdir(parents=True)
        (tmp_path / ".worktrees" / "s2").mkdir(parents=True)

        count = await mgr.count_user_worktrees(tmp_path, {"s1", "s2", "s3"})
        assert count == 2


# ------------------------------------------------------------------
# Integration tests (real git)
# ------------------------------------------------------------------


class TestWorktreeManagerIntegration:
    """Integration tests using real git repos."""

    @pytest.mark.asyncio
    async def test_create_and_remove_worktree(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)

        cfg = _make_settings(tmp_path, approved_directory=str(repo))
        mgr = WorktreeManager(cfg)

        # Create worktree
        wt_path = await mgr.create_worktree(repo, "test-session-1")
        assert wt_path.exists()
        assert (wt_path / "README.md").exists()

        # Idempotent: creating again returns same path
        wt_path_2 = await mgr.create_worktree(repo, "test-session-1")
        assert wt_path_2 == wt_path

        # Remove worktree
        await mgr.remove_worktree(repo, "test-session-1")
        assert not wt_path.exists()

    @pytest.mark.asyncio
    async def test_get_or_create_worktree(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)

        cfg = _make_settings(tmp_path, approved_directory=str(repo))
        mgr = WorktreeManager(cfg)

        # First call creates
        wt = await mgr.get_or_create_worktree(repo, "sess-a")
        assert wt.exists()

        # Second call reuses
        wt2 = await mgr.get_or_create_worktree(repo, "sess-a")
        assert wt == wt2

    @pytest.mark.asyncio
    async def test_list_worktrees(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)

        cfg = _make_settings(tmp_path, approved_directory=str(repo))
        mgr = WorktreeManager(cfg)

        await mgr.create_worktree(repo, "s1")
        await mgr.create_worktree(repo, "s2")

        worktrees = await mgr.list_worktrees(repo)
        assert len(worktrees) == 2

    @pytest.mark.asyncio
    async def test_cleanup_stale_worktrees(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)

        cfg = _make_settings(tmp_path, approved_directory=str(repo))
        mgr = WorktreeManager(cfg)

        await mgr.create_worktree(repo, "keep")
        await mgr.create_worktree(repo, "stale")

        # Only "keep" is active
        removed = await mgr.cleanup_stale_worktrees(repo, {"keep"})
        assert removed == 1

        # Verify "keep" still exists, "stale" is gone
        assert (await mgr.get_worktree("keep")) is not None
        assert (await mgr.get_worktree("stale")) is None

    @pytest.mark.asyncio
    async def test_is_git_repo_real(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)

        cfg = _make_settings(tmp_path)
        mgr = WorktreeManager(cfg)

        assert await mgr.is_git_repo(repo) is True
        assert await mgr.is_git_repo(tmp_path) is False

    @pytest.mark.asyncio
    async def test_get_default_branch(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)

        cfg = _make_settings(tmp_path)
        mgr = WorktreeManager(cfg)

        branch = await mgr.get_default_branch(repo)
        # Should be "main" or "master" depending on git config
        assert branch in ("main", "master")

    @pytest.mark.asyncio
    async def test_worktree_has_isolated_branch(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)

        cfg = _make_settings(tmp_path, approved_directory=str(repo))
        mgr = WorktreeManager(cfg)

        wt_path = await mgr.create_worktree(repo, "isolated")

        # Check that the worktree is on its own branch
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(wt_path),
            capture_output=True,
            text=True,
        )
        assert result.stdout.strip() == "session/isolated"
