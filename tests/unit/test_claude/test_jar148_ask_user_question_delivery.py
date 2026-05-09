"""Regression tests for JAR-148: AskUserQuestion must be user-visible.

The bug: Claude can emit rich text and then a non-deliverable AskUserQuestion
tool call in the same turn. Telegram saw neither the rich text nor the choice
prompt. At minimum, the final response must include the text plus a readable
numbered representation of the choices.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

from src.claude.sdk_integration import ClaudeSDKManager
from src.config.settings import Settings


def _make_result_message(result=None) -> ResultMessage:
    return ResultMessage(
        subtype="success",
        duration_ms=1000,
        duration_api_ms=800,
        is_error=False,
        num_turns=1,
        session_id="test-session",
        total_cost_usd=0.01,
        result=result,
    )


def _mock_client(*messages):
    client = AsyncMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.query = AsyncMock()

    async def receive_raw_messages():
        for msg in messages:
            yield msg

    query_mock = AsyncMock()
    query_mock.receive_messages = receive_raw_messages
    client._query = query_mock
    return client


def _make_manager(tmp_path):
    return ClaudeSDKManager(
        Settings(
            telegram_bot_token="test:token",
            telegram_bot_username="testbot",
            approved_directory=tmp_path,
            claude_timeout_seconds=2,
            enable_mcp=False,
        )
    )


async def test_text_plus_ask_user_question_tool_is_delivered_as_numbered_prompt(
    tmp_path,
):
    manager = _make_manager(tmp_path)

    rich_text = AssistantMessage(
        content=[TextBlock(text="Minha recomendação é atacar JAR-147 primeiro.")],
        model="claude-sonnet-4-20250514",
    )
    ask_user_question = AssistantMessage(
        content=[
            ToolUseBlock(
                id="ask-1",
                name="AskUserQuestion",
                input={
                    "question": "Qual issue você quer atacar agora?",
                    "choices": [
                        "JAR-147",
                        "JAR-148",
                        "JAR-149",
                        "Outra",
                    ],
                },
            )
        ],
        model="claude-sonnet-4-20250514",
    )

    with (
        patch("src.claude.sdk_integration.parse_message", side_effect=lambda x: x),
        patch(
            "src.claude.sdk_integration.ClaudeSDKClient",
            return_value=_mock_client(
                rich_text,
                ask_user_question,
                _make_result_message(result=None),
            ),
        ),
    ):
        response = await manager.execute_command(
            prompt="Test",
            working_directory=Path("/test"),
        )

    assert "Minha recomendação" in response.content
    assert "Qual issue você quer atacar agora?" in response.content
    assert "1) JAR-147" in response.content
    assert "2) JAR-148" in response.content
    assert "3) JAR-149" in response.content
    assert "4) Outra" in response.content
