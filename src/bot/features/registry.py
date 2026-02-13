"""
Central feature registry and management
"""

from typing import Any, Dict, Optional

import structlog

from src.config.settings import Settings
from src.security.validators import SecurityValidator
from src.storage.facade import Storage

from .conversation_mode import ConversationEnhancer
from .file_handler import FileHandler
from .git_integration import GitIntegration
from .image_handler import ImageHandler
from .quick_actions import QuickActionManager
from .session_export import SessionExporter

logger = structlog.get_logger(__name__)


class FeatureRegistry:
    """Manage all bot features"""

    def __init__(self, config: Settings, storage: Storage, security: SecurityValidator):
        self.config = config
        self.storage = storage
        self.security = security
        self.features: Dict[str, Any] = {}

        # Initialize features based on config
        self._initialize_features()

    def _initialize_features(self):
        """Initialize enabled features"""
        logger.info("Initializing bot features")

        # File upload handling - conditionally enabled
        if self.config.enable_file_uploads:
            try:
                self.features["file_handler"] = FileHandler(
                    config=self.config, security=self.security
                )
                logger.info("File handler feature enabled")
            except Exception as e:
                logger.error("Failed to initialize file handler", error=str(e))

        # Git integration - conditionally enabled
        if self.config.enable_git_integration:
            try:
                self.features["git"] = GitIntegration(settings=self.config)
                logger.info("Git integration feature enabled")
            except Exception as e:
                logger.error("Failed to initialize git integration", error=str(e))

        # Quick actions - skip in agentic mode
        if self.config.enable_quick_actions and not self.config.agentic_mode:
            try:
                self.features["quick_actions"] = QuickActionManager()
                logger.info("Quick actions feature enabled")
            except Exception as e:
                logger.error("Failed to initialize quick actions", error=str(e))

        # Session export - classic mode only
        if not self.config.agentic_mode:
            try:
                self.features["session_export"] = SessionExporter(storage=self.storage)
                logger.info("Session export feature enabled")
            except Exception as e:
                logger.error("Failed to initialize session export", error=str(e))

        # Image handling - always enabled
        try:
            self.features["image_handler"] = ImageHandler(config=self.config)
            logger.info("Image handler feature enabled")
        except Exception as e:
            logger.error("Failed to initialize image handler", error=str(e))

        # Conversation enhancements - skip in agentic mode
        if not self.config.agentic_mode:
            try:
                self.features["conversation"] = ConversationEnhancer()
                logger.info("Conversation enhancer feature enabled")
            except Exception as e:
                logger.error("Failed to initialize conversation enhancer", error=str(e))

        logger.info(
            "Feature initialization complete",
            enabled_features=list(self.features.keys()),
        )

    def get_feature(self, name: str) -> Optional[Any]:
        """Get feature by name"""
        return self.features.get(name)

    def is_enabled(self, feature_name: str) -> bool:
        """Check if feature is enabled"""
        return feature_name in self.features

    def get_file_handler(self) -> Optional[FileHandler]:
        """Get file handler feature"""
        return self.get_feature("file_handler")

    def get_git_integration(self) -> Optional[GitIntegration]:
        """Get git integration feature"""
        return self.get_feature("git")

    def get_quick_actions(self) -> Optional[QuickActionManager]:
        """Get quick actions feature"""
        return self.get_feature("quick_actions")

    def get_session_export(self) -> Optional[SessionExporter]:
        """Get session export feature"""
        return self.get_feature("session_export")

    def get_image_handler(self) -> Optional[ImageHandler]:
        """Get image handler feature"""
        return self.get_feature("image_handler")

    def get_conversation_enhancer(self) -> Optional[ConversationEnhancer]:
        """Get conversation enhancer feature"""
        return self.get_feature("conversation")

    def get_enabled_features(self) -> Dict[str, Any]:
        """Get all enabled features"""
        return self.features.copy()

    def shutdown(self):
        """Shutdown all features"""
        logger.info("Shutting down features")

        # Clear conversation contexts
        conversation = self.get_conversation_enhancer()
        if conversation:
            conversation.conversation_contexts.clear()

        # Clear feature registry
        self.features.clear()

        logger.info("Feature shutdown complete")
