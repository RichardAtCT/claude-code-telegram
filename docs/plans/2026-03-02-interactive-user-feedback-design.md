# Interactive User Feedback via Telegram Inline Keyboards

**Date:** 2026-03-02
**Status:** Approved

## Problem

When Claude calls `AskUserQuestion` (e.g. during brainstorming skills), the CLI subprocess has no TTY and auto-selects the first option. The Telegram user never sees the question and has no way to provide their actual answer.

## Solution

Use a `PreToolUse` SDK hook on `AskUserQuestion` that intercepts the tool call, presents the question as Telegram inline keyboard buttons, waits for the user's tap, and returns the answer via `updatedInput` so the CLI executes the tool with the user's actual choice.

## Approach: PreToolUse Hook with Shared Future

The hook callback and Telegram handler run in the same asyncio event loop. An `asyncio.Future` coordinates between them — the hook awaits the Future while the Telegram callback handler resolves it.

## Data Flow

```
Claude calls AskUserQuestion(questions=[...])
    │
    ▼
CLI sends PreToolUse hook_callback to SDK via control protocol
    │
    ▼
SDK invokes Python hook callback (closure in sdk_integration.py)
    │
    ├── Extracts questions + options from tool_input
    ├── Calls bot.send_message() with inline keyboard
    ├── Creates asyncio.Future, stores in _pending dict
    ├── Awaits the Future (Claude is paused)
    │
    ▼
User taps inline button in Telegram
    │
    ▼
CallbackQueryHandler (pattern "askq:") in orchestrator
    │
    ├── Looks up pending Future by (user_id, chat_id)
    ├── Resolves Future with selected answer
    │
    ▼
Hook callback resumes
    │
    ├── Builds updatedInput with answers dict pre-filled
    ├── Returns SyncHookJSONOutput with hookSpecificOutput
    │
    ▼
CLI executes AskUserQuestion with user's actual answer
```

## Scope

All Claude interactions — not just /menu skills. Any time Claude calls `AskUserQuestion`, the question is routed to Telegram.

## Shared State & Coordination

### PendingQuestion Registry

New file `src/bot/features/interactive_questions.py` with a module-level dict:

```python
_pending: Dict[Tuple[int, int], asyncio.Future] = {}
```

Keyed by `(user_id, chat_id)`. Only one question pending per user+chat at a time (Claude is paused, can't ask another until the first is answered).

### Hook Callback as Closure

`execute_command()` already knows `user_id`. It gains a `telegram_context` parameter (bot, chat_id, thread_id) so it can build the hook closure capturing:
- `user_id`, `chat_id`, `message_thread_id` — where to send the keyboard
- `bot` instance — to call `bot.send_message()`
- Reference to `_pending` dict — to create/resolve Futures

### Telegram Handler

New `CallbackQueryHandler(pattern=r"^askq:")` registered in the orchestrator. Parses callback data, looks up Future, resolves it.

## AskUserQuestion Input Format

```python
{
    "questions": [
        {
            "question": "Which approach?",
            "header": "Approach",
            "options": [
                {"label": "Option A", "description": "..."},
                {"label": "Option B", "description": "..."},
            ],
            "multiSelect": false
        }
    ],
    "answers": {
        "Which approach?": "Option A"  # ← we pre-fill this
    }
}
```

- `questions`: list of 1-4 questions per call
- Each question has 2-4 options + implicit "Other"
- `answers`: dict keyed by question text → selected label(s)
- `multiSelect: true`: multiple options selectable

## Telegram UX

### Callback Data Format (64-byte limit)

- Single select: `askq:0:1` (question 0, option 1)
- Multi-select toggle: `askq:0:t1` (question 0, toggle option 1)
- Multi-select done: `askq:0:done`
- Other: `askq:0:other`

### Single-Select Layout

```
Which approach should we use?

• Option A — Does X and Y
• Option B — Does Z

[Option A] [Option B]
[Other...]
```

### Multi-Select Layout (mid-selection)

```
Which features do you want?

• Auth — Login system
• Cache — Redis caching
• Logs — Structured logging

[☑ Auth] [☐ Cache] [☑ Logs]
[Other...]
[Done ✓]
```

### "Other" Flow

1. User taps "Other..."
2. Message edited to "Type your answer:"
3. One-time MessageHandler captures next text message from that user+chat
4. Text used as answer, Future resolved
5. Handler removes itself

### Sequential Questions

If `AskUserQuestion` has multiple questions (1-4), process one at a time: show question 1, wait for answer, show question 2, wait, etc. All answers collected, then returned as one `updatedInput`.

## Error Handling

- **No timeout on the Future** — waits indefinitely. The outer `claude_timeout_seconds` (3600s) is the hard bound.
- **Stale questions** — if session errors, Future is cancelled in `finally` block. Tapping stale buttons returns "Question expired."
- **Concurrent sessions** — keyed by `(user_id, chat_id)`, independent per project thread.
- **Button clicks after answer** — "Already answered" feedback, keyboard removed.
- **"Other" text capture** — one-time MessageHandler scoped to user+chat, removes itself after capture.

## Files Changed

| File | Change |
|------|--------|
| `src/bot/features/interactive_questions.py` | **New.** Pending dict, keyboard builder, question formatter, callback handler, "Other" text handler |
| `src/claude/sdk_integration.py` | Add `telegram_context` param to `execute_command()`, build PreToolUse hook closure, register in `options.hooks` |
| `src/claude/facade.py` | Pass `telegram_context` through `run_command()` → `_execute()` → `execute_command()` |
| `src/bot/orchestrator.py` | Pass telegram context when calling `run_command()`, register `askq:` CallbackQueryHandler |
| `src/bot/handlers/menu.py` | Pass telegram context when calling `run_command()` from menu skill execution |
