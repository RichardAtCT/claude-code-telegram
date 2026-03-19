"""Tests that persona is injected into Claude's system prompt."""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.claude.facade import ClaudeIntegration
from src.claude.sdk_integration import ClaudeResponse


@pytest.fixture
def mock_storage():
    s = MagicMock()
    s.profiles = MagicMock()
    s.profiles.get_profile = AsyncMock(return_value=None)
    s.memories = MagicMock()
    s.memories.list_memories = AsyncMock(return_value=[])
    return s


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.session_timeout_hours = 24
    config.anthropic_api_key_str = None
    return config


async def test_run_command_builds_persona(mock_config, mock_storage):
    """run_command should call PersonaBuilder.build with the user_id."""
    from src.assistant.persona import PersonaBuilder

    sdk_manager = MagicMock()
    fake_response = ClaudeResponse(
        content="ok", session_id="s1", cost=0.0, duration_ms=10, num_turns=1
    )
    sdk_manager.execute_command = AsyncMock(return_value=fake_response)

    session_manager = MagicMock()
    mock_session = MagicMock()
    mock_session.session_id = "s1"
    mock_session.is_new_session = True
    session_manager.get_or_create_session = AsyncMock(return_value=mock_session)
    session_manager.update_session = AsyncMock()
    session_manager._get_user_sessions = AsyncMock(return_value=[])

    with patch.object(PersonaBuilder, "build", new_callable=AsyncMock) as mock_build:
        mock_build.return_value = "You are a personal assistant."
        integration = ClaudeIntegration(
            config=mock_config,
            sdk_manager=sdk_manager,
            session_manager=session_manager,
            storage=mock_storage,
        )
        await integration.run_command(
            prompt="hello",
            working_directory=Path("/tmp"),
            user_id=99,
        )
        mock_build.assert_awaited_once_with(user_id=99)


async def test_run_command_passes_persona_to_sdk(mock_config, mock_storage):
    """The persona prefix should be passed to execute_command as system_prompt_prefix."""
    from src.assistant.persona import PersonaBuilder

    sdk_manager = MagicMock()
    fake_response = ClaudeResponse(
        content="ok", session_id="s1", cost=0.0, duration_ms=10, num_turns=1
    )
    sdk_manager.execute_command = AsyncMock(return_value=fake_response)

    session_manager = MagicMock()
    mock_session = MagicMock()
    mock_session.session_id = "s1"
    mock_session.is_new_session = True
    session_manager.get_or_create_session = AsyncMock(return_value=mock_session)
    session_manager.update_session = AsyncMock()
    session_manager._get_user_sessions = AsyncMock(return_value=[])

    persona_text = "You are a personal assistant. User name: Paulius."
    with patch.object(PersonaBuilder, "build", new_callable=AsyncMock) as mock_build:
        mock_build.return_value = persona_text
        integration = ClaudeIntegration(
            config=mock_config,
            sdk_manager=sdk_manager,
            session_manager=session_manager,
            storage=mock_storage,
        )
        await integration.run_command(
            prompt="hello",
            working_directory=Path("/tmp"),
            user_id=99,
        )
        call_kwargs = sdk_manager.execute_command.call_args.kwargs
        assert call_kwargs.get("system_prompt_prefix") == persona_text
