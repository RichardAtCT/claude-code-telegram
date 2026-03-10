# Model Switching Feature

## Overview

This feature allows users to dynamically switch between different Claude models within their Telegram session using the `/model` command.

## Configuration

### Environment Variable

Add the `ANTHROPIC_MODELS` variable to your `.env` file:

```bash
# Available Claude models for user selection (comma-separated)
ANTHROPIC_MODELS=claude-opus-4-6,claude-sonnet-4-6,claude-haiku-4-5
```

**Note:** This is optional. If not configured, users can still switch models by typing any valid model name.

## Usage

### View Current Model and Available Options

```
/model
```

**Response:**
```
Current model: claude-opus-4-6

Available models:
  • claude-opus-4-6
  • claude-sonnet-4-6
  • claude-haiku-4-5

Usage: /model <model-name>
Example: /model claude-opus-4-6

Use /model default to reset to config default.
```

### Switch to a Different Model

```
/model claude-sonnet-4-6
```

**Response:**
```
✅ Model switched to: claude-sonnet-4-6

This will be used for all subsequent messages in this session.
```

### Reset to Default Model

```
/model default
```

**Response:**
```
✅ Model reset to default: claude-opus-4-6
```

## How It Works

### Architecture

1. **Configuration Layer** (`src/config/settings.py`)
   - New field: `anthropic_models: Optional[List[str]]`
   - Parses comma-separated model names from `ANTHROPIC_MODELS` env var
   - Validates and strips whitespace

2. **Session State** (`src/bot/orchestrator.py`)
   - Per-user model selection stored in `context.user_data["selected_model"]`
   - Falls back to `CLAUDE_MODEL` config if no user override
   - Persists throughout the Telegram session

3. **SDK Integration** (`src/claude/sdk_integration.py`)
   - Accepts optional `model` parameter in `execute_command()`
   - Overrides config model when provided
   - Passes to Claude Agent SDK options

4. **Command Handler** (`src/bot/orchestrator.py`)
   - `/model` command with argument parsing
   - Validates model against `ANTHROPIC_MODELS` list (if configured)
   - HTML-escaped output to prevent injection

### Request Flow

```
User: /model claude-sonnet-4-6
  ↓
MessageOrchestrator.agentic_model()
  ↓
Validate model in available_models list
  ↓
context.user_data["selected_model"] = "claude-sonnet-4-6"
  ↓
User: "Write a hello world program"
  ↓
MessageOrchestrator.agentic_text()
  ↓
selected_model = _get_selected_model(context)  # Returns "claude-sonnet-4-6"
  ↓
ClaudeIntegration.run_command(model=selected_model)
  ↓
ClaudeSDKManager.execute_command(model=selected_model)
  ↓
ClaudeAgentOptions(model="claude-sonnet-4-6")
  ↓
Claude SDK executes with specified model
```

## Security Considerations

1. **HTML Escaping**: All model names are escaped with `escape_html()` before display
2. **Validation**: If `ANTHROPIC_MODELS` is configured, only listed models are allowed
3. **User Isolation**: Model selection is per-user via `context.user_data`
4. **No Injection Risk**: Model parameter is passed directly to SDK, not evaluated

## Testing

Run the test suite:

```bash
python test_model_switching.py
```

**Tests cover:**
- Configuration parsing (comma-separated, single, with spaces)
- User selection logic (default, override, reset)
- Integration with settings validation

## Implementation Details

### Files Modified

1. **src/config/settings.py**
   - Added `anthropic_models: Optional[List[str]]` field
   - Updated `parse_claude_allowed_tools` validator to handle model lists

2. **src/claude/facade.py**
   - Added `model: Optional[str]` parameter to `run_command()`
   - Passes model through to SDK integration

3. **src/claude/sdk_integration.py**
   - Added `model: Optional[str]` parameter to `execute_command()`
   - Uses `effective_model = model or self.config.claude_model`
   - Passes to `ClaudeAgentOptions(model=effective_model)`

4. **src/bot/orchestrator.py**
   - Added `_get_selected_model()` helper method
   - Added `agentic_model()` command handler
   - Updated `agentic_text()` to pass selected model
   - Registered `/model` command in handler list
   - Added to bot command menu

5. **.env.example**
   - Added `ANTHROPIC_MODELS` documentation and example

6. **CLAUDE.md**
   - Updated agentic mode commands list
   - Added model selection configuration documentation

## Examples

### Use Case 1: Quick Prototyping

```bash
# Start with fast, cheap model
/model claude-haiku-4-5
User: "Generate 10 test users"

# Switch to more capable model for complex work
/model claude-opus-4-6
User: "Now add authentication with JWT tokens"
```

### Use Case 2: Cost Optimization

```bash
# Default: Opus for high quality
CLAUDE_MODEL=claude-opus-4-6

# User wants to reduce costs for simple tasks
/model claude-sonnet-4-6
User: "Run tests"

# Back to default for important work
/model default
User: "Refactor the authentication module"
```

### Use Case 3: Model Comparison

```bash
# Test same prompt with different models
/model claude-opus-4-6
User: "Explain dependency injection"

/model claude-sonnet-4-6
User: "Explain dependency injection"

/model claude-haiku-4-5
User: "Explain dependency injection"
```

## Limitations

1. **Session Scope**: Model selection doesn't persist across bot restarts
2. **No Per-Project Models**: Model is user-wide, not per-project/thread
3. **No History**: Previous model selections are not tracked
4. **Validation**: If `ANTHROPIC_MODELS` is set, models outside the list are rejected

## Future Enhancements

Possible improvements for future versions:

1. **Persistent Model Selection**: Store user preference in database
2. **Per-Project Models**: Allow different models per project/thread
3. **Model Presets**: Define named presets (e.g., "fast", "balanced", "quality")
4. **Cost Estimation**: Show estimated cost before switching models
5. **Model Stats**: Track usage and costs per model
6. **Smart Suggestions**: Suggest appropriate model based on task complexity

## Troubleshooting

### Issue: "Model not in available list"

**Cause:** Trying to use a model not listed in `ANTHROPIC_MODELS`

**Solution:** Either:
- Add the model to `ANTHROPIC_MODELS` in `.env`
- Remove `ANTHROPIC_MODELS` to allow any model name

### Issue: Model doesn't seem to change

**Cause:** Session not refreshed or model override not working

**Solution:**
1. Check `/model` shows the correct current model
2. Try `/model default` then set again
3. Use `/new` to start fresh session
4. Check logs for SDK errors

### Issue: Invalid model name

**Cause:** Model name doesn't exist in Claude API

**Solution:** Use one of:
- `claude-opus-4-6` (most capable)
- `claude-sonnet-4-6` (balanced)
- `claude-haiku-4-5` (fast, affordable)

## Related Configuration

- `CLAUDE_MODEL`: Default model for all users
- `CLAUDE_MAX_COST_PER_REQUEST`: Budget cap (applies to all models)
- `CLAUDE_MAX_TURNS`: Turn limit (applies to all models)
- `ANTHROPIC_API_KEY`: API key (required for SDK mode)
- `ANTHROPIC_BASE_URL`: Custom endpoint (optional)

## References

- [Anthropic Model Documentation](https://docs.anthropic.com/en/docs/models-overview)
- [Claude Code Settings](./CLAUDE.md#configuration)
- [Bot Commands](./CLAUDE.md#adding-a-new-bot-command)
