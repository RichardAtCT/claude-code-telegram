# SDK Duplication & Over-Complication Review

**Date:** 2026-02-19
**SDK Version:** `claude-agent-sdk v0.1.31`
**Codebase Module:** `src/claude/` (2,774 lines across 8 files)

This document captures the findings from a deep review of the `src/claude/` module
against the actual capabilities of the Claude Agent SDK. The goal is to identify
where we're duplicating SDK functionality, over-complicating things, or missing
native features that would simplify the codebase.

The SDK reference used: https://platform.claude.com/docs/en/agent-sdk/python

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Finding 1: Using `query()` Instead of `ClaudeSDKClient`](#finding-1-using-query-instead-of-claudesdkclient)
3. [Finding 2: Tool Validation Duplicates `can_use_tool` and Hooks](#finding-2-tool-validation-duplicates-can_use_tool-and-hooks)
4. [Finding 3: Dual Backend (SDK + CLI Subprocess)](#finding-3-dual-backend-sdk--cli-subprocess)
5. [Finding 4: No Use of `max_budget_usd`](#finding-4-no-use-of-max_budget_usd)
6. [Finding 5: Manual `disallowed_tools` Checking](#finding-5-manual-disallowed_tools-checking)
7. [Finding 6: Bash Pattern Blocklist vs Sandbox + `can_use_tool`](#finding-6-bash-pattern-blocklist-vs-sandbox--can_use_tool)
8. [Finding 7: CLI Path Discovery](#finding-7-cli-path-discovery)
9. [Finding 8: Manual Content Extraction vs `ResultMessage.result`](#finding-8-manual-content-extraction-vs-resultmessageresult)
10. [Finding 9: Dead In-Memory Session State](#finding-9-dead-in-memory-session-state)
11. [Estimated Line Reduction](#estimated-line-reduction)
12. [Recommended Refactor Order](#recommended-refactor-order)
13. [Migration Risks](#migration-risks)

---

## Executive Summary

Approximately **61% (~1,700 lines)** of the `src/claude/` module duplicates or
works around functionality the SDK already provides natively. The three highest
impact issues are:

1. Using the stateless `query()` API then building session management on top,
   when `ClaudeSDKClient` provides stateful multi-turn conversations natively.
2. Implementing reactive tool validation during streaming, when the SDK's
   `can_use_tool` callback blocks tools **before** execution.
3. Maintaining a full CLI subprocess fallback backend that duplicates everything
   the SDK does.

---

## Finding 1: Using `query()` Instead of `ClaudeSDKClient`

**Impact: HIGH** | **Files: `session.py`, `facade.py`, `sdk_integration.py`**

### What the SDK provides

The SDK has two APIs (see [official comparison table](https://platform.claude.com/docs/en/agent-sdk/python)):

| Feature | `query()` | `ClaudeSDKClient` |
|---------|-----------|-------------------|
| Session | New each time | Reuses same session |
| Conversation | Single exchange | Multiple exchanges in same context |
| Interrupts | Not supported | Supported |
| Hooks | Not supported | Supported |
| Custom Tools | Not supported | Supported |
| Continue Chat | New session each time | Maintains conversation |

`ClaudeSDKClient` is purpose-built for our use case:

```python
async with ClaudeSDKClient(options) as client:
    await client.query("first message")
    async for msg in client.receive_response():
        process(msg)

    # Follow-up -- Claude remembers everything above
    await client.query("follow up question")
    async for msg in client.receive_response():
        process(msg)
```

### What we do instead

We use `query()` (the one-shot API) and then build a 340-line `SessionManager`
on top of it:

- **Temporary session IDs** (`session.py:204-215`): We generate `temp_*` UUIDs
  because we don't have a session ID until Claude responds.
- **Session ID swapping** (`session.py:236-257`): After the first response, we
  delete the temp session and re-store under Claude's real ID.
- **Resume logic** (`facade.py:149-155`): Complex checks for `is_new_session`,
  `temp_*` prefix detection, and conditional `options.resume` passing.
- **Auto-resume search** (`facade.py:349-374`): Scans all user sessions to find
  one matching the current directory.
- **Stale session retry** (`facade.py:165-192`): If resume fails with "no
  conversation found", catches the error, cleans up, and retries fresh.
- **In-memory + SQLite dual storage**: Sessions are kept in both
  `SessionManager.active_sessions` dict and `SessionStorage` (SQLite).
- **Abstract `SessionStorage` base class** + `InMemorySessionStorage`
  implementation that exists for testing but adds indirection.

### What the refactor looks like

With `ClaudeSDKClient`:

- No temporary session IDs needed (client manages its own session)
- No session swapping logic
- No resume/retry dance
- Session ID is available immediately from any `ResultMessage`
- Only need thin persistence: store `{user_id, directory, session_id}` in SQLite
  so we can resume across bot restarts via `options.resume`

### Lines affected

- `session.py`: ~250 of 340 lines removable (keep `ClaudeSession` dataclass as
  thin storage model, remove `SessionStorage` ABC, `InMemorySessionStorage`,
  most of `SessionManager`)
- `facade.py`: ~80 lines of session orchestration removable
- `sdk_integration.py`: session-related code simplifies

---

## Finding 2: Tool Validation Duplicates `can_use_tool` and Hooks

**Impact: HIGH** | **Files: `monitor.py`, `facade.py`**

### What the SDK provides

The SDK has a native permission evaluation pipeline:

```
Hooks → Deny Rules → Allow Rules → Ask Rules → Permission Mode → can_use_tool callback
```

The `can_use_tool` callback runs **before** a tool executes and can deny or
modify the call:

```python
async def permission_handler(tool_name, input_data, context):
    if tool_name == "Write" and "/system/" in input_data.get("file_path", ""):
        return PermissionResultDeny(message="System dir write blocked", interrupt=True)

    if tool_name == "Bash":
        cmd = input_data.get("command", "")
        ok, err = check_boundary(cmd, working_dir, approved_dir)
        if not ok:
            return PermissionResultDeny(message=err)

    return PermissionResultAllow(updated_input=input_data)

options = ClaudeAgentOptions(
    can_use_tool=permission_handler,
    allowed_tools=["Read", "Write", "Bash"],
    disallowed_tools=["WebFetch"],
)
```

Key capabilities:
- **Pre-execution**: Blocks tools before they run (not after)
- **Input modification**: Can rewrite tool inputs (e.g. redirect paths)
- **`allowed_tools`/`disallowed_tools`**: Declarative tool filtering
- **`PermissionResultDeny.interrupt`**: Can halt the entire execution
- **`PreToolUse` hooks**: Even more granular control with pattern matching

### What we do instead

**`ToolMonitor` class** (`monitor.py`, 333 lines):
- `validate_tool_call()` (lines 145-281): Checks allowed/disallowed tools,
  validates file paths via `SecurityValidator`, scans bash commands for dangerous
  patterns, checks directory boundaries.
- `check_bash_directory_boundary()` (lines 69-130): Parses bash with `shlex`,
  categorizes commands as read-only vs modifying, resolves paths.
- In-memory `tool_usage` counter and `security_violations` list.
- `get_tool_stats()`, `get_security_violations()`, `get_user_tool_usage()`.

**Facade streaming interception** (`facade.py:93-138`):
- Wraps the stream callback to intercept `StreamUpdate` objects
- Validates tool calls **during** streaming (reactive, not preventive)
- On validation failure, raises `ClaudeToolValidationError` — but the tool may
  have already started executing

**Error message generation** (`facade.py:471-568`):
- `_get_admin_instructions()`: 60 lines generating `.env` configuration hints
- `_create_tool_error_message()`: 37 lines formatting blocked-tool messages

### Critical issue

The current approach is **reactive**: it validates during streaming, meaning
the tool call has already been sent to Claude by the time we check it. The SDK's
`can_use_tool` is **preventive**: it blocks before execution.

### What the refactor looks like

1. Create a single `can_use_tool` callback that encapsulates:
   - Path validation (from `SecurityValidator`)
   - Directory boundary checks (from `check_bash_directory_boundary`)
   - Any remaining custom security logic
2. Pass `allowed_tools` and `disallowed_tools` directly to `ClaudeAgentOptions`
3. Remove `ToolMonitor` class entirely
4. Remove streaming interception from facade
5. If tool usage analytics are needed, use a `PostToolUse` hook instead of
   in-memory counters

### Lines affected

- `monitor.py`: ~280 of 333 lines removable (keep `check_bash_directory_boundary`
  as a utility if needed by the `can_use_tool` callback)
- `facade.py`: ~145 lines of interception + error messaging removable

---

## Finding 3: Dual Backend (SDK + CLI Subprocess)

**Impact: HIGH** | **Files: `integration.py`, `parser.py`, `facade.py`**

### The current architecture

```
facade.py (ClaudeIntegration)
├── sdk_integration.py (ClaudeSDKManager)     -- Primary, 513 lines
├── integration.py (ClaudeProcessManager)     -- Fallback, 594 lines
└── parser.py (OutputParser)                  -- CLI JSON parsing, 338 lines
```

The facade (`_execute_with_fallback`, lines 267-347) tries the SDK first and
falls back to the CLI subprocess if it catches:
- `"Failed to decode JSON"` / `"JSON decode error"`
- `"TaskGroup"` / `"ExceptionGroup"`
- `"Unknown message type"`

### Why this is problematic

1. **Code duplication** — both backends implement the same abstractions:

   | Concept | SDK (`sdk_integration.py`) | CLI (`integration.py`) |
   |---------|--------------------------|----------------------|
   | `ClaudeResponse` dataclass | Lines 107-118 | Lines 33-43 |
   | `StreamUpdate` dataclass | Lines 121-128 | Lines 47-89 |
   | Text extraction | Lines 435-451 | Lines 388-416 |
   | Tool extraction | Lines 453-474 | Lines 528-544 |
   | Command building | SDK options | Lines 219-267 |
   | Stream parsing | Typed messages | Lines 299-386 (raw JSON) |

2. **Incompatible sessions** — fallback starts a fresh session (line 317:
   `session_id=None`), so context is lost on fallback.

3. **SDK bugs aren't our problem** — catching `CLIJSONDecodeError` and
   `ExceptionGroup` means we're papering over SDK bugs rather than reporting
   them. The SDK is actively maintained (v0.1.38 is latest, we're on v0.1.31).

4. **`OutputParser` exists only for CLI** — all 338 lines of `parser.py` parse
   raw JSON output from the subprocess. The SDK returns typed Python objects.

### What the refactor looks like

- Delete `integration.py` (594 lines)
- Delete `parser.py` (338 lines)
- Remove fallback logic from `facade.py` (~80 lines)
- Remove `ClaudeResponse`/`StreamUpdate` from `integration.py` (use SDK's types
  or a single shared definition)
- Upgrade to latest `claude-agent-sdk` to get fixes for JSON/TaskGroup issues

### Lines affected

- `integration.py`: All 594 lines removable
- `parser.py`: All 338 lines removable
- `facade.py`: ~80 lines of fallback logic removable

---

## Finding 4: No Use of `max_budget_usd`

**Impact: MEDIUM** | **Files: `session.py`, `sdk_integration.py`**

### What the SDK provides

```python
options = ClaudeAgentOptions(
    max_budget_usd=5.00,  # Hard cap per query
)
```

This is enforced by the SDK itself — the query stops if the budget is exceeded.

### What we do instead

Cost is tracked in **four places** with no enforcement:

1. `ClaudeSession.total_cost` — accumulated in `update_usage()` (session.py:52)
2. `ClaudeResponse.cost` — returned from both SDK and CLI backends
3. `ResultMessage.total_cost_usd` — SDK native field
4. SQLite `cost_tracking` table — historical storage

None of these **enforce** a limit. They only report after the fact.

### Recommendation

- Set `max_budget_usd` in `ClaudeAgentOptions` for per-query cost caps
- Keep SQLite tracking for historical reporting/dashboards
- Consider adding a config setting like `max_cost_per_query` that maps to this

---

## Finding 5: Manual `disallowed_tools` Checking

**Impact: MEDIUM** | **Files: `monitor.py`**

### What the SDK provides

```python
options = ClaudeAgentOptions(
    disallowed_tools=["WebFetch", "WebSearch"],  # Native support
)
```

The SDK enforces this before any tool executes.

### What we do instead

`ToolMonitor.validate_tool_call()` (monitor.py:176-190) manually checks:

```python
if hasattr(self.config, "claude_disallowed_tools") and self.config.claude_disallowed_tools:
    if tool_name in self.config.claude_disallowed_tools:
        return False, f"Tool explicitly disallowed: {tool_name}"
```

This is a reactive check during streaming, not a preventive block.

### Recommendation

Pass `config.claude_disallowed_tools` directly to `ClaudeAgentOptions.disallowed_tools`.

---

## Finding 6: Bash Pattern Blocklist vs Sandbox + `can_use_tool`

**Impact: MEDIUM** | **Files: `monitor.py`**

### The current approach

`ToolMonitor` (lines 228-258) blocks bash commands containing these substrings:

```python
dangerous_patterns = [
    "rm -rf", "sudo", "chmod 777", "curl", "wget",
    "nc ", "netcat", ">", ">>", "|", "&", ";", "$(", "`",
]
```

### Problems with substring matching

- **`>`** blocks all redirects — including `echo "hello" > file.txt`
- **`|`** blocks all pipes — including `grep pattern | sort`
- **`&`** blocks background processes and `&&` chaining
- **`;`** blocks multi-command lines — including `cd dir; ls`
- **`curl`/`wget`** may be legitimate for development work
- **`$(` and `` ` ``** blocks command substitution — including
  `echo "Today is $(date)"`

This effectively prevents Claude from doing useful shell work in many scenarios.

### What the SDK provides

1. **Sandbox** — OS-level isolation for filesystem and network
2. **`can_use_tool`** — semantic, pre-execution validation
3. **`PreToolUse` hooks** — pattern-matched interception with deny capability

### Recommendation

- Remove the substring blocklist
- Use `can_use_tool` for semantic validation (what is the command actually doing?)
- Rely on the sandbox for OS-level enforcement
- Keep `check_bash_directory_boundary()` as a utility for the `can_use_tool`
  callback — its approach (parsing with `shlex`, checking resolved paths) is
  more sound than substring matching

---

## Finding 7: CLI Path Discovery

**Impact: LOW** | **Files: `sdk_integration.py`**

### The current approach

`find_claude_cli()` (lines 46-86) searches:
- Config/env `CLAUDE_CLI_PATH`
- `shutil.which("claude")`
- `~/.nvm/versions/node/*/bin/claude`
- `~/.npm-global/bin/claude`
- `~/node_modules/.bin/claude`
- `/usr/local/bin/claude`, `/usr/bin/claude`
- `~/AppData/Roaming/npm/claude.cmd` (Windows)

`update_path_for_claude()` (lines 89-104) then modifies `os.environ["PATH"]`.

### What the SDK provides

`ClaudeAgentOptions.cli_path` — if set, the SDK uses it. Otherwise the SDK has
its own internal discovery.

### Recommendation

- Only set `cli_path` if explicitly configured
- Remove `find_claude_cli()` and `update_path_for_claude()` (~60 lines)
- If the SDK can't find the CLI, it raises `CLINotFoundError` — handle that with
  a helpful error message

---

## Finding 8: Manual Content Extraction vs `ResultMessage.result`

**Impact: LOW** | **Files: `sdk_integration.py`**

### The current approach

`_extract_content_from_messages()` (lines 435-451) iterates all messages and
joins `TextBlock.text` values from `AssistantMessage` objects.

### What the SDK provides

`ResultMessage` has a `result` field containing the final text output:

```python
for message in messages:
    if isinstance(message, ResultMessage):
        final_text = message.result  # Already available
```

### Recommendation

Use `ResultMessage.result` directly. Fall back to content extraction only if
`result` is `None`.

---

## Finding 9: Dead In-Memory Session State

**Impact: LOW** | **Files: `sdk_integration.py`**

### The current approach

`ClaudeSDKManager.active_sessions` (line 137) stores full message lists:

```python
self.active_sessions[session_id] = {
    "messages": messages,
    "created_at": ...,
    "last_used": ...,
}
```

This data is **never read back**. The only consumer is `kill_all_processes()`
which just calls `.clear()`, and `get_active_process_count()` which returns the
dict length.

### Recommendation

Remove `active_sessions`, `_update_session()`, and related methods (~20 lines).

---

## Estimated Line Reduction

| File | Current Lines | Removable | Reason |
|------|:---:|:---:|--------|
| `integration.py` | 594 | **594** | Entire CLI subprocess backend |
| `parser.py` | 338 | **338** | Only used by CLI subprocess |
| `session.py` | 340 | **~250** | Keep thin persistence model |
| `monitor.py` | 333 | **~280** | Replace with `can_use_tool` |
| `facade.py` | 568 | **~300** | Remove fallback, interception, admin messages |
| `sdk_integration.py` | 513 | **~100** | Remove CLI discovery, dead state, content extraction |
| `exceptions.py` | 50 | **~20** | Remove `ClaudeToolValidationError` |
| **Total** | **2,774** | **~1,880** | **~68% reduction** |

Post-refactor, the `src/claude/` module should be roughly **~900 lines** with
clearer responsibilities:

- `sdk_integration.py` — Thin wrapper around `ClaudeSDKClient`, builds options,
  handles `can_use_tool` callback
- `session.py` — Thin persistence (SQLite read/write of session IDs)
- `facade.py` — Simplified public API for bot handlers
- `exceptions.py` — Minimal custom exceptions

---

## Recommended Refactor Order

These steps are ordered to minimize risk and allow incremental progress. Each
step should be a separate PR that can be tested independently.

### Phase 1: Low-Risk Cleanup (no behavioral changes)

1. **Remove dead in-memory state** from `ClaudeSDKManager`
   - Delete `active_sessions`, `_update_session()`, `kill_all_processes()` body
   - ~20 lines, zero risk

2. **Use `ResultMessage.result`** for content extraction
   - Add fallback to `_extract_content_from_messages()` only if `result` is None
   - ~10 lines changed, easy to verify

3. **Pass `disallowed_tools` to SDK options**
   - Add `disallowed_tools=self.config.claude_disallowed_tools` to options
   - Keep `ToolMonitor` check as redundant safety for now
   - ~5 lines added

### Phase 2: Remove CLI Subprocess Backend

4. **Delete `integration.py` and `parser.py`**
   - Remove `ClaudeProcessManager` and `OutputParser`
   - Remove fallback logic from `facade.py._execute_with_fallback()`
   - Remove `process_manager` from `ClaudeIntegration.__init__()`
   - ~1,012 lines removed
   - **Risk**: If SDK has bugs, there's no fallback. Mitigate by upgrading to
     latest SDK version first.
   - **Prerequisite**: Upgrade `claude-agent-sdk` from 0.1.31 to latest.
     Run tests. Verify SDK works reliably without fallback.

### Phase 3: Replace `ToolMonitor` with `can_use_tool`

5. **Implement `can_use_tool` callback**
   - Create a callback function that encapsulates:
     - Path validation (from `SecurityValidator.validate_path()`)
     - Directory boundary checks (from `check_bash_directory_boundary()`)
   - Wire it into `ClaudeAgentOptions`
   - ~50 lines of new code

6. **Remove `ToolMonitor` and facade interception**
   - Delete `monitor.py` (except `check_bash_directory_boundary` if still used)
   - Remove `stream_handler` wrapper from `facade.py.run_command()`
   - Remove `_get_admin_instructions()`, `_create_tool_error_message()`
   - ~400 lines removed
   - **Risk**: Security regression if `can_use_tool` callback doesn't cover all
     cases. Mitigate by writing thorough tests for the callback before removing
     `ToolMonitor`.

### Phase 4: Switch to `ClaudeSDKClient`

7. **Replace `query()` with `ClaudeSDKClient`**
   - Refactor `ClaudeSDKManager` to create/manage `ClaudeSDKClient` instances
   - Remove temporary session ID generation
   - Remove session ID swapping logic
   - Simplify `SessionManager` to thin persistence
   - ~300 lines removed, ~50 lines added
   - **Risk**: Highest-risk change. `ClaudeSDKClient` has different lifecycle
     semantics. Mitigate by:
     - Building a prototype first
     - Testing multi-turn conversations thoroughly
     - Verifying session resume across bot restarts
     - Keeping `options.resume` for cross-restart persistence

8. **Add `max_budget_usd`**
   - Add config setting and pass to options
   - ~10 lines
   - No risk

### Phase 5: Final Cleanup

9. **Remove `find_claude_cli()` and `update_path_for_claude()`**
   - Let SDK handle discovery, only pass `cli_path` if configured
   - ~60 lines removed

10. **Consolidate dataclasses**
    - Single `ClaudeResponse` definition (or use SDK types directly)
    - Single `StreamUpdate` definition (or eliminate if using `ClaudeSDKClient`)

---

## Migration Risks

### SDK Version Sensitivity

We're on `v0.1.31`, latest is newer. The SDK is pre-1.0 and API surface may
shift. Before starting Phase 2+:
- Pin to a specific tested version
- Read changelogs between versions
- Run full test suite after upgrade

### `ClaudeSDKClient` Lifecycle

`ClaudeSDKClient` uses `async with` context manager. We need to manage client
lifecycle carefully:
- One client per user? Per user+directory? Global pool?
- What happens when the client disconnects unexpectedly?
- How do we handle bot restarts (need `resume` option)?

Recommend prototyping this before committing to the refactor.

### Security Regression

Moving from `ToolMonitor` to `can_use_tool` changes validation from reactive
to preventive, which is **better**. But the transition must be careful:
- Write tests for every validation rule in `ToolMonitor` first
- Ensure the `can_use_tool` callback covers all cases
- Test edge cases (path traversal, command injection, etc.)

### Test Coverage

Before any refactor:
- Ensure existing tests pass
- Add integration tests for the SDK path (if not already present)
- Add tests for `can_use_tool` callback behavior

---

## References

- [Claude Agent SDK - Python Reference](https://platform.claude.com/docs/en/agent-sdk/python)
- [Claude Agent SDK - Permissions](https://platform.claude.com/docs/en/agent-sdk/permissions)
- [Claude Agent SDK - Hooks](https://platform.claude.com/docs/en/agent-sdk/hooks)
- [GitHub: anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python)
