"""Git worktree manager for per-session filesystem isolation.

Creates and manages git worktrees so each Claude session operates
on an isolated branch and working directory.
"""

import asyncio
import shutil
from pathlib import Path
from typing import Optional, Set

import structlog

from ..config.settings import Settings

logger = structlog.get_logger()


class WorktreeError(Exception):
    """Error during worktree operations."""


class WorktreeManager:
    """Manage git worktrees for session isolation."""

    def __init__(self, config: Settings):
        """Initialize worktree manager."""
        self.config = config
        self.base_dir = config.worktree_base_dir or (
            config.approved_directory / ".worktrees"
        )
        self.branch_prefix = config.worktree_branch_prefix

    async def _run_git(self, *args: str, cwd: Optional[Path] = None) -> str:
        """Run a git command and return stdout."""
        cmd = ["git"] + list(args)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd) if cwd else None,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise WorktreeError(
                f"git {' '.join(args)} failed (rc={proc.returncode}): "
                f"{stderr.decode().strip()}"
            )
        return stdout.decode().strip()

    async def is_git_repo(self, path: Path) -> bool:
        """Check whether *path* is inside a git repository."""
        try:
            await self._run_git("rev-parse", "--git-dir", cwd=path)
            return True
        except (WorktreeError, FileNotFoundError):
            return False

    async def get_repo_root(self, path: Path) -> Path:
        """Return the top-level directory of the git repo containing *path*."""
        root = await self._run_git("rev-parse", "--show-toplevel", cwd=path)
        return Path(root)

    async def get_default_branch(self, repo_path: Path) -> str:
        """Detect the default branch (main/master/etc.) of a repo."""
        try:
            ref = await self._run_git(
                "symbolic-ref", "refs/remotes/origin/HEAD", cwd=repo_path
            )
            # refs/remotes/origin/main -> main
            return ref.rsplit("/", 1)[-1]
        except WorktreeError:
            # Fallback: check if 'main' exists, else 'master', else HEAD
            try:
                await self._run_git("rev-parse", "--verify", "main", cwd=repo_path)
                return "main"
            except WorktreeError:
                try:
                    await self._run_git(
                        "rev-parse", "--verify", "master", cwd=repo_path
                    )
                    return "master"
                except WorktreeError:
                    return "HEAD"

    # ------------------------------------------------------------------
    # Core worktree operations
    # ------------------------------------------------------------------

    def worktree_path_for(self, session_id: str) -> Path:
        """Return the filesystem path for a session's worktree."""
        # Sanitise session_id for use as a directory name
        safe_id = session_id.replace("/", "_").replace("..", "_")
        return self.base_dir / safe_id

    def branch_name_for(self, session_id: str) -> str:
        """Return the branch name for a session's worktree."""
        safe_id = session_id.replace("/", "_").replace("..", "_")
        return f"{self.branch_prefix}/{safe_id}"

    async def create_worktree(
        self,
        repo_path: Path,
        session_id: str,
        base_branch: Optional[str] = None,
    ) -> Path:
        """Create a new worktree for *session_id*.

        Returns the absolute path to the new worktree directory.
        """
        wt_path = self.worktree_path_for(session_id)
        branch = self.branch_name_for(session_id)

        if wt_path.exists():
            logger.info(
                "Worktree already exists",
                session_id=session_id,
                path=str(wt_path),
            )
            return wt_path

        # Ensure base directory exists
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # Resolve base branch
        if base_branch is None:
            base_branch = await self.get_default_branch(repo_path)

        logger.info(
            "Creating worktree",
            session_id=session_id,
            repo=str(repo_path),
            branch=branch,
            base_branch=base_branch,
            path=str(wt_path),
        )

        await self._run_git(
            "worktree",
            "add",
            "-b",
            branch,
            str(wt_path),
            base_branch,
            cwd=repo_path,
        )

        return wt_path

    async def get_worktree(self, session_id: str) -> Optional[Path]:
        """Return the worktree path if it exists on disk, else None."""
        wt_path = self.worktree_path_for(session_id)
        if wt_path.exists() and wt_path.is_dir():
            return wt_path
        return None

    async def get_or_create_worktree(
        self,
        repo_path: Path,
        session_id: str,
        base_branch: Optional[str] = None,
    ) -> Path:
        """Return existing worktree or create a new one."""
        existing = await self.get_worktree(session_id)
        if existing:
            return existing
        return await self.create_worktree(repo_path, session_id, base_branch)

    async def remove_worktree(self, repo_path: Path, session_id: str) -> None:
        """Remove a session's worktree and its branch."""
        wt_path = self.worktree_path_for(session_id)
        branch = self.branch_name_for(session_id)

        if wt_path.exists():
            logger.info(
                "Removing worktree",
                session_id=session_id,
                path=str(wt_path),
            )
            try:
                await self._run_git(
                    "worktree", "remove", "--force", str(wt_path), cwd=repo_path
                )
            except WorktreeError:
                # If git worktree remove fails, force-clean the directory
                logger.warning(
                    "git worktree remove failed, cleaning directory manually",
                    path=str(wt_path),
                )
                shutil.rmtree(wt_path, ignore_errors=True)
                # Prune stale worktree references
                try:
                    await self._run_git("worktree", "prune", cwd=repo_path)
                except WorktreeError:
                    pass

        # Clean up the branch (best-effort)
        try:
            await self._run_git("branch", "-D", branch, cwd=repo_path)
        except WorktreeError:
            # Branch may already be gone or never created
            pass

    async def list_worktrees(self, repo_path: Path) -> list[str]:
        """List all worktree paths managed under base_dir."""
        try:
            output = await self._run_git(
                "worktree", "list", "--porcelain", cwd=repo_path
            )
        except WorktreeError:
            return []

        paths = []
        base_str = str(self.base_dir)
        for line in output.splitlines():
            if line.startswith("worktree "):
                wt_path = line[len("worktree ") :]
                if wt_path.startswith(base_str):
                    paths.append(wt_path)
        return paths

    async def cleanup_stale_worktrees(
        self,
        repo_path: Path,
        active_session_ids: Set[str],
    ) -> int:
        """Remove worktrees for sessions that are no longer active.

        Returns the number of worktrees removed.
        """
        if not self.base_dir.exists():
            return 0

        removed = 0
        existing = await self.list_worktrees(repo_path)

        for wt_path_str in existing:
            wt_path = Path(wt_path_str)
            # The directory name is the session_id
            session_id = wt_path.name
            if session_id not in active_session_ids:
                logger.info(
                    "Cleaning stale worktree",
                    session_id=session_id,
                    path=wt_path_str,
                )
                await self.remove_worktree(repo_path, session_id)
                removed += 1

        return removed

    async def count_user_worktrees(
        self, repo_path: Path, user_session_ids: Set[str]
    ) -> int:
        """Count how many worktrees exist for a user's sessions."""
        count = 0
        for sid in user_session_ids:
            wt = await self.get_worktree(sid)
            if wt is not None:
                count += 1
        return count
