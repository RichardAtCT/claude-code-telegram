"""Voice-specific tests for classic message handlers."""

from unittest.mock import AsyncMock, MagicMock

from src.bot.handlers.message import handle_voice
from src.config import create_test_config


async def test_handle_voice_missing_handler_uses_openai_key(tmp_path):
    """Classic handler fallback references OPENAI_API_KEY for OpenAI provider."""
    settings = create_test_config(
        approved_directory=str(tmp_path),
        voice_provider="openai",
    )

    features = MagicMock()
    features.get_voice_handler.return_value = None

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot_data = {"settings": settings, "features": features}
    context.user_data = {}

    await handle_voice(update, context)

    call_args = update.message.reply_text.call_args
    assert "OPENAI_API_KEY" in call_args.args[0]
    assert call_args.kwargs["parse_mode"] == "HTML"


async def test_handle_voice_missing_handler_uses_mistral_key(tmp_path):
    """Classic handler fallback references MISTRAL_API_KEY for Mistral provider."""
    settings = create_test_config(
        approved_directory=str(tmp_path),
        voice_provider="mistral",
    )

    features = MagicMock()
    features.get_voice_handler.return_value = None

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot_data = {"settings": settings, "features": features}
    context.user_data = {}

    await handle_voice(update, context)

    call_args = update.message.reply_text.call_args
    assert "MISTRAL_API_KEY" in call_args.args[0]
