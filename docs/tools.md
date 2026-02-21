# Available Tools

This document describes the tools that Claude Code can use when interacting through the Telegram bot. Tools are the operations Claude performs behind the scenes to read, write, search, and execute code on your behalf.

## Overview

By default, the bot allows **15 tools**. These are configured via the `CLAUDE_ALLOWED_TOOLS` environment variable and validated at runtime by the [ToolMonitor](../src/claude/monitor.py).

When Claude uses a tool during a conversation, the tool name appears in real-time if verbose output is enabled (`/verbose 1` or `/verbose 2`). If Claude attempts to use a tool that is not in the allowed list, the bot blocks the call and displays an error with the list of currently allowed tools.

## Tool Reference

### File Operations

| Tool | Icon | Description |
|------|------|-------------|
| **Read** | 📖 | Read file contents from disk. Supports text files, images, PDFs, and Jupyter notebooks. |
| **Write** | ✏️ | Create a new file or overwrite an existing file with new contents. |
| **Edit** | ✏️ | Perform targeted string replacements within an existing file without rewriting the entire file. |
| **MultiEdit** | ✏️ | Apply multiple edits to a single file in one operation. Useful for making several changes at once. |

### Search & Navigation

| Tool | Icon | Description |
|------|------|-------------|
| **Glob** | 🔍 | Find files by name pattern (e.g., `**/*.py`, `src/**/*.ts`). Returns matching file paths sorted by modification time. |
| **Grep** | 🔍 | Search file contents using regular expressions. Supports filtering by file type or glob pattern, context lines, and multiple output modes. |
| **LS** | 📂 | List directory contents. |

### Execution

| Tool | Icon | Description |
|------|------|-------------|
| **Bash** | 💻 | Execute shell commands (e.g., `git`, `npm`, `pytest`, `make`). Subject to directory boundary enforcement and, in classic mode, dangerous-pattern blocking. |

### Notebooks

| Tool | Icon | Description |
|------|------|-------------|
| **NotebookRead** | 📓 | Read a Jupyter notebook (`.ipynb`) and return all cells with their outputs. |
| **NotebookEdit** | 📓 | Replace, insert, or delete cells in a Jupyter notebook. |

### Web

| Tool | Icon | Description |
|------|------|-------------|
| **WebFetch** | 🌐 | Fetch a URL and process its content. HTML is converted to markdown before analysis. |
| **WebSearch** | 🌐 | Search the web and return results. Useful for looking up documentation, current events, or information beyond Claude's training data. |

### Task Management

| Tool | Icon | Description |
|------|------|-------------|
| **TodoRead** | ☑️ | Read the current task list that Claude uses to track multi-step work. |
| **TodoWrite** | ☑️ | Create or update a task list to plan and track progress on complex operations. |

### Agent Orchestration

| Tool | Icon | Description |
|------|------|-------------|
| **Task** | 🧠 | Launch a sub-agent to handle complex, multi-step operations autonomously. The sub-agent runs with its own context and returns a result when finished. |

## Verbose Output

When verbose output is enabled, each tool call is shown with its icon as Claude works:

```
You: Add type hints to utils.py

Bot: Working... (5s)
     📖 Read: utils.py
     💬 I'll add type annotations to all functions
     ✏️ Edit: utils.py
     💻 Bash: poetry run mypy src/utils.py
Bot: [Claude shows the changes and type-check results]
```

Control verbosity with `/verbose`:

| Level | Behavior |
|-------|----------|
| `/verbose 0` | Final response only (typing indicator stays active) |
| `/verbose 1` | Tool names + reasoning snippets (default) |
| `/verbose 2` | Tool names with input details + longer reasoning text |

## Configuration

### Allowing / Disallowing Tools

The default allowed tools list is defined in `src/config/settings.py` and can be overridden with environment variables:

```bash
# Allow only specific tools (comma-separated)
CLAUDE_ALLOWED_TOOLS=Read,Write,Edit,Bash,Glob,Grep,LS,Task,MultiEdit,NotebookRead,NotebookEdit,WebFetch,TodoRead,TodoWrite,WebSearch

# Explicitly block specific tools (comma-separated, takes precedence over allowed)
CLAUDE_DISALLOWED_TOOLS=Bash,Write
```

To allow all tools without name-based validation:

```bash
# Skip tool allow/disallow checks (path and bash safety checks still apply)
DISABLE_TOOL_VALIDATION=true
```

### Security Layers

Even when a tool is allowed, additional security checks apply:

1. **File path validation** — `Read`, `Write`, `Edit`, and `MultiEdit` operations must target paths within the `APPROVED_DIRECTORY`. Path traversal attempts are blocked.

2. **Bash command validation** (classic mode) — Dangerous patterns (`rm -rf`, `sudo`, `chmod 777`, pipes, redirections, subshells) are blocked. Filesystem-modifying commands (`mkdir`, `cp`, `mv`, `rm`, etc.) must target paths within the approved directory.

3. **Bash sandboxing** (agentic mode) — Claude Code runs inside its own sandbox. The dangerous-pattern blocklist is skipped in agentic mode since the sandbox provides OS-level isolation, but directory boundary checks for filesystem-modifying commands still apply.

4. **Audit logging** — All tool calls and security violations are recorded for review.

See [Security](../SECURITY.md) for the full security model.
