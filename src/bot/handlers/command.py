"""Command handlers for bot operations."""

import os
import signal
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ...claude.facade import ClaudeIntegration
from ...config.settings import Settings
from ...projects import PrivateTopicsUnavailableError, load_project_registry
from ...security.audit import AuditLogger
from ...security.validators import SecurityValidator
from ...storage.models import SessionModel
from ..utils.html_format import escape_html

logger = structlog.get_logger()


def _is_within_root(path: Path, root: Path) -> bool:
    """Check whether path is within root directory."""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _get_thread_project_root(
    settings: Settings, context: ContextTypes.DEFAULT_TYPE
) -> Optional[Path]:
    """Get thread project root when strict thread mode is active."""
    if not settings.enable_project_threads:
        return None
    thread_context = context.user_data.get("_thread_context")
    if not thread_context:
        return None
    return Path(thread_context["project_root"]).resolve()


def _is_private_chat(update: Update) -> bool:
    """Return True when update is from a private chat."""
    chat = update.effective_chat
    return bool(chat and getattr(chat, "type", "") == "private")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user = update.effective_user
    settings: Settings = context.bot_data["settings"]
    audit_logger: AuditLogger = context.bot_data.get("audit_logger")
    manager = context.bot_data.get("project_threads_manager")
    sync_section = ""

    if settings.enable_project_threads and settings.project_threads_mode == "private":
        if not _is_private_chat(update):
            await update.message.reply_text(
                "🚫 <b>Private Topics Mode</b>\n\n"
                "Use this bot in a private chat and run <code>/start</code> there.",
                parse_mode="HTML",
            )
            return

    if (
        settings.enable_project_threads
        and settings.project_threads_mode == "private"
        and _is_private_chat(update)
    ):
        if manager is None:
            await update.message.reply_text(
                "❌ <b>Project thread mode is misconfigured</b>\n\n"
                "Thread manager is not initialized.",
                parse_mode="HTML",
            )
            return

        try:
            sync_result = await manager.sync_topics(
                context.bot,
                chat_id=update.effective_chat.id,
            )
            sync_section = (
                "\n\n🧵 <b>Project Topics Synced</b>\n"
                f"• Created: <b>{sync_result.created}</b>\n"
                f"• Reused: <b>{sync_result.reused}</b>\n"
                f"• Renamed: <b>{sync_result.renamed}</b>\n"
                f"• Failed: <b>{sync_result.failed}</b>\n\n"
                "Use a project topic thread to start coding."
            )
        except PrivateTopicsUnavailableError:
            await update.message.reply_text(
                manager.private_topics_unavailable_message(),
                parse_mode="HTML",
            )
            if audit_logger:
                await audit_logger.log_command(
                    user_id=user.id,
                    command="start",
                    args=[],
                    success=False,
                )
            return
        except Exception as e:
            sync_section = (
                "\n\n⚠️ <b>Topic Sync Warning</b>\n"
                f"{escape_html(str(e))}\n\n"
                "Run <code>/sync_threads</code> to retry."
            )

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
        f"{sync_section}"
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


