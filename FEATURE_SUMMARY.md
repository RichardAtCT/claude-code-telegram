# Feature Summary: Model Switching with Inline Keyboard

## ✅ Implemented

### 1. Environment Variable
- **`ANTHROPIC_MODELS`**: Comma-separated list of available models
- Example: `ANTHROPIC_MODELS=claude-opus-4-6,claude-sonnet-4-6,claude-haiku-4-5`

### 2. Telegram Command: `/model`
- **No arguments** → Shows inline keyboard with clickable model buttons
- **With argument** → Direct model switch (e.g., `/model claude-sonnet-4-6`)

### 3. Inline Keyboard UI (giống `/repo`)
```
┌─────────────────────────────────┐
│ Select Model                     │
│                                  │
│ Current: claude-opus-4-6        │
│                                  │
│   • claude-opus-4-6 ◀           │
│   • claude-sonnet-4-6           │
│   • claude-haiku-4-5            │
│                                  │
│  ┌──────────────────────┐       │
│  │  claude-opus-4-6     │       │
│  └──────────────────────┘       │
│  ┌──────────────────────┐       │
│  │  claude-sonnet-4-6   │       │
│  └──────────────────────┘       │
│  ┌──────────────────────┐       │
│  │  claude-haiku-4-5    │       │
│  └──────────────────────┘       │
│  ┌──────────────────────┐       │
│  │  🔄 Reset to Default │       │
│  └──────────────────────┘       │
└─────────────────────────────────┘
```

### 4. Quick Select (Click Button)
- User clicks button → Model switches instantly
- Message updates to: "✅ Model switched to: claude-sonnet-4-6"
- No need to type model name

## Architecture Changes

### Files Modified (6 files, +199 lines)

1. **`src/config/settings.py`** (+8 lines)
   - Added `anthropic_models: Optional[List[str]]`
   - Parse comma-separated model list

2. **`src/claude/facade.py`** (+5 lines)
   - Added `model` parameter to `run_command()`

3. **`src/claude/sdk_integration.py`** (+10 lines)
   - Added `model` parameter to `execute_command()`
   - Uses `effective_model = model or config.claude_model`

4. **`src/bot/orchestrator.py`** (+167 lines)
   - Added `_get_selected_model()` helper
   - Updated `agentic_model()` to build inline keyboard
   - Updated `_agentic_callback()` to handle `model:` callbacks
   - Updated callback handler pattern: `^(cd|model):`

5. **`.env.example`** (+5 lines)
   - Added `ANTHROPIC_MODELS` documentation

6. **`CLAUDE.md`** (+4 lines)
   - Updated command list and configuration docs

### Callback Pattern

```python
# Button callback data
"model:claude-opus-4-6"   → Switch to Opus
"model:claude-sonnet-4-6" → Switch to Sonnet
"model:default"           → Reset to config default

# Handler pattern
pattern=r"^(cd|model):"   → Matches both cd: and model: callbacks
```

### State Management

```python
# Store user's selected model
context.user_data["selected_model"] = "claude-sonnet-4-6"

# Get effective model (user override or config default)
def _get_selected_model(context):
    user_override = context.user_data.get("selected_model")
    if user_override is not None:
        return str(user_override)
    return self.settings.claude_model
```

## User Experience Flow

### Flow 1: Quick Select (Inline Keyboard)
```
1. User: /model
2. Bot: Shows inline keyboard with all models
3. User: [Clicks "claude-sonnet-4-6" button]
4. Bot: "✅ Model switched to: claude-sonnet-4-6"
5. User: "Write hello world"
6. Claude: [Uses Sonnet to respond]
```

### Flow 2: Direct Command
```
1. User: /model claude-haiku-4-5
2. Bot: "✅ Model switched to: claude-haiku-4-5"
3. User: "Run tests"
4. Claude: [Uses Haiku to respond]
```

### Flow 3: Reset to Default
```
1. User: /model
2. Bot: Shows inline keyboard
3. User: [Clicks "🔄 Reset to Default" button]
4. Bot: "✅ Model reset to default: claude-opus-4-6"
```

## Comparison with `/repo` Command

| Feature | `/repo` | `/model` |
|---------|---------|----------|
| **Display** | List of directories | List of models |
| **Callback** | `cd:{name}` | `model:{name}` |
| **Indicator** | `◀` for current | `◀` for current |
| **Extra Button** | None | "🔄 Reset to Default" |
| **Layout** | 2 buttons per row | 1 button per row |
| **Icons** | 📦 (git) / 📁 (folder) | None (model names) |

## Benefits

✅ **No typing** - Click to select, no need to remember exact model names
✅ **Visual feedback** - Current model marked with `◀`
✅ **Quick reset** - One-click return to default
✅ **Consistent UX** - Same pattern as `/repo` command
✅ **Mobile-friendly** - Large tappable buttons
✅ **Error prevention** - Can only select from valid models

## Configuration Examples

### Example 1: All Claude 4 models
```bash
ANTHROPIC_MODELS=claude-opus-4-6,claude-sonnet-4-6,claude-haiku-4-5
```

### Example 2: Short aliases
```bash
ANTHROPIC_MODELS=opus,sonnet,haiku
CLAUDE_MODEL=opus  # Default
```

### Example 3: No configuration (allow any model name)
```bash
# Leave ANTHROPIC_MODELS unset
# Users can type any model name: /model claude-3-5-sonnet-20241022
```

## Testing

All tests pass:
- ✅ Configuration parsing (comma-separated, single, with spaces)
- ✅ Inline keyboard generation (rows, buttons, reset button)
- ✅ Callback data patterns (`model:` prefix)
- ✅ User selection logic (default, override, reset)
- ✅ Code formatting (black, isort)

## Next Steps

1. **Add to `.env`**:
   ```bash
   ANTHROPIC_MODELS=claude-opus-4-6,claude-sonnet-4-6,claude-haiku-4-5
   ```

2. **Restart bot**:
   ```bash
   make run
   ```

3. **Test in Telegram**:
   - Send `/model`
   - Click a model button
   - Send a message to Claude
   - Verify correct model is used

## Future Enhancements

- 🔮 Model icons/emojis (🧠 Opus, ⚡ Sonnet, 🏃 Haiku)
- 🔮 Show cost estimate per model
- 🔮 Recent models quick access
- 🔮 Per-project default models
- 🔮 Model usage statistics
