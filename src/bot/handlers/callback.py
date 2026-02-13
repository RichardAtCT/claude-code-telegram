"""Handle inline keyboard callbacks."""

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ...claude.facade import ClaudeIntegration
from ...config.settings import Settings
from ...security.audit import AuditLogger
from ...security.validators import SecurityValidator
from ..utils.html_format import escape_html

logger = structlog.get_logger()


async def handle_callback_query(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Route callback queries to appropriate handlers."""
    query = update.callback_query
    await query.answer()  # Acknowledge the callback

    user_id = query.from_user.id
    data = query.data

    logger.info("Processing callback query", user_id=user_id, callback_data=data)

    try:
        # Parse callback data
        if ":" in data:
            action, param = data.split(":", 1)
        else:
            action, param = data, None

        # Route to appropriate handler
        handlers = {
            "cd": handle_cd_callback,
            "action": handle_action_callback,
            "confirm": handle_confirm_callback,
            "quick": handle_quick_action_callback,
            "followup": handle_followup_callback,
            "conversation": handle_conversation_callback,
            "git": handle_git_callback,
            "export": handle_export_callback,
        }

        handler = handlers.get(action)
        if handler:
            await handler(query, param, context)
        else:
            await query.edit_message_text(
                "❌ <b>Unknown Action</b>\n\n"
                "This button action is not recognized. "
                "The bot may have been updated since this message was sent.",
                parse_mode="HTML",
            )

    except Exception as e:
        logger.error(
            "Error handling callback query",
            error=str(e),
            user_id=user_id,
            callback_data=data,
        )

        try:
            await query.edit_message_text(
                "❌ <b>Error Processing Action</b>\n\n"
                "An error occurred while processing your request.\n"
                "Please try again or use text commands.",
                parse_mode="HTML",
            )
        except Exception:
            # If we can't edit the message, send a new one
            await query.message.reply_text(
                "❌ <b>Error Processing Action</b>\n\n"
                "An error occurred while processing your request.",
                parse_mode="HTML",
            )


async def handle_cd_callback(
    query, project_name: str, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle directory change from inline keyboard."""
    user_id = query.from_user.id
    settings: Settings = context.bot_data["settings"]
    security_validator: SecurityValidator = context.bot_data.get("security_validator")
    audit_logger: AuditLogger = context.bot_data.get("audit_logger")

    try:
        current_dir = context.user_data.get(
            "current_directory", settings.approved_directory
        )

        # Handle special paths
        if project_name == "/":
            new_path = settings.approved_directory
        elif project_name == "..":
            new_path = current_dir.parent
            # Ensure we don't go above approved directory
            if not str(new_path).startswith(str(settings.approved_directory)):
                new_path = settings.approved_directory
        else:
            new_path = settings.approved_directory / project_name

        # Validate path if security validator is available
        if security_validator:
            # Pass the absolute path for validation
            valid, resolved_path, error = security_validator.validate_path(
                str(new_path), settings.approved_directory
            )
            if not valid:
                await query.edit_message_text(
                    f"❌ <b>Access Denied</b>\n\n{escape_html(error)}",
                    parse_mode="HTML",
                )
                return
            # Use the validated path
            new_path = resolved_path

        # Check if directory exists
        if not new_path.exists() or not new_path.is_dir():
            await query.edit_message_text(
                f"❌ <b>Directory Not Found</b>\n\n"
                f"The directory <code>{escape_html(project_name)}</code> no longer exists or is not accessible.",
                parse_mode="HTML",
            )
            return

        # Update directory and clear session
        context.user_data["current_directory"] = new_path
        context.user_data["claude_session_id"] = None

        # Send confirmation with new directory info
        relative_path = new_path.relative_to(settings.approved_directory)

        # Add navigation buttons
        keyboard = [
            [
                InlineKeyboardButton("📁 List Files", callback_data="action:ls"),
                InlineKeyboardButton(
                    "🆕 New Session", callback_data="action:new_session"
                ),
            ],
            [
                InlineKeyboardButton(
                    "📋 Projects", callback_data="action:show_projects"
                ),
                InlineKeyboardButton("📊 Status", callback_data="action:status"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"✅ <b>Directory Changed</b>\n\n"
            f"📂 Current directory: <code>{escape_html(str(relative_path))}/</code>\n\n"
            f"🔄 Claude session cleared. You can now start coding in this directory!",
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

        # Log successful directory change
        if audit_logger:
            await audit_logger.log_command(
                user_id=user_id, command="cd", args=[project_name], success=True
            )

    except Exception as e:
        await query.edit_message_text(
            f"❌ <b>Error changing directory</b>\n\n{escape_html(str(e))}",
            parse_mode="HTML",
        )

        if audit_logger:
            await audit_logger.log_command(
                user_id=user_id, command="cd", args=[project_name], success=False
            )


async def handle_action_callback(
    query, action_type: str, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle general action callbacks."""
    actions = {
        "help": _handle_help_action,
        "show_projects": _handle_show_projects_action,
        "new_session": _handle_new_session_action,
        "continue": _handle_continue_action,
        "end_session": _handle_end_session_action,
        "status": _handle_status_action,
        "ls": _handle_ls_action,
        "start_coding": _handle_start_coding_action,
        "quick_actions": _handle_quick_actions_action,
        "refresh_status": _handle_refresh_status_action,
        "refresh_ls": _handle_refresh_ls_action,
        "export": _handle_export_action,
    }

    handler = actions.get(action_type)
    if handler:
        await handler(query, context)
    else:
        await query.edit_message_text(
            f"❌ <b>Unknown Action: {escape_html(action_type)}</b>\n\n"
            "This action is not implemented yet.",
            parse_mode="HTML",
        )


async def handle_confirm_callback(
    query, confirmation_type: str, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle confirmation dialogs."""
    if confirmation_type == "yes":
        await query.edit_message_text(
            "✅ <b>Confirmed</b>\n\nAction will be processed.",
            parse_mode="HTML",
        )
    elif confirmation_type == "no":
        await query.edit_message_text(
            "❌ <b>Cancelled</b>\n\nAction was cancelled.",
            parse_mode="HTML",
        )
    else:
        await query.edit_message_text(
            "❓ <b>Unknown confirmation response</b>",
            parse_mode="HTML",
        )


# Action handlers


async def _handle_help_action(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle help action."""
    help_text = (
        "🤖 <b>Quick Help</b>\n\n"
        "<b>Navigation:</b>\n"
        "• <code>/ls</code> - List files\n"
        "• <code>/cd &lt;dir&gt;</code> - Change directory\n"
        "• <code>/projects</code> - Show projects\n\n"
        "<b>Sessions:</b>\n"
        "• <code>/new</code> - New Claude session\n"
        "• <code>/status</code> - Session status\n\n"
        "<b>Tips:</b>\n"
        "• Send any text to interact with Claude\n"
        "• Upload files for code review\n"
        "• Use buttons for quick actions\n\n"
        "Use <code>/help</code> for detailed help."
    )

    keyboard = [
        [
            InlineKeyboardButton("📖 Full Help", callback_data="action:full_help"),
            InlineKeyboardButton("🏠 Main Menu", callback_data="action:main_menu"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        help_text, parse_mode="HTML", reply_markup=reply_markup
    )


async def _handle_show_projects_action(
    query, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle show projects action."""
    settings: Settings = context.bot_data["settings"]

    try:
        # Get directories in approved directory
        projects = []
        for item in sorted(settings.approved_directory.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                projects.append(item.name)

        if not projects:
            await query.edit_message_text(
                "📁 <b>No Projects Found</b>\n\n"
                "No subdirectories found in your approved directory.\n"
                "Create some directories to organize your projects!",
                parse_mode="HTML",
            )
            return

        # Create project buttons
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
                InlineKeyboardButton("🏠 Root", callback_data="cd:/"),
                InlineKeyboardButton(
                    "🔄 Refresh", callback_data="action:show_projects"
                ),
            ]
        )

        reply_markup = InlineKeyboardMarkup(keyboard)
        project_list = "\n".join(
            [f"• <code>{escape_html(project)}/</code>" for project in projects]
        )

        await query.edit_message_text(
            f"📁 <b>Available Projects</b>\n\n"
            f"{project_list}\n\n"
            f"Click a project to navigate to it:",
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

    except Exception as e:
        await query.edit_message_text(f"❌ Error loading projects: {str(e)}")


async def _handle_new_session_action(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle new session action."""
    settings: Settings = context.bot_data["settings"]

    # Clear session
    context.user_data["claude_session_id"] = None
    context.user_data["session_started"] = True

    current_dir = context.user_data.get(
        "current_directory", settings.approved_directory
    )
    relative_path = current_dir.relative_to(settings.approved_directory)

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

    await query.edit_message_text(
        f"🆕 <b>New Claude Code Session</b>\n\n"
        f"📂 Working directory: <code>{escape_html(str(relative_path))}/</code>\n\n"
        f"Ready to help you code! Send me a message to get started:",
        parse_mode="HTML",
        reply_markup=reply_markup,
    )


async def _handle_end_session_action(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle end session action."""
    settings: Settings = context.bot_data["settings"]

    # Check if there's an active session
    claude_session_id = context.user_data.get("claude_session_id")

    if not claude_session_id:
        await query.edit_message_text(
            "ℹ️ <b>No Active Session</b>\n\n"
            "There's no active Claude session to end.\n\n"
            "<b>What you can do:</b>\n"
            "• Use the button below to start a new session\n"
            "• Check your session status\n"
            "• Send any message to start a conversation",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🆕 New Session", callback_data="action:new_session"
                        )
                    ],
                    [InlineKeyboardButton("📊 Status", callback_data="action:status")],
                ]
            ),
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

    await query.edit_message_text(
        "✅ <b>Session Ended</b>\n\n"
        f"Your Claude session has been terminated.\n\n"
        f"<b>Current Status:</b>\n"
        f"• Directory: <code>{escape_html(str(relative_path))}/</code>\n"
        f"• Session: None\n"
        f"• Ready for new commands\n\n"
        f"<b>Next Steps:</b>\n"
        f"• Start a new session\n"
        f"• Check status\n"
        f"• Send any message to begin a new conversation",
        parse_mode="HTML",
        reply_markup=reply_markup,
    )


async def _handle_continue_action(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle continue session action."""
    user_id = query.from_user.id
    settings: Settings = context.bot_data["settings"]
    claude_integration: ClaudeIntegration = context.bot_data.get("claude_integration")

    current_dir = context.user_data.get(
        "current_directory", settings.approved_directory
    )

    try:
        if not claude_integration:
            await query.edit_message_text(
                "❌ <b>Claude Integration Not Available</b>\n\n"
                "Claude integration is not properly configured.",
                parse_mode="HTML",
            )
            return

        # Check if there's an existing session in user context
        claude_session_id = context.user_data.get("claude_session_id")

        if claude_session_id:
            # Continue with the existing session (no prompt = use --continue)
            await query.edit_message_text(
                f"🔄 <b>Continuing Session</b>\n\n"
                f"Session ID: <code>{escape_html(claude_session_id[:8])}...</code>\n"
                f"Directory: <code>{escape_html(str(current_dir.relative_to(settings.approved_directory)))}/</code>\n\n"
                f"Continuing where you left off...",
                parse_mode="HTML",
            )

            claude_response = await claude_integration.run_command(
                prompt="",  # Empty prompt triggers --continue
                working_directory=current_dir,
                user_id=user_id,
                session_id=claude_session_id,
            )
        else:
            # No session in context, try to find the most recent session
            await query.edit_message_text(
                "🔍 <b>Looking for Recent Session</b>\n\n"
                "Searching for your most recent session in this directory...",
                parse_mode="HTML",
            )

            claude_response = await claude_integration.continue_session(
                user_id=user_id,
                working_directory=current_dir,
                prompt=None,  # No prompt = use --continue
            )

        if claude_response:
            # Update session ID in context
            context.user_data["claude_session_id"] = claude_response.session_id

            # Send Claude's response
            await query.message.reply_text(
                f"✅ <b>Session Continued</b>\n\n"
                f"{escape_html(claude_response.content[:500])}{'...' if len(claude_response.content) > 500 else ''}",
                parse_mode="HTML",
            )
        else:
            # No session found to continue
            await query.edit_message_text(
                "❌ <b>No Session Found</b>\n\n"
                f"No recent Claude session found in this directory.\n"
                f"Directory: <code>{escape_html(str(current_dir.relative_to(settings.approved_directory)))}/</code>\n\n"
                f"<b>What you can do:</b>\n"
                f"• Use the button below to start a fresh session\n"
                f"• Check your session status\n"
                f"• Navigate to a different directory",
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
        logger.error("Error in continue action", error=str(e), user_id=user_id)
        await query.edit_message_text(
            f"❌ <b>Error Continuing Session</b>\n\n"
            f"An error occurred: <code>{escape_html(str(e))}</code>\n\n"
            f"Try starting a new session instead.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🆕 New Session", callback_data="action:new_session"
                        )
                    ]
                ]
            ),
        )


async def _handle_status_action(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle status action."""
    # This essentially duplicates the /status command functionality
    user_id = query.from_user.id
    settings: Settings = context.bot_data["settings"]

    claude_session_id = context.user_data.get("claude_session_id")
    current_dir = context.user_data.get(
        "current_directory", settings.approved_directory
    )
    relative_path = current_dir.relative_to(settings.approved_directory)

    # Get usage info if rate limiter is available
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

    status_lines = [
        "📊 <b>Session Status</b>",
        "",
        f"📂 Directory: <code>{escape_html(str(relative_path))}/</code>",
        f"🤖 Claude Session: {'✅ Active' if claude_session_id else '❌ None'}",
        usage_info.rstrip(),
    ]

    if claude_session_id:
        status_lines.append(
            f"🆔 Session ID: <code>{escape_html(claude_session_id[:8])}...</code>"
        )

    # Add action buttons
    keyboard = []
    if claude_session_id:
        keyboard.append(
            [
                InlineKeyboardButton("🔄 Continue", callback_data="action:continue"),
                InlineKeyboardButton(
                    "🛑 End Session", callback_data="action:end_session"
                ),
            ]
        )
        keyboard.append(
            [
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
            InlineKeyboardButton("🔄 Refresh", callback_data="action:refresh_status"),
            InlineKeyboardButton("📁 Projects", callback_data="action:show_projects"),
        ]
    )

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "\n".join(status_lines), parse_mode="HTML", reply_markup=reply_markup
    )


async def _handle_ls_action(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ls action."""
    settings: Settings = context.bot_data["settings"]
    current_dir = context.user_data.get(
        "current_directory", settings.approved_directory
    )

    try:
        # List directory contents (similar to /ls command)
        items = []
        directories = []
        files = []

        for item in sorted(current_dir.iterdir()):
            if item.name.startswith("."):
                continue

            # Escape markdown special characters in filenames
            safe_name = _escape_markdown(item.name)

            if item.is_dir():
                directories.append(f"📁 {safe_name}/")
            else:
                try:
                    size = item.stat().st_size
                    size_str = _format_file_size(size)
                    files.append(f"📄 {safe_name} ({size_str})")
                except OSError:
                    files.append(f"📄 {safe_name}")

        items = directories + files
        relative_path = current_dir.relative_to(settings.approved_directory)

        if not items:
            message = f"📂 <code>{escape_html(str(relative_path))}/</code>\n\n<i>(empty directory)</i>"
        else:
            message = f"📂 <code>{escape_html(str(relative_path))}/</code>\n\n"
            max_items = 30  # Limit for inline display
            if len(items) > max_items:
                shown_items = items[:max_items]
                message += "\n".join(shown_items)
                message += f"\n\n<i>... and {len(items) - max_items} more items</i>"
            else:
                message += "\n".join(items)

        # Add buttons
        keyboard = []
        if current_dir != settings.approved_directory:
            keyboard.append(
                [
                    InlineKeyboardButton("⬆️ Go Up", callback_data="cd:.."),
                    InlineKeyboardButton("🏠 Root", callback_data="cd:/"),
                ]
            )

        keyboard.append(
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="action:refresh_ls"),
                InlineKeyboardButton(
                    "📋 Projects", callback_data="action:show_projects"
                ),
            ]
        )

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            message, parse_mode="HTML", reply_markup=reply_markup
        )

    except Exception as e:
        await query.edit_message_text(f"❌ Error listing directory: {str(e)}")


async def _handle_start_coding_action(
    query, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle start coding action."""
    await query.edit_message_text(
        "🚀 <b>Ready to Code!</b>\n\n"
        "Send me any message to start coding with Claude:\n\n"
        "<b>Examples:</b>\n"
        '• <i>"Create a Python script that..."</i>\n'
        '• <i>"Help me debug this code..."</i>\n'
        '• <i>"Explain how this file works..."</i>\n'
        "• Upload a file for review\n\n"
        "I'm here to help with all your coding needs!",
        parse_mode="HTML",
    )


async def _handle_quick_actions_action(
    query, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle quick actions menu."""
    keyboard = [
        [
            InlineKeyboardButton("🧪 Run Tests", callback_data="quick:test"),
            InlineKeyboardButton("📦 Install Deps", callback_data="quick:install"),
        ],
        [
            InlineKeyboardButton("🎨 Format Code", callback_data="quick:format"),
            InlineKeyboardButton("🔍 Find TODOs", callback_data="quick:find_todos"),
        ],
        [
            InlineKeyboardButton("🔨 Build", callback_data="quick:build"),
            InlineKeyboardButton("🚀 Start Server", callback_data="quick:start"),
        ],
        [
            InlineKeyboardButton("📊 Git Status", callback_data="quick:git_status"),
            InlineKeyboardButton("🔧 Lint Code", callback_data="quick:lint"),
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="action:new_session")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "🛠️ <b>Quick Actions</b>\n\n"
        "Choose a common development task:\n\n"
        "<i>Note: These will be fully functional once Claude Code integration is complete.</i>",
        parse_mode="HTML",
        reply_markup=reply_markup,
    )


async def _handle_refresh_status_action(
    query, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle refresh status action."""
    await _handle_status_action(query, context)


async def _handle_refresh_ls_action(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle refresh ls action."""
    await _handle_ls_action(query, context)


async def _handle_export_action(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle export action."""
    await query.edit_message_text(
        "📤 <b>Export Session</b>\n\n"
        "Session export functionality will be available once the storage layer is implemented.\n\n"
        "<b>Planned features:</b>\n"
        "• Export conversation history\n"
        "• Save session state\n"
        "• Share conversations\n"
        "• Create session backups\n\n"
        "<i>Coming in the next development phase!</i>",
        parse_mode="HTML",
    )


async def handle_quick_action_callback(
    query, action_id: str, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle quick action callbacks."""
    user_id = query.from_user.id

    # Get quick actions manager from bot data if available
    quick_actions = context.bot_data.get("quick_actions")

    if not quick_actions:
        await query.edit_message_text(
            "❌ <b>Quick Actions Not Available</b>\n\n"
            "Quick actions feature is not available.",
            parse_mode="HTML",
        )
        return

    # Get Claude integration
    claude_integration: ClaudeIntegration = context.bot_data.get("claude_integration")
    if not claude_integration:
        await query.edit_message_text(
            "❌ <b>Claude Integration Not Available</b>\n\n"
            "Claude integration is not properly configured.",
            parse_mode="HTML",
        )
        return

    settings: Settings = context.bot_data["settings"]
    current_dir = context.user_data.get(
        "current_directory", settings.approved_directory
    )

    try:
        # Get the action from the manager
        action = quick_actions.actions.get(action_id)
        if not action:
            await query.edit_message_text(
                f"❌ <b>Action Not Found</b>\n\n"
                f"Quick action '{escape_html(action_id)}' is not available.",
                parse_mode="HTML",
            )
            return

        # Execute the action
        await query.edit_message_text(
            f"🚀 <b>Executing {action.icon} {escape_html(action.name)}</b>\n\n"
            f"Running quick action in directory: <code>{escape_html(str(current_dir.relative_to(settings.approved_directory)))}/</code>\n\n"
            f"Please wait...",
            parse_mode="HTML",
        )

        # Run the action through Claude
        claude_response = await claude_integration.run_command(
            prompt=action.prompt, working_directory=current_dir, user_id=user_id
        )

        if claude_response:
            # Format and send the response
            response_text = escape_html(claude_response.content)
            if len(response_text) > 4000:
                response_text = (
                    response_text[:4000] + "...\n\n<i>(Response truncated)</i>"
                )

            await query.message.reply_text(
                f"✅ <b>{action.icon} {escape_html(action.name)} Complete</b>\n\n{response_text}",
                parse_mode="HTML",
            )
        else:
            await query.edit_message_text(
                f"❌ <b>Action Failed</b>\n\n"
                f"Failed to execute {escape_html(action.name)}. Please try again.",
                parse_mode="HTML",
            )

    except Exception as e:
        logger.error("Quick action execution failed", error=str(e), user_id=user_id)
        await query.edit_message_text(
            f"❌ <b>Action Error</b>\n\n"
            f"An error occurred while executing {escape_html(action_id)}: {escape_html(str(e))}",
            parse_mode="HTML",
        )


async def handle_followup_callback(
    query, suggestion_hash: str, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle follow-up suggestion callbacks."""
    user_id = query.from_user.id

    # Get conversation enhancer from bot data if available
    conversation_enhancer = context.bot_data.get("conversation_enhancer")

    if not conversation_enhancer:
        await query.edit_message_text(
            "❌ <b>Follow-up Not Available</b>\n\n"
            "Conversation enhancement features are not available.",
            parse_mode="HTML",
        )
        return

    try:
        # Get stored suggestions (this would need to be implemented in the enhancer)
        # For now, we'll provide a generic response
        await query.edit_message_text(
            "💡 <b>Follow-up Suggestion Selected</b>\n\n"
            "This follow-up suggestion will be implemented once the conversation "
            "enhancement system is fully integrated with the message handler.\n\n"
            "<b>Current Status:</b>\n"
            "• Suggestion received ✅\n"
            "• Integration pending 🔄\n\n"
            "<i>You can continue the conversation by sending a new message.</i>",
            parse_mode="HTML",
        )

        logger.info(
            "Follow-up suggestion selected",
            user_id=user_id,
            suggestion_hash=suggestion_hash,
        )

    except Exception as e:
        logger.error(
            "Error handling follow-up callback",
            error=str(e),
            user_id=user_id,
            suggestion_hash=suggestion_hash,
        )

        await query.edit_message_text(
            "❌ <b>Error Processing Follow-up</b>\n\n"
            "An error occurred while processing your follow-up suggestion.",
            parse_mode="HTML",
        )


async def handle_conversation_callback(
    query, action_type: str, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle conversation control callbacks."""
    user_id = query.from_user.id
    settings: Settings = context.bot_data["settings"]

    if action_type == "continue":
        # Remove suggestion buttons and show continue message
        await query.edit_message_text(
            "✅ <b>Continuing Conversation</b>\n\n"
            "Send me your next message to continue coding!\n\n"
            "I'm ready to help with:\n"
            "• Code review and debugging\n"
            "• Feature implementation\n"
            "• Architecture decisions\n"
            "• Testing and optimization\n"
            "• Documentation\n\n"
            "<i>Just type your request or upload files.</i>",
            parse_mode="HTML",
        )

    elif action_type == "end":
        # End the current session
        conversation_enhancer = context.bot_data.get("conversation_enhancer")
        if conversation_enhancer:
            conversation_enhancer.clear_context(user_id)

        # Clear session data
        context.user_data["claude_session_id"] = None
        context.user_data["session_started"] = False

        current_dir = context.user_data.get(
            "current_directory", settings.approved_directory
        )
        relative_path = current_dir.relative_to(settings.approved_directory)

        # Create quick action buttons
        keyboard = [
            [
                InlineKeyboardButton(
                    "🆕 New Session", callback_data="action:new_session"
                ),
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

        await query.edit_message_text(
            "✅ <b>Conversation Ended</b>\n\n"
            f"Your Claude session has been terminated.\n\n"
            f"<b>Current Status:</b>\n"
            f"• Directory: <code>{escape_html(str(relative_path))}/</code>\n"
            f"• Session: None\n"
            f"• Ready for new commands\n\n"
            f"<b>Next Steps:</b>\n"
            f"• Start a new session\n"
            f"• Check status\n"
            f"• Send any message to begin a new conversation",
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

        logger.info("Conversation ended via callback", user_id=user_id)

    else:
        await query.edit_message_text(
            f"❌ <b>Unknown Conversation Action: {escape_html(action_type)}</b>\n\n"
            "This conversation action is not recognized.",
            parse_mode="HTML",
        )


async def handle_git_callback(
    query, git_action: str, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle git-related callbacks."""
    user_id = query.from_user.id
    settings: Settings = context.bot_data["settings"]
    features = context.bot_data.get("features")

    if not features or not features.is_enabled("git"):
        await query.edit_message_text(
            "❌ <b>Git Integration Disabled</b>\n\n"
            "Git integration feature is not enabled.",
            parse_mode="HTML",
        )
        return

    current_dir = context.user_data.get(
        "current_directory", settings.approved_directory
    )

    try:
        git_integration = features.get_git_integration()
        if not git_integration:
            await query.edit_message_text(
                "❌ <b>Git Integration Unavailable</b>\n\n"
                "Git integration service is not available.",
                parse_mode="HTML",
            )
            return

        if git_action == "status":
            # Refresh git status
            git_status = await git_integration.get_status(current_dir)
            status_message = git_integration.format_status(git_status)

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

            await query.edit_message_text(
                status_message, parse_mode="HTML", reply_markup=reply_markup
            )

        elif git_action == "diff":
            # Show git diff
            diff_output = await git_integration.get_diff(current_dir)

            if not diff_output.strip():
                diff_message = "📊 <b>Git Diff</b>\n\n<i>No changes to show.</i>"
            else:
                # Clean up diff output for Telegram
                # Remove emoji symbols that interfere with parsing
                clean_diff = (
                    diff_output.replace("➕", "+").replace("➖", "-").replace("📍", "@")
                )

                # Limit diff output
                max_length = 2000
                if len(clean_diff) > max_length:
                    clean_diff = (
                        clean_diff[:max_length] + "\n\n... output truncated ..."
                    )

                escaped_diff = escape_html(clean_diff)
                diff_message = (
                    f"📊 <b>Git Diff</b>\n\n<pre><code>{escaped_diff}</code></pre>"
                )

            keyboard = [
                [
                    InlineKeyboardButton("📜 Show Log", callback_data="git:log"),
                    InlineKeyboardButton("📊 Status", callback_data="git:status"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                diff_message, parse_mode="HTML", reply_markup=reply_markup
            )

        elif git_action == "log":
            # Show git log
            commits = await git_integration.get_file_history(current_dir, ".")

            if not commits:
                log_message = "📜 <b>Git Log</b>\n\n<i>No commits found.</i>"
            else:
                log_message = "📜 <b>Git Log</b>\n\n"
                for commit in commits[:10]:  # Show last 10 commits
                    short_hash = commit.hash[:7]
                    short_message = escape_html(commit.message[:60])
                    if len(commit.message) > 60:
                        short_message += "..."
                    log_message += f"• <code>{short_hash}</code> {short_message}\n"

            keyboard = [
                [
                    InlineKeyboardButton("📊 Show Diff", callback_data="git:diff"),
                    InlineKeyboardButton("📊 Status", callback_data="git:status"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                log_message, parse_mode="HTML", reply_markup=reply_markup
            )

        else:
            await query.edit_message_text(
                f"❌ <b>Unknown Git Action: {escape_html(git_action)}</b>\n\n"
                "This git action is not recognized.",
                parse_mode="HTML",
            )

    except Exception as e:
        logger.error(
            "Error in git callback",
            error=str(e),
            git_action=git_action,
            user_id=user_id,
        )
        await query.edit_message_text(
            f"❌ <b>Git Error</b>\n\n{escape_html(str(e))}",
            parse_mode="HTML",
        )


async def handle_export_callback(
    query, export_format: str, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle export format selection callbacks."""
    user_id = query.from_user.id
    features = context.bot_data.get("features")

    if export_format == "cancel":
        await query.edit_message_text(
            "📤 <b>Export Cancelled</b>\n\n" "Session export has been cancelled.",
            parse_mode="HTML",
        )
        return

    session_exporter = features.get_session_export() if features else None
    if not session_exporter:
        await query.edit_message_text(
            "❌ <b>Export Unavailable</b>\n\n"
            "Session export service is not available.",
            parse_mode="HTML",
        )
        return

    # Get current session
    claude_session_id = context.user_data.get("claude_session_id")
    if not claude_session_id:
        await query.edit_message_text(
            "❌ <b>No Active Session</b>\n\n" "There's no active session to export.",
            parse_mode="HTML",
        )
        return

    try:
        # Show processing message
        await query.edit_message_text(
            f"📤 <b>Exporting Session</b>\n\n"
            f"Generating {escape_html(export_format.upper())} export...",
            parse_mode="HTML",
        )

        # Export session
        exported_session = await session_exporter.export_session(
            claude_session_id, export_format
        )

        # Send the exported file
        from io import BytesIO

        file_bytes = BytesIO(exported_session.content.encode("utf-8"))
        file_bytes.name = exported_session.filename

        await query.message.reply_document(
            document=file_bytes,
            filename=exported_session.filename,
            caption=(
                f"📤 <b>Session Export Complete</b>\n\n"
                f"Format: {escape_html(exported_session.format.upper())}\n"
                f"Size: {exported_session.size_bytes:,} bytes\n"
                f"Created: {exported_session.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
            ),
            parse_mode="HTML",
        )

        # Update the original message
        await query.edit_message_text(
            f"✅ <b>Export Complete</b>\n\n"
            f"Your session has been exported as {escape_html(exported_session.filename)}.\n"
            f"Check the file above for your complete conversation history.",
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(
            "Export failed", error=str(e), user_id=user_id, format=export_format
        )
        await query.edit_message_text(
            f"❌ <b>Export Failed</b>\n\n{escape_html(str(e))}",
            parse_mode="HTML",
        )


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
