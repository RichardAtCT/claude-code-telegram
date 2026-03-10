# Model Name Mapper

## Overview

The model mapper automatically resolves short aliases to full Anthropic model names, making it easier to work with enterprise/proxy endpoints that use custom naming schemes.

## Supported Aliases

### Claude 4.6 (Latest)
| Alias | Full Name |
|-------|-----------|
| `opus` | `claude-opus-4-6` |
| `cc-opus` | `claude-opus-4-6` |
| `opus-4.6` | `claude-opus-4-6` |
| `claude-opus` | `claude-opus-4-6` |
| `sonnet` | `claude-sonnet-4-6` |
| `cc-sonnet` | `claude-sonnet-4-6` |
| `sonnet-4.6` | `claude-sonnet-4-6` |
| `claude-sonnet` | `claude-sonnet-4-6` |

### Claude 4.5
| Alias | Full Name |
|-------|-----------|
| `haiku` | `claude-haiku-4-5` |
| `cc-haiku` | `claude-haiku-4-5` |
| `haiku-4.5` | `claude-haiku-4-5` |
| `claude-haiku` | `claude-haiku-4-5` |

### Claude 3.5 (Legacy)
| Alias | Full Name |
|-------|-----------|
| `sonnet-3.5` | `claude-3-5-sonnet-20241022` |
| `haiku-3.5` | `claude-3-5-haiku-20241022` |

## How It Works

### 1. Configuration
```bash
# Option A: Use short aliases (easier to type)
ANTHROPIC_MODELS=cc-opus,cc-sonnet,cc-haiku

# Option B: Use full names (explicit)
ANTHROPIC_MODELS=claude-opus-4-6,claude-sonnet-4-6,claude-haiku-4-5

# Option C: Mix both (flexible)
ANTHROPIC_MODELS=opus,claude-sonnet-4-6,cc-haiku
```

### 2. User Interface
When user sends `/model`:

```
Select Model

Current: Opus 4.6

  • Opus 4.6 (cc-opus) ◀
  • Sonnet 4.6 (cc-sonnet)
  • Haiku 4.5 (cc-haiku)

[cc-opus]      ← Button
[cc-sonnet]    ← Button
[cc-haiku]     ← Button
```

**Benefits:**
- Shows friendly display names: "Opus 4.6" instead of "claude-opus-4-6"
- Shows actual model string in parentheses for clarity
- User can click any alias, all resolve to correct model

### 3. Resolution Flow
```
User action          → Model mapper        → Claude SDK
──────────────────────────────────────────────────────────
/model cc-opus       → claude-opus-4-6     → Uses Opus 4.6
/model sonnet        → claude-sonnet-4-6   → Uses Sonnet 4.6
/model opus-4.6      → claude-opus-4-6     → Uses Opus 4.6
/model custom-xyz    → custom-xyz          → Passes through
```

## Use Cases

### Use Case 1: Enterprise Proxy
```bash
# Enterprise uses "cc-" prefix for all models
ANTHROPIC_BASE_URL=https://claude.enterprise.com/v1
ANTHROPIC_MODELS=cc-opus,cc-sonnet,cc-haiku

# User sees friendly names but backend uses correct API names
/model → Shows "Opus 4.6", "Sonnet 4.6", "Haiku 4.5"
Click → Sends "claude-opus-4-6" to enterprise endpoint
```

### Use Case 2: Short Aliases
```bash
# Users prefer short names
ANTHROPIC_MODELS=opus,sonnet,haiku

# Easier to type: /model opus
# Instead of:     /model claude-opus-4-6
```

### Use Case 3: Mixed Configuration
```bash
# Allow both enterprise aliases and direct names
ANTHROPIC_MODELS=cc-opus,claude-sonnet-4-6,haiku

# All resolve correctly:
cc-opus           → claude-opus-4-6
claude-sonnet-4-6 → claude-sonnet-4-6 (pass-through)
haiku             → claude-haiku-4-5
```

### Use Case 4: Custom Models
```bash
# Mix standard and custom models
ANTHROPIC_MODELS=opus,my-fine-tuned-claude

# Standard alias resolves, custom name passes through:
opus               → claude-opus-4-6
my-fine-tuned-claude → my-fine-tuned-claude (unchanged)
```

## API Reference

### Functions

#### `resolve_model_name(model_input: Optional[str]) -> Optional[str]`
Resolve alias to full Anthropic model name.

```python
>>> from src.claude.model_mapper import resolve_model_name
>>> resolve_model_name("cc-opus")
'claude-opus-4-6'
>>> resolve_model_name("claude-opus-4-6")  # Already full name
'claude-opus-4-6'
>>> resolve_model_name("custom-model")  # Unknown, passes through
'custom-model'
```

#### `get_display_name(model_name: Optional[str]) -> str`
Get user-friendly display name.

```python
>>> from src.claude.model_mapper import get_display_name
>>> get_display_name("cc-opus")
'Opus 4.6'
>>> get_display_name("claude-sonnet-4-6")
'Sonnet 4.6'
>>> get_display_name("custom-model")
'custom-model'
```

#### `is_valid_model_alias(model_input: str) -> bool`
Check if string is a known alias.

