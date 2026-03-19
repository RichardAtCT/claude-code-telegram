"""Bot features package"""

from .code_review import CodeReviewManager, ReviewResult
from .collaboration import CollaborationManager
from .confirmation import ConfirmationManager, PendingAction
from .conversation_mode import ConversationContext, ConversationEnhancer
from .file_handler import CodebaseAnalysis, FileHandler, ProcessedFile
from .voice_handler import ProcessedVoice, VoiceHandler

__all__ = [
    "CodeReviewManager",
    "ReviewResult",
    "CollaborationManager",
    "ConfirmationManager",
    "PendingAction",
    "FileHandler",
    "ProcessedFile",
    "CodebaseAnalysis",
    "ConversationEnhancer",
    "ConversationContext",
    "VoiceHandler",
    "ProcessedVoice",
]
