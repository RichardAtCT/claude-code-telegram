"""Authentication system supporting multiple methods.

Features:
- Telegram ID whitelist
- Token-based authentication
- Session management
- Audit logging
"""

import hashlib
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog

from src.exceptions import SecurityError

# from src.exceptions import AuthenticationError  # Future use

logger = structlog.get_logger()


@dataclass
class UserSession:
    """User session data."""

    user_id: int
    auth_provider: str
    created_at: datetime
    last_activity: datetime
    user_info: Optional[Dict[str, Any]] = None
    session_timeout: timedelta = timedelta(hours=24)

    def __post_init__(self) -> None:
        if self.last_activity is None:
            self.last_activity = self.created_at

    def is_expired(self) -> bool:
        """Check if session has expired."""
        return datetime.now(UTC) - self.last_activity > self.session_timeout

    def refresh(self) -> None:
        """Refresh session activity."""
        self.last_activity = datetime.now(UTC)


class AuthProvider(ABC):
    """Base authentication provider."""

    @abstractmethod
    async def authenticate(self, user_id: int, credentials: Dict[str, Any]) -> bool:
        """Verify user credentials."""

    @abstractmethod
    async def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user information."""


class WhitelistAuthProvider(AuthProvider):
    """Whitelist-based authentication."""

    def __init__(self, allowed_users: List[int], allow_all_dev: bool = False):
        self.allowed_users = set(allowed_users)
        self.allow_all_dev = allow_all_dev
        logger.info(
            "Whitelist auth provider initialized",
            allowed_users=len(self.allowed_users),
            allow_all_dev=allow_all_dev,
        )

    async def authenticate(self, user_id: int, credentials: Dict[str, Any]) -> bool:
        """Authenticate user against whitelist."""
        is_allowed = self.allow_all_dev or user_id in self.allowed_users
        logger.info(
            "Whitelist authentication attempt", user_id=user_id, success=is_allowed
        )
        return is_allowed

    async def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user information if whitelisted."""
        if self.allow_all_dev or user_id in self.allowed_users:
            return {
                "user_id": user_id,
                "auth_type": "whitelist" + ("_dev" if self.allow_all_dev else ""),
                "permissions": ["basic"],
            }
        return None