```python
>>> from src.claude.model_mapper import is_valid_model_alias
>>> is_valid_model_alias("cc-opus")
True
>>> is_valid_model_alias("claude-opus-4-6")  # Full name, not alias
False
```

## Display Names

The mapper provides friendly display names for the UI:

| Full Model Name | Display Name |
|-----------------|--------------|
| `claude-opus-4-6` | `Opus 4.6` |
| `claude-sonnet-4-6` | `Sonnet 4.6` |
| `claude-haiku-4-5` | `Haiku 4.5` |
| `claude-3-5-sonnet-20241022` | `Sonnet 3.5` |
| `claude-3-5-haiku-20241022` | `Haiku 3.5` |

## Implementation Details

### Resolution Happens in SDK Layer
```python
# User selection stored as-is
context.user_data["selected_model"] = "cc-opus"

# Resolution happens when calling Claude SDK
effective_model = resolve_model_name(user_model)  # → "claude-opus-4-6"
ClaudeAgentOptions(model=effective_model)
```

**Why?**
- User can type any alias
- Config can use any naming scheme
- SDK always receives correct full name
- Custom models pass through unchanged

### Case-Insensitive Matching
```python
resolve_model_name("CC-OPUS")   # → claude-opus-4-6
resolve_model_name("Sonnet")    # → claude-sonnet-4-6
resolve_model_name("HAIKU")     # → claude-haiku-4-5
```

### Whitespace Trimming
```python
resolve_model_name("  opus  ")   # → claude-opus-4-6
resolve_model_name("\topus\n")   # → claude-opus-4-6
```

## Testing

```bash
# Run model mapper tests
poetry run pytest tests/test_model_mapper.py -v

# Test specific scenario
poetry run pytest tests/test_model_mapper.py::TestEndToEndScenarios::test_enterprise_proxy_scenario -v
```

All 28 tests pass ✅

## Logging

The mapper logs resolution for debugging:

```python
logger.debug(
    "Resolved model alias",
    input="cc-opus",
    resolved="claude-opus-4-6",
)
```

Set `LOG_LEVEL=DEBUG` to see resolution logs.

## Adding New Models

To add support for new Claude models:

1. **Update `MODEL_ALIASES` dict** in `src/claude/model_mapper.py`:
   ```python
   MODEL_ALIASES = {
       # ... existing aliases ...
       "opus-5": "claude-opus-5-0",
       "cc-opus-5": "claude-opus-5-0",
   }
   ```

2. **Update `MODEL_DISPLAY_NAMES` dict**:
   ```python
   MODEL_DISPLAY_NAMES = {
       # ... existing names ...
       "claude-opus-5-0": "Opus 5.0",
   }
   ```

3. **Add tests** in `tests/test_model_mapper.py`:
   ```python
   def test_opus_5_alias(self):
       assert resolve_model_name("opus-5") == "claude-opus-5-0"
       assert get_display_name("opus-5") == "Opus 5.0"
   ```

4. **Run tests**:
   ```bash
   poetry run pytest tests/test_model_mapper.py -v
   ```

## Troubleshooting

### Issue: Alias not resolving
**Symptom:** `cc-opus` shows as literal "cc-opus" instead of "Opus 4.6"

**Cause:** Mapper not integrated or alias not in dict

**Solution:**
1. Check `MODEL_ALIASES` dict has the alias
2. Verify `resolve_model_name()` is called in SDK integration
3. Check logs for resolution messages

### Issue: Custom model rejected
**Symptom:** Enterprise model "my-model" rejected as invalid

**Cause:** Validation checks resolved name against allowed list

**Solution:**
```bash
# Add to ANTHROPIC_MODELS (it will pass through)
ANTHROPIC_MODELS=opus,sonnet,my-model
```

### Issue: Wrong model used
**Symptom:** Selected "cc-opus" but Sonnet responded

**Cause:** Resolution not working

**Solution:**
1. Check SDK logs: `LOG_LEVEL=DEBUG`
2. Look for "Resolved model alias" log entry
3. Verify `effective_model` passed to Claude SDK

## Best Practices

### ✅ Do
- Use short aliases in config for readability
- Mix aliases and full names as needed
- Add custom enterprise models to config
- Use `cc-` prefix for enterprise consistency

### ❌ Don't
- Don't use full names if aliases exist (harder to read)
- Don't assume unknown aliases will resolve (they pass through)
- Don't modify MODEL_ALIASES without updating tests

## Examples

### Example 1: Standard Setup
```bash
ANTHROPIC_MODELS=opus,sonnet,haiku
```

### Example 2: Enterprise Setup
```bash
ANTHROPIC_BASE_URL=https://claude-proxy.company.com/v1
ANTHROPIC_MODELS=cc-opus,cc-sonnet,cc-haiku
```

### Example 3: Mixed Setup
```bash
ANTHROPIC_MODELS=opus,claude-sonnet-4-6,cc-haiku,custom-model-v2
```

### Example 4: Legacy Support
```bash
# Support both 3.5 and 4.x models
ANTHROPIC_MODELS=opus,sonnet,haiku,sonnet-3.5,haiku-3.5
```

## Related Documentation

- [Model Switching Feature](MODEL_SWITCHING.md)
- [Anthropic Models Documentation](https://docs.anthropic.com/en/docs/about-claude/models)
- [Configuration Guide](CLAUDE.md#configuration)
