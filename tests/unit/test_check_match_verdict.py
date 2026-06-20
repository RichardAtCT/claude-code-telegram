"""Regression tests for Check Match / Investigate verdict parsing.

These guard against the "corrupted double verdict" bug where the model emits two
contradictory blocks (e.g. a WON block followed by a LOST block) and the parser
concatenated both into the message shown to the user.
"""

from src.bot.handlers.callback import _parse_verdict_block

WON = "✅ WON"
LOST = "❌ LOST"
UNDET = "⏳ UNDETERMINED"
UNKNOWN = "❓ UNKNOWN"


def test_single_clean_block_passthrough():
    raw = f"{WON}\nScore: 6-2 | 6-1\nReason: P1 won the match 2-0."
    assert _parse_verdict_block(raw) == raw


def test_double_verdict_keeps_only_first_block():
    """The exact corruption: a WON block immediately followed by a LOST block."""
    raw = (
        f"{WON}\n"
        "Score: 5-7 | 6-1 | 0-4\n"
        "Reason: re-count gives 23 ... which is NOT > 23.5.\n"
        f"{LOST}\n"
        "Score: 5-7 | 6-1 | 0-4\n"
        "Reason: Total match games = 23, not over 23.5."
    )
    out = _parse_verdict_block(raw)
    assert out == (
        f"{WON}\n"
        "Score: 5-7 | 6-1 | 0-4\n"
        "Reason: re-count gives 23 ... which is NOT > 23.5."
    )
    assert LOST not in out
    # Exactly one status line survives.
    assert out.count(WON) == 1


def test_preamble_before_block_is_dropped():
    raw = (
        "Let me work through this carefully.\n"
        "First I add the games...\n"
        f"{UNDET}\n"
        "Score: 4-3\n"
        "Reason: only set 1 in progress, outcome not locked."
    )
    out = _parse_verdict_block(raw)
    assert out.startswith(UNDET)
    assert "Let me work" not in out


def test_undetermined_status_is_recognized():
    raw = f"{UNDET}\nScore: 0-4 in progress\nReason: outcome not yet locked."
    assert _parse_verdict_block(raw) == raw


def test_no_status_line_falls_back_to_raw():
    raw = "I cannot determine the result from this."
    assert _parse_verdict_block(raw) == raw


def test_trailing_blank_lines_trimmed():
    raw = f"{LOST}\nScore: 6-3\nReason: under busted.\n\n"
    assert _parse_verdict_block(raw) == f"{LOST}\nScore: 6-3\nReason: under busted."
