"""Multi-user collaboration — teams and shared projects.

Allows users to create teams, invite members, and share project contexts
so multiple users can collaborate on the same codebase via the bot.
"""

import uuid
from datetime import UTC, datetime
from typing import Dict, List, Optional

import structlog

from ...storage.database import DatabaseManager
from ...storage.models import SharedProjectModel, TeamMemberModel, TeamModel
from ...storage.repositories import TeamRepository

logger = structlog.get_logger()


class CollaborationManager:
    """Manages teams, membership, and shared project sessions."""

    def __init__(self, team_repo: TeamRepository):
        self.team_repo = team_repo

    async def create_team(self, name: str, creator_user_id: int) -> str:
        """Create a new team and add the creator as admin.

        Returns the team_id.
        """
        team = await self.team_repo.create_team(name, creator_user_id)
        logger.info(
            "Team created",
            team_id=team.team_id,
            name=name,
            creator=creator_user_id,
        )
        return team.team_id

    async def invite_member(
        self,
        team_id: str,
        user_id: int,
        inviter_id: int,
        role: str = "member",
    ) -> bool:
        """Add a user to a team.

        The inviter must be an admin or the creator. Returns True on success.
        """
        # Verify inviter has permission
        members = await self.team_repo.get_team_members(team_id)
        inviter_member = next(
            (m for m in members if m.user_id == inviter_id), None
        )
        if not inviter_member or inviter_member.role not in ("admin", "creator"):
            logger.warning(
                "Unauthorized invite attempt",
                team_id=team_id,
                inviter_id=inviter_id,
            )
            return False

        # Check if already a member
        if any(m.user_id == user_id for m in members):
            logger.info(
                "User already a team member",
                team_id=team_id,
                user_id=user_id,
            )
            return False

        await self.team_repo.add_member(team_id, user_id, role)
        logger.info(
            "Member added to team",
            team_id=team_id,
            user_id=user_id,
            role=role,
            invited_by=inviter_id,
        )
        return True

    async def remove_member(
        self, team_id: str, user_id: int, remover_id: int
    ) -> bool:
        """Remove a user from a team. Remover must be admin/creator."""
        members = await self.team_repo.get_team_members(team_id)
        remover = next((m for m in members if m.user_id == remover_id), None)
        if not remover or remover.role not in ("admin", "creator"):
            return False

        await self.team_repo.remove_member(team_id, user_id)
        logger.info(
            "Member removed from team",
            team_id=team_id,
            user_id=user_id,
            removed_by=remover_id,
        )
        return True

    async def share_project(
        self, team_id: str, project_path: str, user_id: int
    ) -> Optional[SharedProjectModel]:
        """Share a project with the team. User must be a member."""
        if not await self.is_team_member(team_id, user_id):
            logger.warning(
                "Non-member tried to share project",
                team_id=team_id,
                user_id=user_id,
            )
            return None

        shared = await self.team_repo.share_project(team_id, project_path)
        logger.info(
            "Project shared with team",
            team_id=team_id,
            project_path=project_path,
            shared_session_id=shared.shared_session_id,
        )
        return shared

    async def get_shared_session(
        self, team_id: str, project_path: str
    ) -> Optional[str]:
        """Get the shared session ID for a team+project, if any."""
        projects = await self.team_repo.get_shared_projects(team_id)
        for p in projects:
            if p.project_path == project_path:
                return p.shared_session_id
        return None

    async def is_team_member(self, team_id: str, user_id: int) -> bool:
        """Check if user is a member of the team."""
        members = await self.team_repo.get_team_members(team_id)
        return any(m.user_id == user_id for m in members)

    async def get_user_teams(self, user_id: int) -> List[TeamModel]:
        """Get all teams a user belongs to."""
        return await self.team_repo.get_user_teams(user_id)

    async def get_team_members(self, team_id: str) -> List[TeamMemberModel]:
        """Get all members of a team."""
        return await self.team_repo.get_team_members(team_id)

    async def get_shared_projects(
        self, team_id: str
    ) -> List[SharedProjectModel]:
        """Get all shared projects for a team."""
        return await self.team_repo.get_shared_projects(team_id)
