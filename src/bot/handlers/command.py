"""Command handlers for bot operations."""

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ...claude.facade import ClaudeIntegration
from ...config.settings import Settings
from ...security.audit import AuditLogger
from ...security.validators import SecurityValidator
from ..utils.html_format import escape_html

logger = structlog.get_logger()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user = update.effective_user

    welcome_message = (
        f"👋 Welcome to Claude Code Telegram Bot, {escape_html(user.first_name)}!\n\n"
        f"🤖 I help you access Claude Code remotely through Telegram.\n\n"
        f"<b>Available Commands:</b>\n"
        f"• <code>/help</code> - Show detailed help\n"
        f"• <code>/new</code> - Start a new Claude session\n"
        f"• <code>/ls</code> - List files in current directory\n"
        f"• <code>/cd &lt;dir&gt;</code> - Change directory\n"
        f"• <code>/projects</code> - Show available projects\n"
        f"• <code>/status</code> - Show session status\n"
        f"• <code>/actions</code> - Show quick actions\n"
        f"• <code>/git</code> - Git repository commands\n\n"
        f"<b>Quick Start:</b>\n"
        f"1. Use <code>/projects</code> to see available projects\n"
        f"2. Use <code>/cd &lt;project&gt;</code> to navigate to a project\n"
        f"3. Send any message to start coding with Claude!\n\n"
        f"🔒 Your access is secured and all actions are logged.\n"
        f"📊 Use <code>/status</code> to check your usage limits."
    )

    # Add quick action buttons
    keyboard = [
        [
            InlineKeyboardButton(
                "📁 Show Projects", callback_data="action:show_projects"
            ),
            InlineKeyboardButton("❓ Get Help", callback_data="action:help"),
        ],
        [
            InlineKeyboardButton("🆕 New Session", callback_data="action:new_session"),
            InlineKeyboardButton("📊 Check Status", callback_data="action:status"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        welcome_message, parse_mode="HTML", reply_markup=reply_markup
    )

    # Log command
    audit_logger: AuditLogger = context.bot_data.get("audit_logger")
    if audit_logger:
        await audit_logger.log_command(
            user_id=user.id, command="start", args=[], success=True
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    help_text = (
        "🤖 <b>Claude Code Telegram Bot Help</b>\n\n"
        "<b>Navigation Commands:</b>\n"
        "• <code>/ls</code> - List files and directories\n"
        "• <code>/cd &lt;directory&gt;</code> - Change to directory\n"
        "• <code>/pwd</code> - Show current directory\n"
        "• <code>/projects</code> - Show available projects\n\n"
        "<b>Session Commands:</b>\n"
        "• <code>/new</code> - Clear context and start a fresh session\n"
        "• <code>/continue [message]</code> - Explicitly continue last session\n"
        "• <code>/end</code> - End current session and clear context\n"
        "• <code>/status</code> - Show session and usage status\n"
        "• <code>/export</code> - Export session history\n"
        "• <code>/actions</code> - Show context-aware quick actions\n"
        "• <code>/git</code> - Git repository information\n\n"
        "<b>Session Behavior:</b>\n"
        "• Sessions are automatically maintained per project directory\n"
        "• Switching directories with <code>/cd</code> resumes the session for that project\n"
        "• Use <code>/new</code> or <code>/end</code> to explicitly clear session context\n"
        "• Sessions persist across bot restarts\n\n"
        "<b>Usage Examples:</b>\n"
        "• <code>cd myproject</code> - Enter project directory\n"
        "• <code>ls</code> - See what's in current directory\n"
        "• <code>Create a simple Python script</code> - Ask Claude to code\n"
        "• Send a file to have Claude review it\n\n"
        "<b>File Operations:</b>\n"
        "• Send text files (.py, .js, .md, etc.) for review\n"
        "• Claude can read, modify, and create files\n"
        "• All file operations are within your approved directory\n\n"
        "<b>Security Features:</b>\n"
        "• 🔒 Path traversal protection\n"
        "• ⏱️ Rate limiting to prevent abuse\n"
        "• 📊 Usage tracking and limits\n"
        "• 🛡️ Input validation and sanitization\n\n"
        "<b>Tips:</b>\n"
        "• Use specific, clear requests for best results\n"
        "• Check <code>/status</code> to monitor your usage\n"
        "• Use quick action buttons when available\n"
        "• File uploads are automatically processed by Claude\n\n"
        "Need more help? Contact your administrator."
    )

    await update.message.reply_text(help_text, parse_mode="HTML")


async def new_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /new command - explicitly starts a fresh session, clearing previous context."""
    settings: Settings = context.bot_data["settings"]

    # Get current directory (default to approved directory)
    current_dir = context.user_data.get(
        "current_directory", settings.approved_directory
    )
    relative_path = current_dir.relative_to(settings.approved_directory)

    # Track what was cleared for user feedback
    old_session_id = context.user_data.get("claude_session_id")

    # Clear existing session data - this is the explicit way to reset context
    context.user_data["claude_session_id"] = None
    context.user_data["session_started"] = True

    cleared_info = ""
    if old_session_id:
        cleared_info = (
            f"\n🗑️ Previous session <code>{old_session_id[:8]}...</code> cleared."
        )

    keyboard = [
        [
            InlineKeyboardButton(
                "📝 Start Coding", callback_data="action:start_coding"
            ),
            InlineKeyboardButton(
                "📁 Change Project", callback_data="action:show_projects"
            ),
        ],
        [
            InlineKeyboardButton(
                "📋 Quick Actions", callback_data="action:quick_actions"
            ),
            InlineKeyboardButton("❓ Help", callback_data="action:help"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🆕 <b>New Claude Code Session</b>\n\n"
        f"📂 Working directory: <code>{relative_path}/</code>{cleared_info}\n\n"
        f"Context has been cleared. Send a message to start fresh, "
        f"or use the buttons below:",
        parse_mode="HTML",
        reply_markup=reply_markup,
    )


async def continue_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /continue command with optional prompt."""
    user_id = update.effective_user.id
    settings: Settings = context.bot_data["settings"]
    claude_integration: ClaudeIntegration = context.bot_data.get("claude_integration")
    audit_logger: AuditLogger = context.bot_data.get("audit_logger")

    # Parse optional prompt from command arguments
    # If no prompt provided, use a default to continue the conversation
    prompt = " ".join(context.args) if context.args else None
    default_prompt = "Please continue where we left off"

    current_dir = context.user_data.get(
        "current_directory", settings.approved_directory
    )

    try:
        if not claude_integration:
            await update.message.reply_text(
                "❌ <b>Claude Integration Not Available</b>\n\n"
                "Claude integration is not properly configured."
            )
            return

        # Check if there's an existing session in user context
        claude_session_id = context.user_data.get("claude_session_id")

        if claude_session_id:
            # We have a session in context, continue it directly
            status_msg = await update.message.reply_text(
                f"🔄 <b>Continuing Session</b>\n\n"
                f"Session ID: <code>{claude_session_id[:8]}...</code>\n"
                f"Directory: <code>{current_dir.relative_to(settings.approved_directory)}/</code>\n\n"
                f"{'Processing your message...' if prompt else 'Continuing where you left off...'}",
                parse_mode="HTML",
            )

            # Continue with the existing session
            # Use default prompt if none provided (Claude CLI requires a prompt)
            claude_response = await claude_integration.run_command(
                prompt=prompt or default_prompt,
                working_directory=current_dir,
                user_id=user_id,
                session_id=claude_session_id,
            )
        else:
            # No session in context, try to find the most recent session
            status_msg = await update.message.reply_text(
                "🔍 <b>Looking for Recent Session</b>\n\n"
                "Searching for your most recent session in this directory...",
                parse_mode="HTML",
            )

            # Use default prompt if none provided
            claude_response = await claude_integration.continue_session(
                user_id=user_id,
                working_directory=current_dir,
                prompt=prompt or default_prompt,
            )

        if claude_response:
            # Update session ID in context
            context.user_data["claude_session_id"] = claude_response.session_id

            # Delete status message and send response
            await status_msg.delete()

            # Format and send Claude's response
            from ..utils.formatting import ResponseFormatter

            formatter = ResponseFormatter(settings)
            formatted_messages = formatter.format_claude_response(
                claude_response.content
            )

            for msg in formatted_messages:
                await update.message.reply_text(
                    msg.text,
                    parse_mode=msg.parse_mode,
                    reply_markup=msg.reply_markup,
                )

            # Log successful continue
            if audit_logger:
                await audit_logger.log_command(
                    user_id=user_id,
                    command="continue",
                    args=context.args or [],
                    success=True,
                )

        else:
            # No session found to continue
            await status_msg.edit_text(
                "❌ <b>No Session Found</b>\n\n"
                f"No recent Claude session found in this directory.\n"
                f"Directory: <code>{current_dir.relative_to(settings.approved_directory)}/</code>\n\n"
                f"<b>What you can do:</b>\n"
                f"• Use <code>/new</code> to start a fresh session\n"
                f"• Use <code>/status</code> to check your sessions\n"
                f"• Navigate to a different directory with <code>/cd</code>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🆕 New Session", callback_data="action:new_session"
                            ),
                            InlineKeyboardButton(
                                "📊 Status", callback_data="action:status"
                            ),
                        ]
                    ]
                ),
            )

    except Exception as e:
        error_msg = str(e)
        logger.error("Error in continue command", error=error_msg, user_id=user_id)

        # Delete status message if it exists
        try:
            if "status_msg" in locals():
                await status_msg.delete()
        except Exception:
            pass

        # Send error response
        await update.message.reply_text(
            f"❌ <b>Error Continuing Session</b>\n\n"
            f"An error occurred while trying to continue your session:\n\n"
            f"<code>{error_msg}</code>\n\n"
            f"<b>Suggestions:</b>\n"
            f"• Try starting a new session with <code>/new</code>\n"
            f"• Check your session status with <code>/status</code>\n"
            f"• Contact support if the issue persists",
            parse_mode="HTML",
        )

        # Log failed continue
        if audit_logger:
            await audit_logger.log_command(
                user_id=user_id,
                command="continue",
                args=context.args or [],
                success=False,
            )