async def sync_threads(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Synchronize project topics in the configured forum chat."""
    settings: Settings = context.bot_data["settings"]
    audit_logger: AuditLogger = context.bot_data.get("audit_logger")
    user_id = update.effective_user.id

    if not settings.enable_project_threads:
        await update.message.reply_text(
            "ℹ️ <b>Project thread mode is disabled.</b>", parse_mode="HTML"
        )
        return

    manager = context.bot_data.get("project_threads_manager")
    if not manager:
        await update.message.reply_text(
            "❌ <b>Project thread manager not initialized.</b>", parse_mode="HTML"
        )
        return

    status_msg = await update.message.reply_text(
        "🔄 <b>Syncing project topics...</b>", parse_mode="HTML"
    )

    if settings.project_threads_mode == "private":
        if not _is_private_chat(update):
            await status_msg.edit_text(
                "❌ <b>Private Thread Mode</b>\n\n"
                "Run <code>/sync_threads</code> in your private chat with the bot.",
                parse_mode="HTML",
            )
            return
        target_chat_id = update.effective_chat.id
    else:
        if settings.project_threads_chat_id is None:
            await status_msg.edit_text(
                "❌ <b>Group Thread Mode Misconfigured</b>\n\n"
                "Set <code>PROJECT_THREADS_CHAT_ID</code> first.",
                parse_mode="HTML",
            )
            return
        if (
            not update.effective_chat
            or update.effective_chat.id != settings.project_threads_chat_id
        ):
            await status_msg.edit_text(
                "❌ <b>Group Thread Mode</b>\n\n"
                "Run <code>/sync_threads</code> in the configured project threads group.",
                parse_mode="HTML",
            )
            return
        target_chat_id = settings.project_threads_chat_id

    try:
        if not settings.projects_config_path:
            await status_msg.edit_text(
                "❌ <b>Project thread mode is misconfigured</b>\n\n"
                "Set <code>PROJECTS_CONFIG_PATH</code> to a valid YAML file.",
                parse_mode="HTML",
            )
            if audit_logger:
                await audit_logger.log_command(user_id, "sync_threads", [], False)
            return

        registry = load_project_registry(
            config_path=settings.projects_config_path,
            approved_directory=settings.approved_directory,
        )
        manager.registry = registry
        context.bot_data["project_registry"] = registry

        result = await manager.sync_topics(context.bot, chat_id=target_chat_id)
        await status_msg.edit_text(
            "✅ <b>Project topic sync complete</b>\n\n"
            f"• Created: <b>{result.created}</b>\n"
            f"• Reused: <b>{result.reused}</b>\n"
            f"• Renamed: <b>{result.renamed}</b>\n"
            f"• Reopened: <b>{result.reopened}</b>\n"
            f"• Closed: <b>{result.closed}</b>\n"
            f"• Deactivated: <b>{result.deactivated}</b>\n"
            f"• Failed: <b>{result.failed}</b>",
            parse_mode="HTML",
        )
        if audit_logger:
            await audit_logger.log_command(user_id, "sync_threads", [], True)
    except PrivateTopicsUnavailableError:
        await status_msg.edit_text(
            manager.private_topics_unavailable_message(),
            parse_mode="HTML",
        )
        if audit_logger:
            await audit_logger.log_command(user_id, "sync_threads", [], False)
    except Exception as e:
        await status_msg.edit_text(
            f"❌ <b>Project topic sync failed</b>\n\n{escape_html(str(e))}",
            parse_mode="HTML",
        )
        if audit_logger:
            await audit_logger.log_command(user_id, "sync_threads", [], False)


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
    context.user_data["force_new_session"] = True

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
    project_root = _get_thread_project_root(settings, context)
    directory_root = project_root or settings.approved_directory

    try:
        # Handle known navigation shortcuts first
        if target_path == "/":
            resolved_path = directory_root
        elif target_path == "..":
            resolved_path = current_dir.parent
            if not _is_within_root(resolved_path, directory_root):
                resolved_path = directory_root
        else:
            # Validate path using security validator
            if security_validator:
                valid, resolved_path, error = security_validator.validate_path(
                    target_path, current_dir
                )

                if not valid:
                    await update.message.reply_text(
                        f"❌ <b>Access Denied</b>\n\n{error}"
                    )

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
                resolved_path = current_dir / target_path
                resolved_path = resolved_path.resolve()

        if project_root and not _is_within_root(resolved_path, project_root):
            await update.message.reply_text(
                "❌ <b>Access Denied</b>\n\n"
                "In thread mode, navigation is limited to the current project root.",
                parse_mode="HTML",
            )
            return

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
        relative_base = project_root or settings.approved_directory
        relative_path = resolved_path.relative_to(relative_base)
        relative_display = "/" if str(relative_path) == "." else f"{relative_path}/"
        await update.message.reply_text(
            f"✅ <b>Directory Changed</b>\n\n"
            f"📂 Current directory: <code>{relative_display}</code>"
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
        if settings.enable_project_threads:
            registry = context.bot_data.get("project_registry")
            manager = context.bot_data.get("project_threads_manager")
            if manager and getattr(manager, "registry", None):
                registry = manager.registry
            if not registry:
                await update.message.reply_text(
                    "❌ <b>Project registry is not initialized.</b>",
                    parse_mode="HTML",
                )
                return

            projects = registry.list_enabled()
            if not projects:
                await update.message.reply_text(
                    "📁 <b>No Projects Found</b>\n\n"
                    "No enabled projects found in projects config.",
                    parse_mode="HTML",
                )
                return

            project_list = "\n".join(
                [
                    f"• <b>{escape_html(p.name)}</b> "
                    f"(<code>{escape_html(p.slug)}</code>) "
                    f"→ <code>{escape_html(str(p.relative_path))}</code>"
                    for p in projects
                ]
            )

            await update.message.reply_text(
                f"📁 <b>Configured Projects</b>\n\n{project_list}",
                parse_mode="HTML",
            )
            return

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
    update.effective_user.id
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
        now = datetime.now(timezone.utc)
        actions = await quick_action_manager.get_suggestions(
            session=SessionModel(
                session_id="",  # ephemeral session for quick actions context
                user_id=user_id,
                project_path=str(current_dir),
                created_at=now,
                last_used=now,
            )
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
        status_message = "🔗 <b>Git Repository Status</b>\n\n"
        status_message += f"📂 Directory: <code>{relative_path}/</code>\n"
        status_message += f"🌿 Branch: <code>{git_status.branch}</code>\n"

        if git_status.ahead > 0:
            status_message += f"⬆️ Ahead: {git_status.ahead} commits\n"
        if git_status.behind > 0:
            status_message += f"⬇️ Behind: {git_status.behind} commits\n"

        # Show file changes
        if not git_status.is_clean:
            status_message += "\n<b>Changes:</b>\n"
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


async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /restart command - gracefully restart the bot process.

    Sends a confirmation message then triggers SIGTERM so systemd
    (or any process manager with restart-on-exit) brings the bot back up.

    Auth: protected by the auth middleware (group -2) which raises
    ``ApplicationHandlerStop`` for unauthenticated users before any
    handler in group 10 runs.  No per-handler check is needed.
    """
    audit_logger: AuditLogger = context.bot_data.get("audit_logger")
    user_id = update.effective_user.id

    await update.message.reply_text(
        "🔄 <b>Restarting bot…</b>\n\nBack shortly.",
        parse_mode="HTML",
    )

    if audit_logger:
        await audit_logger.log_command(user_id, "restart", [], True)

    logger.info("Restart requested via /restart command", user_id=user_id)

    # SIGTERM triggers the existing graceful-shutdown handler in main.py;
    # systemd Restart=always will bring the process back up.
    os.kill(os.getpid(), signal.SIGTERM)


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


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /profile -- show or update personal profile.

    Usage:
      /profile                   -- show current profile
      /profile name Paulius      -- set name
      /profile timezone Europe/Vilnius
      /profile style concise|detailed|friendly|formal
    """
    from ...storage.models import UserProfileModel

    user = update.effective_user
    storage = context.bot_data.get("storage")
    if not storage:
        await update.message.reply_text("Storage unavailable.")
        return

    args = context.args or []

    if not args:
        profile = await storage.profiles.get_profile(user.id)
        if not profile:
            await update.message.reply_text(
                "<b>Your profile is not set yet.</b>\n\n"
                "Use:\n"
                "  <code>/profile name Your Name</code>\n"
                "  <code>/profile timezone Europe/Vilnius</code>\n"
                "  <code>/profile style concise|detailed|friendly|formal</code>",
                parse_mode="HTML",
            )
            return

        await update.message.reply_text(
            f"<b>Your Profile</b>\n\n"
            f"Name: {profile.name or '\u2014'}\n"
            f"Timezone: {profile.timezone}\n"
            f"Style: {profile.communication_style}\n"
            f"Wake time: {profile.wake_time}\n"
            f"Daily briefing: {'on ' + profile.briefing_cron if profile.briefing_enabled else 'off'}",
            parse_mode="HTML",
        )
        return

    field = args[0].lower()
    value = " ".join(args[1:]) if len(args) > 1 else ""

    if not value:
        await update.message.reply_text("Please provide a value.")
        return

    profile = await storage.profiles.get_profile(user.id)
    if not profile:
        profile = UserProfileModel(user_id=user.id)

    field_map = {
        "name": "name",
        "timezone": "timezone",
        "tz": "timezone",
        "style": "communication_style",
        "wake": "wake_time",
    }

    attr = field_map.get(field)
    if not attr:
        await update.message.reply_text(
            f"Unknown field '{escape_html(field)}'. Valid: name, timezone, style, wake",
            parse_mode="HTML",
        )
        return

    updated_profile = UserProfileModel(
        user_id=profile.user_id,
        name=value if attr == "name" else profile.name,
        timezone=value if attr == "timezone" else profile.timezone,
        wake_time=value if attr == "wake_time" else profile.wake_time,
        communication_style=value if attr == "communication_style" else profile.communication_style,
        briefing_enabled=profile.briefing_enabled,
        briefing_cron=profile.briefing_cron,
        briefing_chat_id=profile.briefing_chat_id,
    )
    await storage.profiles.upsert_profile(updated_profile)
    await update.message.reply_text(
        f"Profile updated: <b>{escape_html(field)}</b> = {escape_html(value)}",
        parse_mode="HTML",
    )


async def remember_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /remember <key> <value> — store a persistent fact.

    Example: /remember hobby orienteering
    """
    user = update.effective_user
    storage = context.bot_data.get("storage")
    args = context.args or []

    if len(args) < 2:
        await update.message.reply_text(
            "Usage: <code>/remember &lt;key&gt; &lt;value&gt;</code>\n"
            "Example: <code>/remember hobby orienteering</code>",
            parse_mode="HTML",
        )
        return

    key = args[0].rstrip(":")
    value = " ".join(args[1:])
    await storage.memories.set_memory(user.id, key, value)
    await update.message.reply_text(
        f"Remembered: <b>{escape_html(key)}</b> = {escape_html(value)}",
        parse_mode="HTML",
    )


async def memories_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /memories — list all stored facts."""
    user = update.effective_user
    storage = context.bot_data.get("storage")
    memories = await storage.memories.list_memories(user.id)

    if not memories:
        await update.message.reply_text("No memories stored yet. Use /remember to add some.")
        return

    lines = ["<b>Your Memories</b>\n"]
    for mem in memories:
        lines.append(f"[{mem.id}] <b>{escape_html(mem.key)}</b>: {escape_html(mem.value)}")

    lines.append("\nUse <code>/forget &lt;id&gt;</code> to remove one.")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /forget <id> — remove a stored memory by ID."""
    user = update.effective_user
    storage = context.bot_data.get("storage")
    args = context.args or []

    if not args or not args[0].isdigit():
        await update.message.reply_text(
            "Usage: <code>/forget &lt;id&gt;</code> — get the ID from /memories",
            parse_mode="HTML",
        )
        return

    memory_id = int(args[0])
    deleted = await storage.memories.delete_memory(user.id, memory_id)

    if deleted:
        await update.message.reply_text(f"Memory [{memory_id}] deleted.")
    else:
        await update.message.reply_text(f"Memory [{memory_id}] not found.")


async def task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /task — manage personal tasks.

    Usage:
      /task list               — list open tasks
      /task add <title>        — add a new task
      /task done <id>          — mark task as done
      /task delete <id>        — delete a task
      /task all                — list all tasks including done
    """
    from ...storage.models import TaskModel as _TaskModel

    user = update.effective_user
    storage = context.bot_data.get("storage")
    args = context.args or []

    subcommand = args[0].lower() if args else ""

    if subcommand == "add":
        title = " ".join(args[1:])
        if not title:
            await update.message.reply_text(
                "Usage: <code>/task add &lt;title&gt;</code>", parse_mode="HTML"
            )
            return
        task = await storage.tasks.create_task(
            _TaskModel(user_id=user.id, title=title)
        )
        await update.message.reply_text(f"Task [{task.id}] added: {escape_html(title)}")

    elif subcommand == "list":
        tasks = await storage.tasks.list_tasks(user.id, status="open")
        if not tasks:
            await update.message.reply_text(
                "No open tasks. Add one with <code>/task add &lt;title&gt;</code>.",
                parse_mode="HTML",
            )
            return
        lines = ["<b>Open Tasks</b>\n"]
        for t in tasks:
            due = f"  <i>due {t.due_date}</i>" if t.due_date else ""
            lines.append(f"[{t.id}] {escape_html(t.title)}{due}")
        lines.append("\n<code>/task done &lt;id&gt;</code> to complete")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    elif subcommand == "all":
        tasks = await storage.tasks.list_tasks(user.id)
        if not tasks:
            await update.message.reply_text("No tasks found.")
            return
        lines = ["<b>All Tasks</b>\n"]
        for t in tasks:
            icon = "done" if t.status == "done" else "open"
            lines.append(f"[{icon}] [{t.id}] {escape_html(t.title)}")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    elif subcommand == "done":
        if len(args) < 2 or not args[1].isdigit():
            await update.message.reply_text(
                "Usage: <code>/task done &lt;id&gt;</code>", parse_mode="HTML"
            )
            return
        task_id = int(args[1])
        updated = await storage.tasks.update_task_status(task_id, "done")
        if updated:
            await update.message.reply_text(f"Task [{task_id}] marked as done.")
        else:
            await update.message.reply_text(f"Task [{task_id}] not found.")

    elif subcommand == "delete":
        if len(args) < 2 or not args[1].isdigit():
            await update.message.reply_text(
                "Usage: <code>/task delete &lt;id&gt;</code>", parse_mode="HTML"
            )
            return
        task_id = int(args[1])
        deleted = await storage.tasks.delete_task(user.id, task_id)
        if deleted:
            await update.message.reply_text(f"Task [{task_id}] deleted.")
        else:
            await update.message.reply_text(f"Task [{task_id}] not found.")

    else:
        await update.message.reply_text(
            "<b>Task Commands</b>\n\n"
            "<code>/task add &lt;title&gt;</code> — add task\n"
            "<code>/task list</code> — list open tasks\n"
            "<code>/task done &lt;id&gt;</code> — mark done\n"
            "<code>/task delete &lt;id&gt;</code> — delete\n"
            "<code>/task all</code> — all tasks",
            parse_mode="HTML",
        )


async def briefing_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /briefing — manage daily briefing.

    Usage:
      /briefing          — show current status
      /briefing now      — send briefing immediately
      /briefing on       — enable daily briefing at stored time
      /briefing on 09:00 — enable at specific time (HH:MM)
      /briefing off      — disable daily briefing
    """
    from ...storage.models import UserProfileModel

    user = update.effective_user
    storage = context.bot_data.get("storage")
    assembler = context.bot_data.get("briefing_assembler")
    briefing_scheduler = context.bot_data.get("briefing_scheduler")
    args = context.args or []
    subcommand = args[0].lower() if args else ""

    if subcommand == "now":
        if not assembler:
            await update.message.reply_text("Briefing unavailable.")
            return
        text = await assembler.build(user_id=user.id)
        await update.message.reply_text(text, parse_mode="HTML")
        return

    if subcommand == "off":
        profile = await storage.profiles.get_profile(user.id)
        if profile:
            updated = UserProfileModel(
                user_id=profile.user_id,
                name=profile.name,
                timezone=profile.timezone,
                wake_time=profile.wake_time,
                communication_style=profile.communication_style,
                briefing_enabled=False,
                briefing_cron=profile.briefing_cron,
                briefing_chat_id=profile.briefing_chat_id,
            )
            await storage.profiles.upsert_profile(updated)
        if briefing_scheduler:
            await briefing_scheduler.disable(user.id)
        await update.message.reply_text("Daily briefing disabled.")
        return

    if subcommand == "on":
        time_arg = args[1] if len(args) > 1 else "08:00"
        try:
            hour, minute = (int(x) for x in time_arg.split(":"))
            cron = f"{minute} {hour} * * *"
        except (ValueError, AttributeError):
            await update.message.reply_text("Invalid time. Use HH:MM format, e.g. 09:00")
            return
        chat_id = update.message.chat_id
        if briefing_scheduler:
            await briefing_scheduler.enable(user.id, chat_id=chat_id, cron=cron)
        await update.message.reply_text(
            f"Daily briefing enabled at {escape_html(time_arg)}.\n"
            f"Use <code>/briefing now</code> to preview it.",
            parse_mode="HTML",
        )
        return

    # Default: show status
    profile = await storage.profiles.get_profile(user.id)
    if profile and profile.briefing_enabled:
        await update.message.reply_text(
            f"<b>Daily Briefing</b>\n\n"
            f"Status: Enabled\n"
            f"Schedule: <code>{profile.briefing_cron}</code>\n\n"
            f"<code>/briefing now</code> — preview\n"
            f"<code>/briefing off</code> — disable",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            "<b>Daily Briefing</b>\n\n"
            "Status: Disabled\n\n"
            "<code>/briefing on 09:00</code> — enable at 9 AM\n"
            "<code>/briefing now</code> — send right now",
            parse_mode="HTML",
        )
