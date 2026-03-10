# Before & After: Model Switching UI

## ❌ BEFORE (Text-only)

### User sends: `/model`

```
Current model: default

Available models:
  • claude-opus-4-6
  • claude-sonnet-4-6
  • claude-haiku-4-5

Usage: /model <model-name>
Example: /model claude-opus-4-6

Use /model default to reset to config default.
```

**Problems:**
- ❌ User has to type exact model name
- ❌ Risk of typos
- ❌ Need to remember full model string
- ❌ Multiple steps (read, type, send)
- ❌ Not mobile-friendly

### To switch model:
```
User types: /model claude-sonnet-4-6
         → Easy to make typo!
         → Need to copy-paste or remember
```

---

## ✅ AFTER (Inline Keyboard)

### User sends: `/model`

```
┌─────────────────────────────────────────┐
│ Select Model                             │
│                                          │
│ Current: claude-opus-4-6                │
│                                          │
│   • claude-opus-4-6 ◀                   │
│   • claude-sonnet-4-6                   │
│   • claude-haiku-4-5                    │
│                                          │
│  ┌──────────────────────────┐           │
│  │   claude-opus-4-6        │  ← Tap    │
│  └──────────────────────────┘           │
│  ┌──────────────────────────┐           │
│  │   claude-sonnet-4-6      │  ← Tap    │
│  └──────────────────────────┘           │
│  ┌──────────────────────────┐           │
│  │   claude-haiku-4-5       │  ← Tap    │
│  └──────────────────────────┘           │
│  ┌──────────────────────────┐           │
│  │   🔄 Reset to Default    │  ← Tap    │
│  └──────────────────────────┘           │
└─────────────────────────────────────────┘
```

**Benefits:**
- ✅ One-tap selection
- ✅ No typing required
- ✅ No typo errors
- ✅ Visual current model indicator (◀)
- ✅ Quick reset button
- ✅ Mobile-friendly
- ✅ Faster workflow

### To switch model:
```
User taps: [claude-sonnet-4-6] button
         → Instant switch!
         → No typing needed!
```

---

## Side-by-Side Comparison

| Feature | Before (Text) | After (Keyboard) |
|---------|--------------|------------------|
| **Steps to switch** | 3 steps (read → type → send) | 1 step (tap) |
| **Typing required** | Yes, full model name | No |
| **Typo risk** | High | None |
| **Mobile UX** | Poor (small keyboard) | Excellent (large buttons) |
| **Visual indicator** | No | Yes (◀ marker) |
| **Reset option** | Type "/model default" | Tap reset button |
| **Speed** | Slow | Fast |
| **Error-prone** | Yes (typos) | No (valid options only) |

---

## Real-World Usage Example

### Scenario: Quick testing with different models

**BEFORE (Text):**
```
User: /model
Bot: [Shows list]
User: /model claude-haiku-4-5     ← Type full name
Bot: ✅ Model switched to: claude-haiku-4-5
User: Run tests
Bot: [Response from Haiku]

User: /model claude-opus-4-6      ← Type full name again
Bot: ✅ Model switched to: claude-opus-4-6
User: Review the code
Bot: [Response from Opus]

⏱️ Time: ~10-15 seconds per switch
```

**AFTER (Keyboard):**
```
User: /model
Bot: [Shows buttons]
User: [Taps claude-haiku-4-5]     ← One tap!
Bot: ✅ Model switched to: claude-haiku-4-5
User: Run tests
Bot: [Response from Haiku]

User: /model
Bot: [Shows buttons]
User: [Taps claude-opus-4-6]      ← One tap!
Bot: ✅ Model switched to: claude-opus-4-6
User: Review the code
Bot: [Response from Opus]

⏱️ Time: ~2-3 seconds per switch
```

**Result:** 5x faster! 🚀

---

## Technical Implementation

### Callback Pattern
```python
# Old: Manual string parsing
if message.text == "/model claude-opus-4-6":
    # Complex parsing logic

# New: Callback data pattern
callback_data = "model:claude-opus-4-6"
prefix, model_name = callback_data.split(":", 1)
# Clean, simple, reliable
```

### Button Layout
```python
# Build keyboard (1 button per row for clarity)
keyboard_rows = []
for model_name in available_models:
    keyboard_rows.append([
        InlineKeyboardButton(
            model_name,
            callback_data=f"model:{model_name}"
        )
    ])

# Add reset button if user has override
if context.user_data.get("selected_model"):
    keyboard_rows.append([
        InlineKeyboardButton(
            "🔄 Reset to Default",
            callback_data="model:default"
        )
    ])
```

### Callback Handler
```python
async def _agentic_callback(self, update, context):
    query = update.callback_query
    await query.answer()

    prefix, value = query.data.split(":", 1)

    if prefix == "model":
        if value == "default":
            context.user_data.pop("selected_model", None)
        else:
            context.user_data["selected_model"] = value

        await query.edit_message_text(
            f"✅ Model switched to: {value}"
        )
```

---

## Consistency with `/repo` Command

The new `/model` UI follows the same pattern as the existing `/repo` command:

| Command | Callback Pattern | Display Style |
|---------|-----------------|---------------|
| `/repo` | `cd:{directory}` | Inline keyboard with indicators |
| `/model` | `model:{model}` | Inline keyboard with indicators |

This creates a **consistent user experience** across the bot! 🎯