async def list_files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ls command."""
    user_id = update.effective_user.id
    settings: Settings = context.bot_data["settings"]
    audit_logger: AuditLogger = context.bot_data.get("audit_logger")

    # Get current directory
    current_dir = context.user_data.get(
        "current_directory", settings.approved_directory
    )

    try:
        # List directory contents
        items = []
        directories = []
        files = []

        for item in sorted(current_dir.iterdir()):
            # Skip hidden files (starting with .)
            if item.name.startswith("."):
                continue

            # Escape HTML special characters in filenames
            safe_name = _escape_markdown(item.name)

            if item.is_dir():
                directories.append(f"📁 {safe_name}/")
            else:
                # Get file size
                try:
                    size = item.stat().st_size
                    size_str = _format_file_size(size)
                    files.append(f"📄 {safe_name} ({size_str})")
                except OSError:
                    files.append(f"📄 {safe_name}")

        # Combine directories first, then files
        items = directories + files

        # Format response
        relative_path = current_dir.relative_to(settings.approved_directory)
        if not items:
            message = f"📂 <code>{relative_path}/</code>\n\n<i>(empty directory)</i>"
        else:
            message = f"📂 <code>{relative_path}/</code>\n\n"

            # Limit items shown to prevent message being too long
            max_items = 50
            if len(items) > max_items:
                shown_items = items[:max_items]
                message += "\n".join(shown_items)
                message += f"\n\n<i>... and {len(items) - max_items} more items</i>"
            else:
                message += "\n".join(items)

        # Add navigation buttons if not at root
        keyboard = []
        if current_dir != settings.approved_directory:
            keyboard.append(
                [
                    InlineKeyboardButton("⬆️ Go Up", callback_data="cd:.."),
                    InlineKeyboardButton("🏠 Go to Root", callback_data="cd:/"),
                ]
            )

        keyboard.append(
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="action:refresh_ls"),
                InlineKeyboardButton(
                    "📁 Projects", callback_data="action:show_projects"
                ),
            ]
        )

        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

        await update.message.reply_text(
            message, parse_mode="HTML", reply_markup=reply_markup
        )

        # Log successful command
        if audit_logger:
            await audit_logger.log_command(user_id, "ls", [], True)

    except Exception as e:
        error_msg = f"❌ Error listing directory: {str(e)}"
        await update.message.reply_text(error_msg)

        # Log failed command
        if audit_logger:
            await audit_logger.log_command(user_id, "ls", [], False)

        logger.error("Error in list_files command", error=str(e), user_id=user_id)


async def change_directory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /cd command."""
    user_id = update.effective_user.id
    settings: Settings = context.bot_data["settings"]
    security_validator: SecurityValidator = context.bot_data.get("security_validator")
    audit_logger: AuditLogger = context.bot_data.get("audit_logger")

    # Parse arguments
    if not context.args:
        await update.message.reply_text(
            "<b>Usage:</b> <code>/cd &lt;directory&gt;</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/cd myproject</code> - Enter subdirectory\n"
            "• <code>/cd ..</code> - Go up one level\n"
            "• <code>/cd /</code> - Go to root of approved directory\n\n"
            "<b>Tips:</b>\n"
            "• Use <code>/ls</code> to see available directories\n"
            "• Use <code>/projects</code> to see all projects",
            parse_mode="HTML",
        )
        return

    target_path = " ".join(context.args)
    current_dir = context.user_data.get(
        "current_directory", settings.approved_directory
    )

    try:
        # Validate path using security validator
        if security_validator:
            valid, resolved_path, error = security_validator.validate_path(
                target_path, current_dir
            )

            if not valid:
                await update.message.reply_text(f"❌ <b>Access Denied</b>\n\n{error}")

                # Log security violation
                if audit_logger:
                    await audit_logger.log_security_violation(
                        user_id=user_id,
                        violation_type="path_traversal_attempt",
                        details=f"Attempted path: {target_path}",
                        severity="medium",
                    )
                return
        else:
            # Fallback validation without security validator
            if target_path == "/":
                resolved_path = settings.approved_directory
            elif target_path == "..":
                resolved_path = current_dir.parent
                if not str(resolved_path).startswith(str(settings.approved_directory)):
                    resolved_path = settings.approved_directory
            else:
                resolved_path = current_dir / target_path
                resolved_path = resolved_path.resolve()

        # Check if directory exists and is actually a directory
        if not resolved_path.exists():
            await update.message.reply_text(
                f"❌ <b>Directory Not Found</b>\n\n<code>{target_path}</code> does not exist."
            )
            return

        if not resolved_path.is_dir():
            await update.message.reply_text(
                f"❌ <b>Not a Directory</b>\n\n<code>{target_path}</code> is not a directory."
            )
            return

        # Update current directory in user data
        context.user_data["current_directory"] = resolved_path

        # Look up existing session for the new directory instead of clearing
        claude_integration: ClaudeIntegration = context.bot_data.get(
            "claude_integration"
        )
        resumed_session_info = ""
        if claude_integration:
            existing_session = await claude_integration._find_resumable_session(
                user_id, resolved_path
            )
            if existing_session:
                context.user_data["claude_session_id"] = existing_session.session_id
                resumed_session_info = (
                    f"\n🔄 Resumed session <code>{existing_session.session_id[:8]}...</code> "
                    f"({existing_session.message_count} messages)"
                )
            else:
                # No session for this directory - clear the current one
                context.user_data["claude_session_id"] = None
                resumed_session_info = (
                    "\n🆕 No existing session. Send a message to start a new one."
                )

        # Send confirmation
        relative_path = resolved_path.relative_to(settings.approved_directory)
        await update.message.reply_text(
            f"✅ <b>Directory Changed</b>\n\n"
            f"📂 Current directory: <code>{relative_path}/</code>"
            f"{resumed_session_info}",
            parse_mode="HTML",
        )

        # Log successful command
        if audit_logger:
            await audit_logger.log_command(user_id, "cd", [target_path], True)

    except Exception as e:
        error_msg = f"❌ <b>Error changing directory</b>\n\n{str(e)}"
        await update.message.reply_text(error_msg, parse_mode="HTML")

        # Log failed command
        if audit_logger:
            await audit_logger.log_command(user_id, "cd", [target_path], False)

        logger.error("Error in change_directory command", error=str(e), user_id=user_id)


