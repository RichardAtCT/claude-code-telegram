"""Unit tests for chat routing helpers."""

from src.bot.features.chat_routing import (
    HISTORY_CONTEXT_SIZE,
    MAX_BUFFER_SIZE,
    append_to_buffer,
    build_group_prompt,
    format_history,
    get_working_directory,
    is_group_triggered,
    strip_group_trigger_prefix,
)
from src.config import create_test_config


def test_append_to_buffer_adds_message() -> None:
    """Messages are appended in sender/text form."""
    buffer: list[dict[str, str]] = []

    append_to_buffer(buffer, "Alice", "hello")

    assert buffer == [{"sender": "Alice", "text": "hello"}]


def test_append_to_buffer_trims_oldest_messages() -> None:
    """The buffer keeps only the most recent MAX_BUFFER_SIZE messages."""
    buffer: list[dict[str, str]] = []

    for idx in range(MAX_BUFFER_SIZE + 5):
        append_to_buffer(buffer, f"User {idx}", f"msg {idx}")

    assert len(buffer) == MAX_BUFFER_SIZE
    assert buffer[0] == {"sender": "User 5", "text": "msg 5"}
    assert buffer[-1] == {
        "sender": f"User {MAX_BUFFER_SIZE + 4}",
        "text": f"msg {MAX_BUFFER_SIZE + 4}",
    }


def test_format_history_handles_empty_messages() -> None:
    """Formatting an empty history returns an empty string."""
    assert format_history([]) == ""


def test_format_history_formats_multiple_messages() -> None:
    """History lines are rendered as Sender: text."""
    messages = [
        {"sender": "Alice", "text": "Hello"},
        {"sender": "Bob", "text": "World"},
    ]

    assert format_history(messages) == "Alice: Hello\nBob: World"


def test_get_working_directory_prefers_personal_chat(tmp_path) -> None:
    """Personal-chat mapping wins when the chat ID matches."""
    personal_dir = tmp_path / "personal"
    personal_dir.mkdir()
    group_dir = tmp_path / "group"
    group_dir.mkdir()
    settings = create_test_config(
        approved_directory=str(tmp_path),
        personal_chat_id=123,
        personal_chat_directory=str(personal_dir),
        group_chat_id=-100,
        group_chat_directory=str(group_dir),
    )

    assert get_working_directory(123, settings) == personal_dir.resolve()


def test_get_working_directory_uses_group_chat_directory(tmp_path) -> None:
    """Group-chat mapping is used when the group chat matches."""
    group_dir = tmp_path / "group"
    group_dir.mkdir()
    settings = create_test_config(
        approved_directory=str(tmp_path),
        group_chat_id=-100,
        group_chat_directory=str(group_dir),
    )

    assert get_working_directory(-100, settings) == group_dir.resolve()


def test_get_working_directory_falls_back_to_approved_directory(tmp_path) -> None:
    """Unknown chats use the global approved directory."""
    settings = create_test_config(approved_directory=str(tmp_path))

    assert get_working_directory(999, settings) == tmp_path.resolve()


def test_is_group_triggered_matches_plain_prefix() -> None:
    """The plain prefix triggers with and without trailing text."""
    assert is_group_triggered("claude", "claude") is True
    assert is_group_triggered("claude summarize this", "claude") is True


def test_is_group_triggered_matches_slash_prefix_variants() -> None:
    """Slash commands trigger in both plain and @botname forms."""
    assert is_group_triggered("/claude", "claude") is True
    assert is_group_triggered("/claude summarize this", "claude") is True
    assert is_group_triggered("/claude@test_bot", "claude") is True
    assert is_group_triggered("/claude@test_bot summarize this", "claude") is True


def test_is_group_triggered_rejects_non_matching_messages() -> None:
    """Messages without the configured prefix do not trigger."""
    assert is_group_triggered("please ask claude", "claude") is False
    assert is_group_triggered("/other@test_bot summarize this", "claude") is False


def test_strip_group_trigger_prefix_handles_plain_prefix() -> None:
    """Plain-prefix messages are stripped down to their payload."""
    assert strip_group_trigger_prefix("claude", "claude") == ""
    assert (
        strip_group_trigger_prefix("claude summarize this", "claude")
        == "summarize this"
    )


def test_strip_group_trigger_prefix_handles_slash_prefix() -> None:
    """Slash commands strip both the slash and any @botname suffix."""
    assert strip_group_trigger_prefix("/claude", "claude") == ""
    assert (
        strip_group_trigger_prefix("/claude summarize this", "claude")
        == "summarize this"
    )
    assert strip_group_trigger_prefix("/claude@test_bot", "claude") == ""
    assert (
        strip_group_trigger_prefix("/claude@test_bot summarize this", "claude")
        == "summarize this"
    )


def test_build_group_prompt_returns_stripped_text_without_history() -> None:
    """Triggered messages without history do not get a history wrapper."""
    assert (
        build_group_prompt([], "claude summarize this", "claude") == "summarize this"
    )


def test_build_group_prompt_injects_recent_history() -> None:
    """History is prepended ahead of the stripped group prompt."""
    history = [
        {"sender": "Alice", "text": "First"},
        {"sender": "Bob", "text": "Second"},
    ]

    prompt = build_group_prompt(history, "claude summarize this", "claude")

    assert prompt == (
        "[Recent group conversation:\nAlice: First\nBob: Second\n]\n\n"
        "summarize this"
    )


def test_build_group_prompt_limits_history_to_context_window() -> None:
    """Only the last HISTORY_CONTEXT_SIZE entries are injected."""
    history = [
        {"sender": f"User {idx}", "text": f"msg {idx}"}
        for idx in range(HISTORY_CONTEXT_SIZE + 3)
    ]

    prompt = build_group_prompt(history, "claude summarize this", "claude")

    assert "User 0: msg 0" not in prompt
    assert "User 1: msg 1" not in prompt
    assert "User 2: msg 2" not in prompt
    assert f"User 3: msg 3" in prompt
    assert prompt.endswith("]\n\nsummarize this")
