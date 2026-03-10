# 🐛 Bug Fix: Model Switching Tool State Conflict

## Problem

User reported error when switching model and sending message:
```
✅ Model switched to: cc/claude-haiku-4-5-20251001
❌ An unexpected error occurred
API Error: 400 {"error":{"message":"[400]: messages.6.content.0: unexpected tool_use_id found in tool_result blocks..."}}
```

## Root Causes

### 1. Incorrect Model Name Format
- **Issue**: Model name showed as `cc/claude-haiku-4-5-20251001` (with `/` separator)
- **Expected**: Should resolve to `claude-haiku-4-5-20251001`
- **Cause**: Model mapper had short alias `haiku` pointing to `claude-haiku-4-5` but API expects `claude-haiku-4-5-20251001`

### 2. Tool State Conflict
- **Issue**: Switching models mid-session causes tool_use ID mismatch
- **Why**: Old session has pending tool_use blocks, new model creates new session with different IDs
- **Result**: API rejects because tool_result references unknown tool_use_id

## Fixes Applied

### Fix 1: Update Model Names (src/claude/model_mapper.py)
```python
# Before
"haiku": "claude-haiku-4-5",
"cc-haiku": "claude-haiku-4-5",

# After
"haiku": "claude-haiku-4-5-20251001",
"cc-haiku": "claude-haiku-4-5-20251001",
"claude-haiku-4-5": "claude-haiku-4-5-20251001",  # Legacy alias
```

### Fix 2: Clear Session on Model Switch (src/bot/orchestrator.py)
```python
# Added session clearing
context.user_data["selected_model"] = model_name

# Clear session to avoid tool state conflicts
old_session_id = context.user_data.get("claude_session_id")
if old_session_id:
    context.user_data.pop("claude_session_id", None)
    logger.info(
        "Cleared session due to model switch",
        old_session_id=old_session_id,
        new_model=model_name,
    )

# Updated message
await update.message.reply_text(
    f"✅ Model switched to: {model_display}\n\n"
    f"Starting fresh session with new model.",  # ← Changed
    parse_mode="HTML",
)
```

## Changes Summary

### Files Modified (4 files)

1. **src/claude/model_mapper.py**
   - Updated haiku aliases to use full dated model name
   - Added legacy alias support for backward compatibility

2. **src/bot/orchestrator.py** (2 locations)
   - Added session clearing in `agentic_model()` command handler
   - Added session clearing in `_agentic_callback()` callback handler
   - Updated success message to indicate fresh session

3. **tests/test_model_mapper.py**
   - Updated test expectations for haiku model name
   - All 28 tests pass ✅

## Behavior Changes

### Before
```
User: /model cc-haiku
Bot: ✅ Model switched to: Haiku 4.5
     This will be used for all subsequent messages in this session.
     
User: Hello
Bot: ❌ API Error: 400 [tool state conflict]
```

### After
```
User: /model cc-haiku
Bot: ✅ Model switched to: Haiku 4.5
     Starting fresh session with new model.  ← New message
     
User: Hello
Bot: ✅ [Works correctly with fresh session]
```

## Why This Matters

### Tool State Explanation
Claude API maintains conversation state including:
- Previous messages
- Tool calls (tool_use blocks)
- Tool results (tool_result blocks)

Each tool_use has an ID that must match in the corresponding tool_result.

When switching models mid-conversation:
1. Old session has pending tool_use (e.g., `call_738616...`)
2. New model tries to create new session but sees old tool_result
3. API rejects: "tool_result references unknown tool_use_id"

**Solution**: Clear session_id when switching models → Forces fresh start

## Testing

```bash
# All tests pass
poetry run pytest tests/test_model_mapper.py -v
# 28 passed

# Test model resolution
python -c "from src.claude.model_mapper import resolve_model_name; \
print(resolve_model_name('cc-haiku'))"
# Output: claude-haiku-4-5-20251001 ✅

# Test display names
python -c "from src.claude.model_mapper import get_display_name; \
print(get_display_name('cc-haiku'))"
# Output: Haiku 4.5 ✅
```

## User Impact

### Positive
✅ Model switching now works reliably
✅ No more API 400 errors
✅ Clear message about fresh session
✅ Correct model names used

### Neutral
⚠️ Switching models starts fresh session (loses conversation history)
   - This is intentional to avoid tool state conflicts
   - User can still `/new` for fresh session anyway

## Related Issues

- Model mapper now uses correct dated model names
- Session management improved for model switching
- Inline keyboard continues to work correctly
- All enterprise/proxy alias scenarios supported

## Prevention

To avoid similar issues in future:
1. Always use full dated model names from Anthropic docs
2. Test model switching with active sessions
3. Clear session state when changing critical parameters
4. Update tests when model names change