class TokenStorage(ABC):
    """Abstract token storage interface."""

    @abstractmethod
    async def store_token(
        self, user_id: int, token_hash: str, expires_at: datetime
    ) -> None:
        """Store token hash for user."""

    @abstractmethod
    async def get_user_token(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get token data for user."""

    @abstractmethod
    async def revoke_token(self, user_id: int) -> None:
        """Revoke token for user."""


class InMemoryTokenStorage(TokenStorage):
    """In-memory token storage for development/testing."""

    def __init__(self) -> None:
        self._tokens: Dict[int, Dict[str, Any]] = {}

    async def store_token(
        self, user_id: int, token_hash: str, expires_at: datetime
    ) -> None:
        """Store token hash in memory."""
        self._tokens[user_id] = {
            "hash": token_hash,
            "expires_at": expires_at,
            "created_at": datetime.now(UTC),
        }

    async def get_user_token(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get token data from memory."""
        token_data = self._tokens.get(user_id)
        if token_data and token_data["expires_at"] > datetime.now(UTC):
            return token_data
        elif token_data:
            # Token expired, remove it
            del self._tokens[user_id]
        return None

    async def revoke_token(self, user_id: int) -> None:
        """Remove token from memory."""
        self._tokens.pop(user_id, None)


class TokenAuthProvider(AuthProvider):
    """Token-based authentication."""

    def __init__(
        self,
        secret: str,
        storage: TokenStorage,
        token_lifetime: timedelta = timedelta(days=30),
    ):
        self.secret = secret
        self.storage = storage
        self.token_lifetime = token_lifetime
        logger.info("Token auth provider initialized")

    async def authenticate(self, user_id: int, credentials: Dict[str, Any]) -> bool:
        """Authenticate using token."""
        token = credentials.get("token")
        if not token:
            logger.warning(
                "Token authentication failed: no token provided", user_id=user_id
            )
            return False

        stored_token = await self.storage.get_user_token(user_id)
        if not stored_token:
            logger.warning(
                "Token authentication failed: no stored token", user_id=user_id
            )
            return False

        is_valid = self._verify_token(token, stored_token["hash"])
        logger.info("Token authentication attempt", user_id=user_id, success=is_valid)
        return is_valid

    async def generate_token(self, user_id: int) -> str:
        """Generate new authentication token."""
        token = secrets.token_urlsafe(32)
        hashed = self._hash_token(token)
        expires_at = datetime.now(UTC) + self.token_lifetime

        await self.storage.store_token(user_id, hashed, expires_at)

        logger.info(
            "Token generated", user_id=user_id, expires_at=expires_at.isoformat()
        )
        return token

    async def revoke_token(self, user_id: int) -> None:
        """Revoke user's token."""
        await self.storage.revoke_token(user_id)
        logger.info("Token revoked", user_id=user_id)

    async def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user information if token is valid."""
        token_data = await self.storage.get_user_token(user_id)
        if token_data:
            return {
                "user_id": user_id,
                "auth_type": "token",
                "permissions": ["basic", "advanced"],
                "token_created": token_data["created_at"].isoformat(),
                "token_expires": token_data["expires_at"].isoformat(),
            }
        return None

    def _hash_token(self, token: str) -> str:
        """Hash token for secure storage."""
        return hashlib.sha256(f"{token}{self.secret}".encode()).hexdigest()

    def _verify_token(self, token: str, stored_hash: str) -> bool:
        """Verify token against stored hash."""
        return self._hash_token(token) == stored_hash


class AuthenticationManager:
    """Main authentication manager supporting multiple providers."""

    def __init__(self, providers: List[AuthProvider]):
        if not providers:
            raise SecurityError("At least one authentication provider is required")

        self.providers = providers
        self.sessions: Dict[int, UserSession] = {}
        logger.info("Authentication manager initialized", providers=len(self.providers))

    async def authenticate_user(
        self, user_id: int, credentials: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Try authentication with all providers."""
        credentials = credentials or {}

        # Clean expired sessions first
        self._cleanup_expired_sessions()

        # Try each provider
        for provider in self.providers:
            try:
                if await provider.authenticate(user_id, credentials):
                    await self._create_session(user_id, provider)
                    logger.info(
                        "User authenticated successfully",
                        user_id=user_id,
                        provider=provider.__class__.__name__,
                    )
                    return True
            except Exception as e:
                logger.error(
                    "Authentication provider error",
                    user_id=user_id,
                    provider=provider.__class__.__name__,
                    error=str(e),
                )

        logger.warning("Authentication failed for user", user_id=user_id)
        return False

    async def _create_session(self, user_id: int, provider: AuthProvider) -> None:
        """Create authenticated session."""
        user_info = await provider.get_user_info(user_id)
        self.sessions[user_id] = UserSession(
            user_id=user_id,
            auth_provider=provider.__class__.__name__,
            created_at=datetime.now(UTC),
            last_activity=datetime.now(UTC),
            user_info=user_info,
        )

        logger.info(
            "Session created", user_id=user_id, provider=provider.__class__.__name__
        )

    def is_authenticated(self, user_id: int) -> bool:
        """Check if user has active session."""
        session = self.sessions.get(user_id)
        if session and not session.is_expired():
            return True
        elif session:
            # Remove expired session
            del self.sessions[user_id]
            logger.info("Expired session removed", user_id=user_id)
        return False

    def get_session(self, user_id: int) -> Optional[UserSession]:
        """Get user session if valid."""
        if self.is_authenticated(user_id):
            return self.sessions[user_id]
        return None

    def refresh_session(self, user_id: int) -> bool:
        """Refresh user session activity."""
        session = self.get_session(user_id)
        if session:
            session.refresh()
            return True
        return False

    def end_session(self, user_id: int) -> None:
        """End user session."""
        if user_id in self.sessions:
            del self.sessions[user_id]
            logger.info("Session ended", user_id=user_id)

    def _cleanup_expired_sessions(self) -> None:
        """Remove expired sessions."""
        expired_sessions = [
            user_id
            for user_id, session in self.sessions.items()
            if session.is_expired()
        ]

        for user_id in expired_sessions:
            del self.sessions[user_id]

        if expired_sessions:
            logger.info("Expired sessions cleaned up", count=len(expired_sessions))

    def get_active_sessions_count(self) -> int:
        """Get count of active sessions."""
        self._cleanup_expired_sessions()
        return len(self.sessions)

    def get_session_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get session information for user."""
        session = self.get_session(user_id)
        if session:
            return {
                "user_id": session.user_id,
                "auth_provider": session.auth_provider,
                "created_at": session.created_at.isoformat(),
                "last_activity": session.last_activity.isoformat(),
                "is_expired": session.is_expired(),
                "user_info": session.user_info,
            }
        return None
