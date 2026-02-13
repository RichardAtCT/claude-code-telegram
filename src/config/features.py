"""Feature flag management."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .settings import Settings


class FeatureFlags:
    """Feature flag management system."""

    def __init__(self, settings: "Settings"):
        """Initialize with settings."""
        self.settings = settings

    @property
    def mcp_enabled(self) -> bool:
        """Check if Model Context Protocol is enabled."""
        return self.settings.enable_mcp and self.settings.mcp_config_path is not None

    @property
    def git_enabled(self) -> bool:
        """Check if Git integration is enabled."""
        return self.settings.enable_git_integration

    @property
    def file_uploads_enabled(self) -> bool:
        """Check if file uploads are enabled."""
        return self.settings.enable_file_uploads

    @property
    def quick_actions_enabled(self) -> bool:
        """Check if quick action buttons are enabled."""
        return self.settings.enable_quick_actions

    @property
    def telemetry_enabled(self) -> bool:
        """Check if telemetry is enabled."""
        return self.settings.enable_telemetry

    @property
    def token_auth_enabled(self) -> bool:
        """Check if token-based authentication is enabled."""
        return (
            self.settings.enable_token_auth
            and self.settings.auth_token_secret is not None
        )

    @property
    def webhook_enabled(self) -> bool:
        """Check if webhook mode is enabled."""
        return self.settings.webhook_url is not None

    @property
    def development_features_enabled(self) -> bool:
        """Check if development features are enabled."""
        return self.settings.development_mode

    @property
    def api_server_enabled(self) -> bool:
        """Check if the webhook API server is enabled."""
        return self.settings.enable_api_server

    @property
    def scheduler_enabled(self) -> bool:
        """Check if the job scheduler is enabled."""
        return self.settings.enable_scheduler

    @property
    def agentic_mode_enabled(self) -> bool:
        """Check if agentic conversational mode is enabled."""
        return self.settings.agentic_mode

    def is_feature_enabled(self, feature_name: str) -> bool:
        """Generic feature check by name."""
        feature_map = {
            "mcp": self.mcp_enabled,
            "git": self.git_enabled,
            "file_uploads": self.file_uploads_enabled,
            "quick_actions": self.quick_actions_enabled,
            "telemetry": self.telemetry_enabled,
            "token_auth": self.token_auth_enabled,
            "webhook": self.webhook_enabled,
            "development": self.development_features_enabled,
            "api_server": self.api_server_enabled,
            "scheduler": self.scheduler_enabled,
            "agentic_mode": self.agentic_mode_enabled,
        }
        return feature_map.get(feature_name, False)

    def get_enabled_features(self) -> list[str]:
        """Get list of all enabled features."""
        features = []
        if self.mcp_enabled:
            features.append("mcp")
        if self.git_enabled:
            features.append("git")
        if self.file_uploads_enabled:
            features.append("file_uploads")
        if self.quick_actions_enabled:
            features.append("quick_actions")
        if self.telemetry_enabled:
            features.append("telemetry")
        if self.token_auth_enabled:
            features.append("token_auth")
        if self.webhook_enabled:
            features.append("webhook")
        if self.development_features_enabled:
            features.append("development")
        if self.api_server_enabled:
            features.append("api_server")
        if self.scheduler_enabled:
            features.append("scheduler")
        return features
