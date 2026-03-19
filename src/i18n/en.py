"""English translations for Claude Code Telegram Bot."""

TRANSLATIONS: dict[str, str] = {
    # --- Agentic /start ---
    "start.private_topics_mode": (
        "\U0001f6ab <b>Private Topics Mode</b>\n\n"
        "Use this bot in a private chat and run <code>/start</code> there."
    ),
    "start.topics_synced": (
        "\n\n\U0001f9f5 Topics synced (created {created}, reused {reused})."
    ),
    "start.topic_sync_failed": (
        "\n\n\U0001f9f5 Topic sync failed. Run /sync_threads to retry."
    ),
    "start.welcome": (
        "Hi {name}! I'm your AI coding assistant.\n"
        "Just tell me what you need \u2014 I can read, write, and run code.\n\n"
        "Working in: {dir_display}\n"
        "Commands: /new (reset) \u00b7 /status"
    ),

    # --- Agentic /new ---
    "new.reset": "Session reset. What's next?",

    # --- Agentic /status ---
    "status.line": "\U0001f4c2 {dir_display} \u00b7 Session: {session_status}{cost_str}",

    # --- Agentic /verbose ---
    "verbose.current": (
        "Verbosity: <b>{level}</b> ({label})\n\n"
        "Usage: <code>/verbose 0|1|2</code>\n"
        "  0 = quiet (final response only)\n"
        "  1 = normal (tools + reasoning)\n"
        "  2 = detailed (tools with inputs + reasoning)"
    ),
    "verbose.invalid": "Please use: /verbose 0, /verbose 1, or /verbose 2",
    "verbose.set": "Verbosity set to <b>{level}</b> ({label})",
    "verbose.quiet": "quiet",
    "verbose.normal": "normal",
    "verbose.detailed": "detailed",

    # --- Progress ---
    "progress.working": "Working...",
    "progress.transcribing": "Transcribing...",
    "progress.earlier_entries": "... ({count} earlier entries)",

    # --- Errors ---
    "error.claude_unavailable": "Claude integration not available. Check configuration.",
    "error.delivery_failed": (
        "Failed to deliver response (Telegram error: {error}). Please try again."
    ),
    "error.file_rejected": "File rejected: {error}",
    "error.file_too_large": "File too large ({size}MB). Max: 10MB.",
    "error.unsupported_format": "Unsupported file format. Must be text-based (UTF-8).",
    "error.photo_unavailable": "Photo processing is not available.",
    "error.rate_limited": "\u23f1\ufe0f {message}",
    "error.workspace_read": "Error reading workspace: {error}",
    "error.dir_not_found": "Directory not found: <code>{name}</code>",
    "error.a2a_not_enabled": "A2A is not enabled.",

    # --- /repo ---
    "repo.switched": "Switched to <code>{name}/</code>{git_badge}{session_badge}",
    "repo.git_badge": " (git)",
    "repo.session_resumed": " \u00b7 session resumed",
    "repo.no_repos": (
        "No repos in <code>{path}</code>.\n"
        'Clone one by telling me, e.g. <i>"clone org/repo"</i>.'
    ),
    "repo.title": "<b>Repos</b>",

    # --- /lang ---
    "lang.current": (
        "Current language: <b>{lang_name}</b>\n\n"
        "Usage: <code>/lang en</code> or <code>/lang zh</code>"
    ),
    "lang.set": "Language set to <b>{lang_name}</b>",
    "lang.invalid": (
        "Unsupported language: <code>{lang}</code>\n"
        "Supported: {supported}"
    ),
    "lang.en": "English",
    "lang.zh": "\u4e2d\u6587",

    # --- Voice ---
    "voice.unavailable": (
        "Voice processing is not available. "
        "Set {api_key_env} for {provider_name} and install "
        'voice extras with: pip install "claude-code-telegram[voice]"'
    ),

    # --- A2A ---
    "a2a.agent_usage": (
        "<b>Usage:</b> <code>/agent &lt;alias&gt; &lt;message&gt;</code>\n\n"
        "Use <code>/agents</code> to list registered agents."
    ),
    "a2a.agent_not_found": (
        "No agent registered with alias <code>{alias}</code>.\n"
        "Use <code>/agents add {alias} &lt;url&gt;</code> first."
    ),
    "a2a.no_agents": (
        "\U0001f916 <b>No A2A agents registered.</b>\n\n"
        "Register one:\n"
        "<code>/agents add mybot https://example.com</code>"
    ),
    "a2a.agents_title": "\U0001f916 <b>Registered A2A Agents</b>\n",
    "a2a.agent_registered": (
        "\u2705 Agent registered:\n"
        "  Alias: <code>{alias}</code>\n"
        "  Name: {name}\n"
        "  URL: {url}\n\n"
        "Use: <code>/agent {alias} &lt;message&gt;</code>"
    ),
    "a2a.agent_removed": "\U0001f5d1 Agent <code>{alias}</code> removed.",
    "a2a.agent_not_exists": "No agent with alias <code>{alias}</code>.",
    "a2a.agents_usage": (
        "<b>Usage:</b>\n"
        "<code>/agents</code> \u2014 list agents\n"
        "<code>/agents add &lt;alias&gt; &lt;url&gt;</code> \u2014 register\n"
        "<code>/agents remove &lt;alias&gt;</code> \u2014 unregister"
    ),
    "a2a.call_failed": (
        "\u274c A2A call to <code>{alias}</code> failed:\n"
        "<code>{error}</code>"
    ),
    "a2a.resolve_failed": (
        "\u274c Failed to resolve agent:\n"
        "<code>{error}</code>"
    ),

    # --- Thread mode ---
    "thread.misconfigured": (
        "\u274c <b>Project Thread Mode Misconfigured</b>\n\n"
        "Thread manager is not initialized."
    ),

    # --- Bot commands (menu descriptions) ---
    "cmd.start": "Start the bot",
    "cmd.new": "Start a fresh session",
    "cmd.status": "Show session status",
    "cmd.verbose": "Set output verbosity (0/1/2)",
    "cmd.repo": "List repos / switch workspace",
    "cmd.restart": "Restart the bot",
    "cmd.sync_threads": "Sync project topics",
    "cmd.lang": "Set language (en/zh)",
    "cmd.help": "Show available commands",
    "cmd.continue": "Explicitly continue last session",
    "cmd.end": "End current session and clear context",
    "cmd.ls": "List files in current directory",
    "cmd.cd": "Change directory (resumes project session)",
    "cmd.pwd": "Show current directory",
    "cmd.projects": "Show all projects",
    "cmd.export": "Export current session",
    "cmd.actions": "Show quick actions",
    "cmd.git": "Git repository commands",

    # --- Classic /start ---
    "classic.welcome": (
        "\U0001f44b Welcome to Claude Code Telegram Bot, {name}!\n\n"
        "\U0001f916 I help you access Claude Code remotely through Telegram.\n\n"
        "<b>Available Commands:</b>\n"
        "\u2022 <code>/help</code> - Show detailed help\n"
        "\u2022 <code>/new</code> - Start a new Claude session\n"
        "\u2022 <code>/ls</code> - List files in current directory\n"
        "\u2022 <code>/cd &lt;dir&gt;</code> - Change directory\n"
        "\u2022 <code>/projects</code> - Show available projects\n"
        "\u2022 <code>/status</code> - Show session status\n"
        "\u2022 <code>/actions</code> - Show quick actions\n"
        "\u2022 <code>/git</code> - Git repository commands\n\n"
        "<b>Quick Start:</b>\n"
        "1. Use <code>/projects</code> to see available projects\n"
        "2. Use <code>/cd &lt;project&gt;</code> to navigate to a project\n"
        "3. Send any message to start coding with Claude!\n\n"
        "\U0001f512 Your access is secured and all actions are logged.\n"
        "\U0001f4ca Use <code>/status</code> to check your usage limits."
    ),

    # --- Classic /help ---
    "classic.help": (
        "\U0001f916 <b>Claude Code Telegram Bot Help</b>\n\n"
        "<b>Navigation Commands:</b>\n"
        "\u2022 <code>/ls</code> - List files and directories\n"
        "\u2022 <code>/cd &lt;directory&gt;</code> - Change to directory\n"
        "\u2022 <code>/pwd</code> - Show current directory\n"
        "\u2022 <code>/projects</code> - Show available projects\n\n"
        "<b>Session Commands:</b>\n"
        "\u2022 <code>/new</code> - Clear context and start a fresh session\n"
        "\u2022 <code>/continue [message]</code> - Explicitly continue last session\n"
        "\u2022 <code>/end</code> - End current session and clear context\n"
        "\u2022 <code>/status</code> - Show session and usage status\n"
        "\u2022 <code>/export</code> - Export session history\n"
        "\u2022 <code>/actions</code> - Show context-aware quick actions\n"
        "\u2022 <code>/git</code> - Git repository information\n\n"
        "<b>Session Behavior:</b>\n"
        "\u2022 Sessions are automatically maintained per project directory\n"
        "\u2022 Switching directories with <code>/cd</code> resumes the session for that project\n"
        "\u2022 Use <code>/new</code> or <code>/end</code> to explicitly clear session context\n"
        "\u2022 Sessions persist across bot restarts\n\n"
        "<b>Usage Examples:</b>\n"
        "\u2022 <code>cd myproject</code> - Enter project directory\n"
        "\u2022 <code>ls</code> - See what's in current directory\n"
        "\u2022 <code>Create a simple Python script</code> - Ask Claude to code\n"
        "\u2022 Send a file to have Claude review it\n\n"
        "<b>File Operations:</b>\n"
        "\u2022 Send text files (.py, .js, .md, etc.) for review\n"
        "\u2022 Claude can read, modify, and create files\n"
        "\u2022 All file operations are within your approved directory\n\n"
        "<b>Security Features:</b>\n"
        "\u2022 \U0001f512 Path traversal protection\n"
        "\u2022 \u23f1\ufe0f Rate limiting to prevent abuse\n"
        "\u2022 \U0001f4ca Usage tracking and limits\n"
        "\u2022 \U0001f6e1\ufe0f Input validation and sanitization\n\n"
        "<b>Tips:</b>\n"
        "\u2022 Use specific, clear requests for best results\n"
        "\u2022 Check <code>/status</code> to monitor your usage\n"
        "\u2022 Use quick action buttons when available\n"
        "\u2022 File uploads are automatically processed by Claude\n\n"
        "Need more help? Contact your administrator."
    ),

    # --- Classic /new ---
    "classic.new.cleared": (
        "\n\U0001f5d1\ufe0f Previous session <code>{session_id}...</code> cleared."
    ),
    "classic.new.message": (
        "\U0001f195 <b>New Claude Code Session</b>\n\n"
        "\U0001f4c2 Working directory: <code>{path}/</code>{cleared_info}\n\n"
        "Context has been cleared. Send a message to start fresh, "
        "or use the buttons below:"
    ),

    # --- Classic /continue ---
    "classic.continue.continuing": (
        "\U0001f504 <b>Continuing Session</b>\n\n"
        "Session ID: <code>{session_id}...</code>\n"
        "Directory: <code>{path}/</code>\n\n"
        "{status}"
    ),
    "classic.continue.processing": "Processing your message...",
    "classic.continue.resuming": "Continuing where you left off...",
    "classic.continue.searching": (
        "\U0001f50d <b>Looking for Recent Session</b>\n\n"
        "Searching for your most recent session in this directory..."
    ),
    "classic.continue.no_session": (
        "\u274c <b>No Session Found</b>\n\n"
        "No recent Claude session found in this directory.\n"
        "Directory: <code>{path}/</code>\n\n"
        "<b>What you can do:</b>\n"
        "\u2022 Use <code>/new</code> to start a fresh session\n"
        "\u2022 Use <code>/status</code> to check your sessions\n"
        "\u2022 Navigate to a different directory with <code>/cd</code>"
    ),
    "classic.continue.error": (
        "\u274c <b>Error Continuing Session</b>\n\n"
        "An error occurred while trying to continue your session:\n\n"
        "<code>{error}</code>\n\n"
        "<b>Suggestions:</b>\n"
        "\u2022 Try starting a new session with <code>/new</code>\n"
        "\u2022 Check your session status with <code>/status</code>\n"
        "\u2022 Contact support if the issue persists"
    ),
    "classic.continue.not_available": (
        "\u274c <b>Claude Integration Not Available</b>\n\n"
        "Claude integration is not properly configured."
    ),

    # --- Classic /ls ---
    "classic.ls.empty": "\U0001f4c2 <code>{path}/</code>\n\n<i>(empty directory)</i>",
    "classic.ls.more_items": "... and {count} more items",
    "classic.ls.error": "\u274c Error listing directory: {error}",

    # --- Classic /cd ---
    "classic.cd.usage": (
        "<b>Usage:</b> <code>/cd &lt;directory&gt;</code>\n\n"
        "<b>Examples:</b>\n"
        "\u2022 <code>/cd myproject</code> - Enter subdirectory\n"
        "\u2022 <code>/cd ..</code> - Go up one level\n"
        "\u2022 <code>/cd /</code> - Go to root of approved directory\n\n"
        "<b>Tips:</b>\n"
        "\u2022 Use <code>/ls</code> to see available directories\n"
        "\u2022 Use <code>/projects</code> to see all projects"
    ),
    "classic.cd.access_denied": "\u274c <b>Access Denied</b>\n\n{error}",
    "classic.cd.thread_restricted": (
        "\u274c <b>Access Denied</b>\n\n"
        "In thread mode, navigation is limited to the current project root."
    ),
    "classic.cd.not_found": (
        "\u274c <b>Directory Not Found</b>\n\n"
        "<code>{path}</code> does not exist."
    ),
    "classic.cd.not_dir": (
        "\u274c <b>Not a Directory</b>\n\n"
        "<code>{path}</code> is not a directory."
    ),
    "classic.cd.changed": (
        "\u2705 <b>Directory Changed</b>\n\n"
        "\U0001f4c2 Current directory: <code>{path}</code>{session_info}"
    ),
    "classic.cd.session_resumed": (
        "\n\U0001f504 Resumed session <code>{session_id}...</code> "
        "({message_count} messages)"
    ),
    "classic.cd.no_session": (
        "\n\U0001f195 No existing session. Send a message to start a new one."
    ),
    "classic.cd.error": "\u274c <b>Error changing directory</b>\n\n{error}",

    # --- Classic /pwd ---
    "classic.pwd": (
        "\U0001f4cd <b>Current Directory</b>\n\n"
        "Relative: <code>{relative}/</code>\n"
        "Absolute: <code>{absolute}</code>"
    ),

    # --- Classic /projects ---
    "classic.projects.registry_error": (
        "\u274c <b>Project registry is not initialized.</b>"
    ),
    "classic.projects.no_projects": (
        "\U0001f4c1 <b>No Projects Found</b>\n\n"
        "No enabled projects found in projects config."
    ),
    "classic.projects.configured": "\U0001f4c1 <b>Configured Projects</b>\n\n{list}",
    "classic.projects.no_dirs": (
        "\U0001f4c1 <b>No Projects Found</b>\n\n"
        "No subdirectories found in your approved directory.\n"
        "Create some directories to organize your projects!"
    ),
    "classic.projects.available": (
        "\U0001f4c1 <b>Available Projects</b>\n\n"
        "{list}\n\n"
        "Click a project below to navigate to it:"
    ),
    "classic.projects.error": "\u274c Error loading projects: {error}",

    # --- Classic /status ---
    "classic.status.title": "\U0001f4ca <b>Session Status</b>",
    "classic.status.directory": "\U0001f4c2 Directory: <code>{path}/</code>",
    "classic.status.session_active": "\U0001f916 Claude Session: \u2705 Active",
    "classic.status.session_none": "\U0001f916 Claude Session: \u274c None",
    "classic.status.usage": "\U0001f4b0 Usage: ${current:.2f} / ${limit:.2f} ({pct:.0f}%)",
    "classic.status.usage_error": "\U0001f4b0 Usage: <i>Unable to retrieve</i>",
    "classic.status.last_update": "\U0001f550 Last Update: {time}",
    "classic.status.session_id": "\U0001f194 Session ID: <code>{id}...</code>",
    "classic.status.resumable": (
        "\U0001f504 Resumable: <code>{id}...</code> ({count} msgs)"
    ),
    "classic.status.auto_resume": "\U0001f4a1 Session will auto-resume on your next message",

    # --- Classic /export ---
    "classic.export.unavailable": (
        "\U0001f4e4 <b>Export Session</b>\n\n"
        "Session export functionality is not available.\n\n"
        "<b>Planned features:</b>\n"
        "\u2022 Export conversation history\n"
        "\u2022 Save session state\n"
        "\u2022 Share conversations\n"
        "\u2022 Create session backups"
    ),
    "classic.export.no_session": (
        "\u274c <b>No Active Session</b>\n\n"
        "There's no active Claude session to export.\n\n"
        "<b>What you can do:</b>\n"
        "\u2022 Start a new session with <code>/new</code>\n"
        "\u2022 Continue an existing session with <code>/continue</code>\n"
        "\u2022 Check your status with <code>/status</code>"
    ),
    "classic.export.ready": (
        "\U0001f4e4 <b>Export Session</b>\n\n"
        "Ready to export session: <code>{session_id}...</code>\n\n"
        "<b>Choose export format:</b>"
    ),

    # --- Classic /end ---
    "classic.end.no_session": (
        "\u2139\ufe0f <b>No Active Session</b>\n\n"
        "There's no active Claude session to end.\n\n"
        "<b>What you can do:</b>\n"
        "\u2022 Use <code>/new</code> to start a new session\n"
        "\u2022 Use <code>/status</code> to check your session status\n"
        "\u2022 Send any message to start a conversation"
    ),
    "classic.end.ended": (
        "\u2705 <b>Session Ended</b>\n\n"
        "Your Claude session has been terminated.\n\n"
        "<b>Current Status:</b>\n"
        "\u2022 Directory: <code>{path}/</code>\n"
        "\u2022 Session: None\n"
        "\u2022 Ready for new commands\n\n"
        "<b>Next Steps:</b>\n"
        "\u2022 Start a new session with <code>/new</code>\n"
        "\u2022 Check status with <code>/status</code>\n"
        "\u2022 Send any message to begin a new conversation"
    ),

    # --- Classic /actions ---
    "classic.actions.disabled": (
        "\u274c <b>Quick Actions Disabled</b>\n\n"
        "Quick actions feature is not enabled.\n"
        "Contact your administrator to enable this feature."
    ),
    "classic.actions.unavailable": (
        "\u274c <b>Quick Actions Unavailable</b>\n\n"
        "Quick actions service is not available."
    ),
    "classic.actions.none": (
        "\U0001f916 <b>No Actions Available</b>\n\n"
        "No quick actions are available for the current context.\n\n"
        "<b>Try:</b>\n"
        "\u2022 Navigating to a project directory with <code>/cd</code>\n"
        "\u2022 Creating some code files\n"
        "\u2022 Starting a Claude session with <code>/new</code>"
    ),
    "classic.actions.title": (
        "\u26a1 <b>Quick Actions</b>\n\n"
        "\U0001f4c2 Context: <code>{path}/</code>\n\n"
        "Select an action to execute:"
    ),
    "classic.actions.error": "\u274c <b>Error Loading Actions</b>\n\n{error}",

    # --- Classic /git ---
    "classic.git.disabled": (
        "\u274c <b>Git Integration Disabled</b>\n\n"
        "Git integration feature is not enabled.\n"
        "Contact your administrator to enable this feature."
    ),
    "classic.git.unavailable": (
        "\u274c <b>Git Integration Unavailable</b>\n\n"
        "Git integration service is not available."
    ),
    "classic.git.not_repo": (
        "\U0001f4c2 <b>Not a Git Repository</b>\n\n"
        "Current directory <code>{path}/</code> is not a git repository.\n\n"
        "<b>Options:</b>\n"
        "\u2022 Navigate to a git repository with <code>/cd</code>\n"
        "\u2022 Initialize a new repository (ask Claude to help)\n"
        "\u2022 Clone an existing repository (ask Claude to help)"
    ),
    "classic.git.error": "\u274c <b>Git Error</b>\n\n{error}",

    # --- Classic /restart ---
    "classic.restart": "\U0001f504 <b>Restarting bot\u2026</b>\n\nBack shortly.",

    # --- Classic /sync_threads ---
    "classic.sync.disabled": "\u2139\ufe0f <b>Project thread mode is disabled.</b>",
    "classic.sync.not_init": "\u274c <b>Project thread manager not initialized.</b>",
    "classic.sync.syncing": "\U0001f504 <b>Syncing project topics...</b>",
    "classic.sync.private_error": (
        "\u274c <b>Private Thread Mode</b>\n\n"
        "Run <code>/sync_threads</code> in your private chat with the bot."
    ),
    "classic.sync.group_no_chat_id": (
        "\u274c <b>Group Thread Mode Misconfigured</b>\n\n"
        "Set <code>PROJECT_THREADS_CHAT_ID</code> first."
    ),
    "classic.sync.group_wrong_chat": (
        "\u274c <b>Group Thread Mode</b>\n\n"
        "Run <code>/sync_threads</code> in the configured project threads group."
    ),
    "classic.sync.no_config": (
        "\u274c <b>Project thread mode is misconfigured</b>\n\n"
        "Set <code>PROJECTS_CONFIG_PATH</code> to a valid YAML file."
    ),
    "classic.sync.complete": (
        "\u2705 <b>Project topic sync complete</b>\n\n"
        "\u2022 Created: <b>{created}</b>\n"
        "\u2022 Reused: <b>{reused}</b>\n"
        "\u2022 Renamed: <b>{renamed}</b>\n"
        "\u2022 Reopened: <b>{reopened}</b>\n"
        "\u2022 Closed: <b>{closed}</b>\n"
        "\u2022 Deactivated: <b>{deactivated}</b>\n"
        "\u2022 Failed: <b>{failed}</b>"
    ),
    "classic.sync.failed": (
        "\u274c <b>Project topic sync failed</b>\n\n{error}"
    ),

    # --- Classic start sync section ---
    "classic.start.sync_section": (
        "\n\n\U0001f9f5 <b>Project Topics Synced</b>\n"
        "\u2022 Created: <b>{created}</b>\n"
        "\u2022 Reused: <b>{reused}</b>\n"
        "\u2022 Renamed: <b>{renamed}</b>\n"
        "\u2022 Failed: <b>{failed}</b>\n\n"
        "Use a project topic thread to start coding."
    ),
    "classic.start.sync_warning": (
        "\n\n\u26a0\ufe0f <b>Topic Sync Warning</b>\n"
        "{error}\n\n"
        "Run <code>/sync_threads</code> to retry."
    ),
    "classic.start.misconfigured": (
        "\u274c <b>Project thread mode is misconfigured</b>\n\n"
        "Thread manager is not initialized."
    ),

    # --- Button labels ---
    "btn.show_projects": "\U0001f4c1 Show Projects",
    "btn.get_help": "\u2753 Get Help",
    "btn.new_session": "\U0001f195 New Session",
    "btn.check_status": "\U0001f4ca Check Status",
    "btn.start_coding": "\U0001f4dd Start Coding",
    "btn.change_project": "\U0001f4c1 Change Project",
    "btn.quick_actions": "\U0001f4cb Quick Actions",
    "btn.help": "\u2753 Help",
    "btn.go_up": "\u2b06\ufe0f Go Up",
    "btn.go_root": "\U0001f3e0 Go to Root",
    "btn.refresh": "\U0001f504 Refresh",
    "btn.projects": "\U0001f4c1 Projects",
    "btn.list_files": "\U0001f4c1 List Files",
    "btn.continue": "\U0001f504 Continue",
    "btn.start_session": "\U0001f195 Start Session",
    "btn.export": "\U0001f4e4 Export",
    "btn.status": "\U0001f4ca Status",
    "btn.show_diff": "\U0001f4ca Show Diff",
    "btn.show_log": "\U0001f4dc Show Log",
    "btn.files": "\U0001f4c1 Files",
    "btn.markdown": "\U0001f4dd Markdown",
    "btn.html": "\U0001f310 HTML",
    "btn.json": "\U0001f4cb JSON",
    "btn.cancel": "\u274c Cancel",

    # --- Error handler (core.py) ---
    "error.auth_required": "\U0001f512 Authentication required. Please contact the administrator.",
    "error.security_violation": "\U0001f6e1\ufe0f Security violation detected. This incident has been logged.",
    "error.rate_limit": "\u23f1\ufe0f Rate limit exceeded. Please wait before sending more messages.",
    "error.config": "\u2699\ufe0f Configuration error. Please contact the administrator.",
    "error.timeout": "\u23f0 Operation timed out. Please try again with a simpler request.",
    "error.unexpected": "\u274c An unexpected error occurred. Please try again.",
}