async def print_working_directory(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /pwd command."""
    settings: Settings = context.bot_data["settings"]
    current_dir = context.user_data.get(
        "current_directory", settings.approved_directory
    )

    relative_path = current_dir.relative_to(settings.approved_directory)
    absolute_path = str(current_dir)

    # Add quick navigation buttons
    keyboard = [
        [
            InlineKeyboardButton("📁 List Files", callback_data="action:ls"),
            InlineKeyboardButton("📋 Projects", callback_data="action:show_projects"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"📍 <b>Current Directory</b>\n\n"
        f"Relative: <code>{relative_path}/</code>\n"
        f"Absolute: <code>{absolute_path}</code>",
        parse_mode="HTML",
        reply_markup=reply_markup,
    )


async def show_projects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /projects command."""
    settings: Settings = context.bot_data["settings"]

    try:
        # Get directories in approved directory (these are "projects")
        projects = []
        for item in sorted(settings.approved_directory.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                projects.append(item.name)

        if not projects:
            await update.message.reply_text(
                "📁 <b>No Projects Found</b>\n\n"
                "No subdirectories found in your approved directory.\n"
                "Create some directories to organize your projects!"
            )
            return

        # Create inline keyboard with project buttons
        keyboard = []
        for i in range(0, len(projects), 2):
            row = []
            for j in range(2):
                if i + j < len(projects):
                    project = projects[i + j]
                    row.append(
                        InlineKeyboardButton(
                            f"📁 {project}", callback_data=f"cd:{project}"
                        )
                    )
            keyboard.append(row)

        # Add navigation buttons
        keyboard.append(
            [
                InlineKeyboardButton("🏠 Go to Root", callback_data="cd:/"),
                InlineKeyboardButton(
                    "🔄 Refresh", callback_data="action:show_projects"
                ),
            ]
        )

        reply_markup = InlineKeyboardMarkup(keyboard)

        project_list = "\n".join([f"• <code>{project}/</code>" for project in projects])

        await update.message.reply_text(
            f"📁 <b>Available Projects</b>\n\n"
            f"{project_list}\n\n"
            f"Click a project below to navigate to it:",
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Error loading projects: {str(e)}")
        logger.error("Error in show_projects command", error=str(e))


async def session_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command."""
    user_id = update.effective_user.id
    settings: Settings = context.bot_data["settings"]

    # Get session info
    claude_session_id = context.user_data.get("claude_session_id")
    current_dir = context.user_data.get(
        "current_directory", settings.approved_directory
    )
    relative_path = current_dir.relative_to(settings.approved_directory)

    # Get rate limiter info if available
    rate_limiter = context.bot_data.get("rate_limiter")
    usage_info = ""
    if rate_limiter:
        try:
            user_status = rate_limiter.get_user_status(user_id)
            cost_usage = user_status.get("cost_usage", {})
            current_cost = cost_usage.get("current", 0.0)
            cost_limit = cost_usage.get("limit", settings.claude_max_cost_per_user)
            cost_percentage = (current_cost / cost_limit) * 100 if cost_limit > 0 else 0

            usage_info = f"💰 Usage: ${current_cost:.2f} / ${cost_limit:.2f} ({cost_percentage:.0f}%)\n"
        except Exception:
            usage_info = "💰 Usage: <i>Unable to retrieve</i>\n"

    # Check if there's a resumable session from the database
    resumable_info = ""
    if not claude_session_id:
        claude_integration: ClaudeIntegration = context.bot_data.get(
            "claude_integration"
        )
        if claude_integration:
            existing = await claude_integration._find_resumable_session(
                user_id, current_dir
            )
            if existing:
                resumable_info = (
                    f"🔄 Resumable: <code>{existing.session_id[:8]}...</code> "
                    f"({existing.message_count} msgs)"
                )

    # Format status message
    status_lines = [
        "📊 <b>Session Status</b>",
        "",
        f"📂 Directory: <code>{relative_path}/</code>",
        f"🤖 Claude Session: {'✅ Active' if claude_session_id else '❌ None'}",
        usage_info.rstrip(),
        f"🕐 Last Update: {update.message.date.strftime('%H:%M:%S UTC')}",
    ]

    if claude_session_id:
        status_lines.append(f"🆔 Session ID: <code>{claude_session_id[:8]}...</code>")
    elif resumable_info:
        status_lines.append(resumable_info)
        status_lines.append("💡 Session will auto-resume on your next message")

    # Add action buttons
    keyboard = []
    if claude_session_id:
        keyboard.append(
            [
                InlineKeyboardButton("🔄 Continue", callback_data="action:continue"),
                InlineKeyboardButton(
                    "🆕 New Session", callback_data="action:new_session"
                ),
            ]
        )
    else:
        keyboard.append(
            [
                InlineKeyboardButton(
                    "🆕 Start Session", callback_data="action:new_session"
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton("📤 Export", callback_data="action:export"),
            InlineKeyboardButton("🔄 Refresh", callback_data="action:refresh_status"),
        ]
    )

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "\n".join(status_lines), parse_mode="HTML", reply_markup=reply_markup
    )


async def export_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /export command."""
    user_id = update.effective_user.id
    features = context.bot_data.get("features")

    # Check if session export is available
    session_exporter = features.get_session_export() if features else None

    if not session_exporter:
        await update.message.reply_text(
            "📤 <b>Export Session</b>\n\n"
            "Session export functionality is not available.\n\n"
            "<b>Planned features:</b>\n"
            "• Export conversation history\n"
            "• Save session state\n"
            "• Share conversations\n"
            "• Create session backups"
        )
        return

    # Get current session
    claude_session_id = context.user_data.get("claude_session_id")

    if not claude_session_id:
        await update.message.reply_text(
            "❌ <b>No Active Session</b>\n\n"
            "There's no active Claude session to export.\n\n"
            "<b>What you can do:</b>\n"
            "• Start a new session with <code>/new</code>\n"
            "• Continue an existing session with <code>/continue</code>\n"
            "• Check your status with <code>/status</code>"
        )
        return

    # Create export format selection keyboard
    keyboard = [
        [
            InlineKeyboardButton("📝 Markdown", callback_data="export:markdown"),
            InlineKeyboardButton("🌐 HTML", callback_data="export:html"),
        ],
        [
            InlineKeyboardButton("📋 JSON", callback_data="export:json"),
            InlineKeyboardButton("❌ Cancel", callback_data="export:cancel"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📤 <b>Export Session</b>\n\n"
        f"Ready to export session: <code>{claude_session_id[:8]}...</code>\n\n"
        "<b>Choose export format:</b>",
        parse_mode="HTML",
        reply_markup=reply_markup,
    )


async def end_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /end command to terminate the current session."""
    user_id = update.effective_user.id
    settings: Settings = context.bot_data["settings"]

    # Check if there's an active session
    claude_session_id = context.user_data.get("claude_session_id")

    if not claude_session_id:
        await update.message.reply_text(
            "ℹ️ <b>No Active Session</b>\n\n"
            "There's no active Claude session to end.\n\n"
            "<b>What you can do:</b>\n"
            "• Use <code>/new</code> to start a new session\n"
            "• Use <code>/status</code> to check your session status\n"
            "• Send any message to start a conversation"
        )
        return

    # Get current directory for display
    current_dir = context.user_data.get(
        "current_directory", settings.approved_directory
    )
    relative_path = current_dir.relative_to(settings.approved_directory)

    # Clear session data
    context.user_data["claude_session_id"] = None
    context.user_data["session_started"] = False
    context.user_data["last_message"] = None

    # Create quick action buttons
    keyboard = [
        [
            InlineKeyboardButton("🆕 New Session", callback_data="action:new_session"),
            InlineKeyboardButton(
                "📁 Change Project", callback_data="action:show_projects"
            ),
        ],
        [
            InlineKeyboardButton("📊 Status", callback_data="action:status"),
            InlineKeyboardButton("❓ Help", callback_data="action:help"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "✅ <b>Session Ended</b>\n\n"
        f"Your Claude session has been terminated.\n\n"
        f"<b>Current Status:</b>\n"
        f"• Directory: <code>{relative_path}/</code>\n"
        f"• Session: None\n"
        f"• Ready for new commands\n\n"
        f"<b>Next Steps:</b>\n"
        f"• Start a new session with <code>/new</code>\n"
        f"• Check status with <code>/status</code>\n"
        f"• Send any message to begin a new conversation",
        parse_mode="HTML",
        reply_markup=reply_markup,
    )

    logger.info("Session ended by user", user_id=user_id, session_id=claude_session_id)


async def quick_actions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /actions command to show quick actions."""
    user_id = update.effective_user.id
    settings: Settings = context.bot_data["settings"]
    features = context.bot_data.get("features")

    if not features or not features.is_enabled("quick_actions"):
        await update.message.reply_text(
            "❌ <b>Quick Actions Disabled</b>\n\n"
            "Quick actions feature is not enabled.\n"
            "Contact your administrator to enable this feature."
        )
        return

    # Get current directory
    current_dir = context.user_data.get(
        "current_directory", settings.approved_directory
    )

    try:
        quick_action_manager = features.get_quick_actions()
        if not quick_action_manager:
            await update.message.reply_text(
                "❌ <b>Quick Actions Unavailable</b>\n\n"
                "Quick actions service is not available."
            )
            return

        # Get context-aware actions
        actions = await quick_action_manager.get_suggestions(
            session_data={"working_directory": str(current_dir), "user_id": user_id}
        )

        if not actions:
            await update.message.reply_text(
                "🤖 <b>No Actions Available</b>\n\n"
                "No quick actions are available for the current context.\n\n"
                "<b>Try:</b>\n"
                "• Navigating to a project directory with <code>/cd</code>\n"
                "• Creating some code files\n"
                "• Starting a Claude session with <code>/new</code>"
            )
            return

        # Create inline keyboard
        keyboard = quick_action_manager.create_inline_keyboard(actions, max_columns=2)

        relative_path = current_dir.relative_to(settings.approved_directory)
        await update.message.reply_text(
            f"⚡ <b>Quick Actions</b>\n\n"
            f"📂 Context: <code>{relative_path}/</code>\n\n"
            f"Select an action to execute:",
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    except Exception as e:
        await update.message.reply_text(f"❌ <b>Error Loading Actions</b>\n\n{str(e)}")
        logger.error("Error in quick_actions command", error=str(e), user_id=user_id)


async def git_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /git command to show git repository information."""
    user_id = update.effective_user.id
    settings: Settings = context.bot_data["settings"]
    features = context.bot_data.get("features")

    if not features or not features.is_enabled("git"):
        await update.message.reply_text(
            "❌ <b>Git Integration Disabled</b>\n\n"
            "Git integration feature is not enabled.\n"
            "Contact your administrator to enable this feature."
        )
        return

    # Get current directory
    current_dir = context.user_data.get(
        "current_directory", settings.approved_directory
    )

    try:
        git_integration = features.get_git_integration()
        if not git_integration:
            await update.message.reply_text(
                "❌ <b>Git Integration Unavailable</b>\n\n"
                "Git integration service is not available."
            )
            return

        # Check if current directory is a git repository
        if not (current_dir / ".git").exists():
            await update.message.reply_text(
                f"📂 <b>Not a Git Repository</b>\n\n"
                f"Current directory <code>{current_dir.relative_to(settings.approved_directory)}/</code> is not a git repository.\n\n"
                f"<b>Options:</b>\n"
                f"• Navigate to a git repository with <code>/cd</code>\n"
                f"• Initialize a new repository (ask Claude to help)\n"
                f"• Clone an existing repository (ask Claude to help)"
            )
            return

        # Get git status
        git_status = await git_integration.get_status(current_dir)

        # Format status message
        relative_path = current_dir.relative_to(settings.approved_directory)
        status_message = f"🔗 <b>Git Repository Status</b>\n\n"
        status_message += f"📂 Directory: <code>{relative_path}/</code>\n"
        status_message += f"🌿 Branch: <code>{git_status.branch}</code>\n"

        if git_status.ahead > 0:
            status_message += f"⬆️ Ahead: {git_status.ahead} commits\n"
        if git_status.behind > 0:
            status_message += f"⬇️ Behind: {git_status.behind} commits\n"

        # Show file changes
        if not git_status.is_clean:
            status_message += f"\n<b>Changes:</b>\n"
            if git_status.modified:
                status_message += f"📝 Modified: {len(git_status.modified)} files\n"
            if git_status.added:
                status_message += f"➕ Added: {len(git_status.added)} files\n"
            if git_status.deleted:
                status_message += f"➖ Deleted: {len(git_status.deleted)} files\n"
            if git_status.untracked:
                status_message += f"❓ Untracked: {len(git_status.untracked)} files\n"
        else:
            status_message += "\n✅ Working directory clean\n"

        # Create action buttons
        keyboard = [
            [
                InlineKeyboardButton("📊 Show Diff", callback_data="git:diff"),
                InlineKeyboardButton("📜 Show Log", callback_data="git:log"),
            ],
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="git:status"),
                InlineKeyboardButton("📁 Files", callback_data="action:ls"),
            ],
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            status_message, parse_mode="HTML", reply_markup=reply_markup
        )

    except Exception as e:
        await update.message.reply_text(f"❌ <b>Git Error</b>\n\n{str(e)}")
        logger.error("Error in git_command", error=str(e), user_id=user_id)


def _format_file_size(size: int) -> str:
    """Format file size in human-readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f}{unit}" if unit != "B" else f"{size}B"
        size /= 1024
    return f"{size:.1f}TB"


def _escape_markdown(text: str) -> str:
    """Escape HTML-special characters in text for Telegram.

    Legacy name kept for compatibility with callers; actually escapes HTML.
    """
    return escape_html(text)
