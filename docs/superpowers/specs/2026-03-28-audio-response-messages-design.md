# Audio Response Messages — Design Spec

## Overview

Add text-to-speech (TTS) capability so the bot can send Claude's responses back as Telegram voice messages using Mistral's Voxtral TTS API. The feature is opt-in at both the admin level (env var) and user level (toggle command).

## Requirements

- Users can toggle voice responses on/off via `/voice on` / `/voice off`
- When enabled, Claude's responses are synthesized to audio and sent as Telegram voice messages
- Short responses: voice message + brief text label (e.g. "Voice response")
- Long responses (above threshold): Claude summarizes for spoken delivery, audio of the summary is sent, full text is sent alongside
- On TTS failure: graceful fallback to text + "(Audio unavailable, sent as text)"
- Admin can disable the feature entirely; users cannot enable it if admin hasn't
- Uses Mistral Voxtral TTS API (same SDK already used for transcription)

## Configuration

### Environment Variables (admin-level)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ENABLE_VOICE_RESPONSES` | bool | `false` | Master switch for TTS feature |
| `VOICE_RESPONSE_MODEL` | str | `voxtral-4b-tts-2603` | Mistral TTS model name |
| `VOICE_RESPONSE_VOICE` | str | `jessica` | Mistral voice preset (see Mistral TTS docs for available voices) |
| `VOICE_RESPONSE_FORMAT` | str | `opus` | Audio output format (opus for Telegram voice compatibility) |
| `VOICE_RESPONSE_MAX_LENGTH` | int | `2000` | Character threshold for long response handling |

### User Toggle

- `/voice on` — enable voice responses for this user (persisted in SQLite)
- `/voice off` — disable voice responses
- `/voice` — show current status
- Command only available when `ENABLE_VOICE_RESPONSES=true`; otherwise responds: "Voice responses are not enabled on this instance"
- Register handler in `MessageOrchestrator._register_agentic_handlers()` and add to `get_bot_commands()`

### Feature Flag

New property `voice_responses_enabled` in `FeatureFlags`:
- Requires `ENABLE_VOICE_RESPONSES=true` AND `mistral_api_key` is set

## Architecture

### Approach: Extend VoiceHandler

Add TTS methods to the existing `VoiceHandler` class in `src/bot/features/voice_handler.py`. This class already manages the Mistral client and handles audio concerns (transcription). Adding synthesis keeps audio logic in one place and reuses the lazy-loaded client.

### New Method: `VoiceHandler.synthesize_speech(text: str) -> bytes`

- Calls `client.audio.speech.complete()` with configured model, voice, and format
- Returns raw audio bytes
- Reuses existing `_get_mistral_client()` — same lazy-loaded Mistral client used for transcription
- Raises `RuntimeError` on API failure (caught by caller)

### Response Flow in Orchestrator

Modified flow in `agentic_text()`, after Claude returns a response:

```
1. Get claude_response text
2. Check: voice_responses feature enabled AND user has toggle on?
   |-- NO --> send text as usual (existing path, unchanged)
   |-- YES -->
       3. Is len(response) > VOICE_RESPONSE_MAX_LENGTH?
          |-- YES (long response path):
          |   a. Call Claude to summarize for spoken delivery
          |   b. Synthesize summary via VoiceHandler.synthesize_speech()
          |   c. Send voice message via reply_voice()
          |   d. Send full text response as normal text message
          |   e. On TTS failure: send text + "(Audio unavailable, sent as text)"
          |
          |-- NO (short response path):
              a. Synthesize full response via VoiceHandler.synthesize_speech()
              b. Send voice message via reply_voice()
              c. Send short label text (e.g. "Voice response")
              d. On TTS failure: send text + "(Audio unavailable, sent as text)"
```

### New Orchestrator Method: `_maybe_send_voice_response()`

Private method encapsulating the voice response logic (steps 2-3 above). Called from `agentic_text()` before the existing text-sending block. Returns `True` if voice was sent successfully (so the text path adjusts accordingly), `False` otherwise.

### Summarization for Long Responses

When the response exceeds `VOICE_RESPONSE_MAX_LENGTH`, a second lightweight Claude call generates a spoken summary:
- Uses the existing `ClaudeIntegration.run_command()` with a summarization prompt
- System prompt: "Summarize the following response in 2-3 sentences suitable for being read aloud as a voice message."
- The summary is synthesized to audio; the full text is sent as a normal text message alongside

### Telegram API

Use `update.message.reply_voice(voice=audio_bytes)` for sending voice messages. Telegram voice messages use OGG/Opus natively, so the default output format is `opus` for compatibility.

## Storage

### Users Table Change

Add column `voice_responses_enabled` (boolean, default `false`) to the existing `users` table via the project's `_run_migrations()` pattern (ALTER TABLE).

### Repository Methods

Add to user repository:
- `get_voice_responses_enabled(user_id: int) -> bool`
- `set_voice_responses_enabled(user_id: int, enabled: bool) -> None`

No new tables needed.

## Error Handling

- TTS API failure (error, timeout, rate limit): fall back to normal text response + brief note "(Audio unavailable, sent as text)"
- Logged at `warning` level via structlog with error type
- Summarization failure: fall back to sending full text (skip audio)
- Feature disabled at admin level: `/voice` command explains it's unavailable

## Testing

### Unit Tests

- `VoiceHandler.synthesize_speech()` — mock Mistral client, verify correct params, verify bytes returned
- `/voice on|off` command — verify toggle persists in storage, verify response messages
- Long response detection — verify threshold triggers summarize path
- TTS failure fallback — mock API error, verify text fallback + note sent

### Integration Points

- `_maybe_send_voice_response()` — verify correct gating on feature flag + user toggle
- Verify existing voice transcription (STT) is unaffected

### Not Tested

- Actual Mistral API calls (mocked)
- Audio quality/playback

## Rollout

1. Feature is off by default (`ENABLE_VOICE_RESPONSES=false`)
2. Admin enables via env var (Mistral API key is already configured for transcription)
3. Individual users opt in via `/voice on`
