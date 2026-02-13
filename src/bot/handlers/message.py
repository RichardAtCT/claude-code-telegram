"""Message handlers for non-command inputs."""

import asyncio
from typing import Optional

import structlog
from telegram import Update
from telegram.ext import ContextTypes

from ...claude.exceptions import ClaudeToolValidationError
from ...config.settings import Settings
from ...security.audit import AuditLogger
from ...security.rate_limiter import RateLimiter
from ...security.validators import SecurityValidator
from ..utils.html_format import escape_html

logger = structlog.get_logger()


async def _format_progress_update(update_obj) -> Optional[str]:
    """Format progress updates with enhanced context and visual indicators."""
    if update_obj.type == "tool_result":
        # Show tool completion status
        tool_name = "Unknown"
        if update_obj.metadata and update_obj.metadata.get("tool_use_id"):
            # Try to extract tool name from context if available
            tool_name = update_obj.metadata.get("tool_name", "Tool")

        if update_obj.is_error():
            return f"❌ <b>{tool_name} failed</b>\n\n<i>{update_obj.get_error_message()}</i>"
        else:
            execution_time = ""
            if update_obj.metadata and update_obj.metadata.get("execution_time_ms"):
                time_ms = update_obj.metadata["execution_time_ms"]
                execution_time = f" ({time_ms}ms)"
            return f"✅ <b>{tool_name} completed</b>{execution_time}"

    elif update_obj.type == "progress":
        # Handle progress updates
        progress_text = f"🔄 <b>{update_obj.content or 'Working...'}</b>"

        percentage = update_obj.get_progress_percentage()
        if percentage is not None:
            # Create a simple progress bar
            filled = int(percentage / 10)  # 0-10 scale
            bar = "█" * filled + "░" * (10 - filled)
            progress_text += f"\n\n<code>{bar}</code> {percentage}%"

        if update_obj.progress:
            step = update_obj.progress.get("step")
            total_steps = update_obj.progress.get("total_steps")
            if step and total_steps:
                progress_text += f"\n\nStep {step} of {total_steps}"

        return progress_text

    elif update_obj.type == "error":
        # Handle error messages
        return f"❌ <b>Error</b>\n\n<i>{update_obj.get_error_message()}</i>"

    elif update_obj.type == "assistant" and update_obj.tool_calls:
        # Show when tools are being called
        tool_names = update_obj.get_tool_names()
        if tool_names:
            tools_text = ", ".join(tool_names)
            return f"🔧 <b>Using tools:</b> {tools_text}"

    elif update_obj.type == "assistant" and update_obj.content:
        # Regular content updates with preview
        content_preview = (
            update_obj.content[:150] + "..."
            if len(update_obj.content) > 150
            else update_obj.content
        )
        return f"🤖 <b>Claude is working...</b>\n\n<i>{content_preview}</i>"

    elif update_obj.type == "system":
        # System initialization or other system messages
        if update_obj.metadata and update_obj.metadata.get("subtype") == "init":
            tools_count = len(update_obj.metadata.get("tools", []))
            model = update_obj.metadata.get("model", "Claude")
            return f"🚀 <b>Starting {model}</b> with {tools_count} tools available"

    return None


def _format_error_message(error_str: str) -> str:
    """Format error messages for user-friendly display."""
    if "usage limit reached" in error_str.lower():
        # Usage limit error - already user-friendly from integration.py
        return error_str
    elif "tool not allowed" in error_str.lower():
        # Tool validation error - already handled in facade.py
        return error_str
    elif "no conversation found" in error_str.lower():
        return (
            f"🔄 <b>Session Not Found</b>\n\n"
            f"The Claude session could not be found or has expired.\n\n"
            f"<b>What you can do:</b>\n"
            f"• Use /new to start a fresh session\n"
            f"• Try your request again\n"
            f"• Use /status to check your current session"
        )
    elif "rate limit" in error_str.lower():
        return (
            f"⏱️ <b>Rate Limit Reached</b>\n\n"
            f"Too many requests in a short time period.\n\n"
            f"<b>What you can do:</b>\n"
            f"• Wait a moment before trying again\n"
            f"• Use simpler requests\n"
            f"• Check your current usage with /status"
        )
    elif "timeout" in error_str.lower():
        return (
            f"⏰ <b>Request Timeout</b>\n\n"
            f"Your request took too long to process and timed out.\n\n"
            f"<b>What you can do:</b>\n"
            f"• Try breaking down your request into smaller parts\n"
            f"• Use simpler commands\n"
            f"• Try again in a moment"
        )
    else:
        # Generic error handling
        # Escape HTML special characters in error message
        safe_error = escape_html(error_str)
        # Truncate very long errors
        if len(safe_error) > 200:
            safe_error = safe_error[:200] + "..."

        return (
            f"❌ <b>Claude Code Error</b>\n\n"
            f"Failed to process your request: {safe_error}\n\n"
            f"Please try again or contact the administrator if the problem persists."
        )


async def handle_text_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle regular text messages as Claude prompts."""
    user_id = update.effective_user.id
    message_text = update.message.text
    settings: Settings = context.bot_data["settings"]

    # Get services
    rate_limiter: Optional[RateLimiter] = context.bot_data.get("rate_limiter")
    audit_logger: Optional[AuditLogger] = context.bot_data.get("audit_logger")

    logger.info(
        "Processing text message", user_id=user_id, message_length=len(message_text)
    )

    try:
        # Check rate limit with estimated cost for text processing
        estimated_cost = _estimate_text_processing_cost(message_text)

        if rate_limiter:
            allowed, limit_message = await rate_limiter.check_rate_limit(
                user_id, estimated_cost
            )
            if not allowed:
                await update.message.reply_text(f"⏱️ {limit_message}")
                return

        # Send typing indicator
        await update.message.chat.send_action("typing")

        # Create progress message
        progress_msg = await update.message.reply_text(
            "🤔 Processing your request...",
            reply_to_message_id=update.message.message_id,
        )

        # Get Claude integration and storage from context
        claude_integration = context.bot_data.get("claude_integration")
        storage = context.bot_data.get("storage")

        if not claude_integration:
            await update.message.reply_text(
                "❌ <b>Claude integration not available</b>\n\n"
                "The Claude Code integration is not properly configured. "
                "Please contact the administrator.",
                parse_mode="HTML",
            )
            return

        # Get current directory
        current_dir = context.user_data.get(
            "current_directory", settings.approved_directory
        )

        # Get existing session ID
        session_id = context.user_data.get("claude_session_id")

        # Enhanced stream updates handler with progress tracking
        async def stream_handler(update_obj):
            try:
                progress_text = await _format_progress_update(update_obj)
                if progress_text:
                    await progress_msg.edit_text(progress_text, parse_mode="HTML")
            except Exception as e:
                logger.warning("Failed to update progress message", error=str(e))

        # Run Claude command
        try:
            claude_response = await claude_integration.run_command(
                prompt=message_text,
                working_directory=current_dir,
                user_id=user_id,
                session_id=session_id,
                on_stream=stream_handler,
            )

            # Update session ID
            context.user_data["claude_session_id"] = claude_response.session_id

            # Check if Claude changed the working directory and update our tracking
            _update_working_directory_from_claude_response(
                claude_response, context, settings, user_id
            )

            # Log interaction to storage
            if storage:
                try:
                    await storage.save_claude_interaction(
                        user_id=user_id,
                        session_id=claude_response.session_id,
                        prompt=message_text,
                        response=claude_response,
                        ip_address=None,  # Telegram doesn't provide IP
                    )
                except Exception as e:
                    logger.warning("Failed to log interaction to storage", error=str(e))

            # Format response
            from ..utils.formatting import ResponseFormatter

            formatter = ResponseFormatter(settings)
            formatted_messages = formatter.format_claude_response(
                claude_response.content
            )

        except ClaudeToolValidationError as e:
            # Tool validation error with detailed instructions
            logger.error(
                "Tool validation error",
                error=str(e),
                user_id=user_id,
                blocked_tools=e.blocked_tools,
            )
            # Error message already formatted, create FormattedMessage
            from ..utils.formatting import FormattedMessage

            formatted_messages = [FormattedMessage(str(e), parse_mode="HTML")]
        except Exception as e:
            logger.error("Claude integration failed", error=str(e), user_id=user_id)
            # Format error and create FormattedMessage
            from ..utils.formatting import FormattedMessage

            formatted_messages = [
                FormattedMessage(_format_error_message(str(e)), parse_mode="HTML")
            ]

        # Delete progress message
        await progress_msg.delete()

        # Send formatted responses (may be multiple messages)
        for i, message in enumerate(formatted_messages):
            try:
                await update.message.reply_text(
                    message.text,
                    parse_mode=message.parse_mode,
                    reply_markup=message.reply_markup,
                    reply_to_message_id=update.message.message_id if i == 0 else None,
                )

                # Small delay between messages to avoid rate limits
                if i < len(formatted_messages) - 1:
                    await asyncio.sleep(0.5)

            except Exception as e:
                logger.warning(
                    "Failed to send HTML response, retrying as plain text",
                    error=str(e),
                    message_index=i,
                )
                try:
                    await update.message.reply_text(
                        message.text,
                        reply_markup=message.reply_markup,
                        reply_to_message_id=(
                            update.message.message_id if i == 0 else None
                        ),
                    )
                except Exception:
                    await update.message.reply_text(
                        "❌ Failed to send response. Please try again.",
                        reply_to_message_id=(
                            update.message.message_id if i == 0 else None
                        ),
                    )

        # Update session info
        context.user_data["last_message"] = update.message.text

        # Add conversation enhancements if available
        features = context.bot_data.get("features")
        conversation_enhancer = (
            features.get_conversation_enhancer() if features else None
        )

        if conversation_enhancer and claude_response:
            try:
                # Update conversation context
                conversation_context = conversation_enhancer.update_context(
                    session_id=claude_response.session_id,
                    user_id=user_id,
                    working_directory=str(current_dir),
                    tools_used=claude_response.tools_used or [],
                    response_content=claude_response.content,
                )

                # Check if we should show follow-up suggestions
                if conversation_enhancer.should_show_suggestions(
                    claude_response.tools_used or [], claude_response.content
                ):
                    # Generate follow-up suggestions
                    suggestions = conversation_enhancer.generate_follow_up_suggestions(
                        claude_response.content,
                        claude_response.tools_used or [],
                        conversation_context,
                    )

                    if suggestions:
                        # Create keyboard with suggestions
                        suggestion_keyboard = (
                            conversation_enhancer.create_follow_up_keyboard(suggestions)
                        )

                        # Send follow-up suggestions
                        await update.message.reply_text(
                            "💡 <b>What would you like to do next?</b>",
                            parse_mode="HTML",
                            reply_markup=suggestion_keyboard,
                        )

            except Exception as e:
                logger.warning(
                    "Conversation enhancement failed", error=str(e), user_id=user_id
                )

        # Log successful message processing
        if audit_logger:
            await audit_logger.log_command(
                user_id=user_id,
                command="text_message",
                args=[update.message.text[:100]],  # First 100 chars
                success=True,
            )

        logger.info("Text message processed successfully", user_id=user_id)

    except Exception as e:
        # Clean up progress message if it exists
        try:
            await progress_msg.delete()
        except:
            pass

        error_msg = f"❌ <b>Error processing message</b>\n\n{escape_html(str(e))}"
        await update.message.reply_text(error_msg, parse_mode="HTML")

        # Log failed processing
        if audit_logger:
            await audit_logger.log_command(
                user_id=user_id,
                command="text_message",
                args=[update.message.text[:100]],
                success=False,
            )

        logger.error("Error processing text message", error=str(e), user_id=user_id)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle file uploads."""
    user_id = update.effective_user.id
    document = update.message.document
    settings: Settings = context.bot_data["settings"]

    # Get services
    security_validator: Optional[SecurityValidator] = context.bot_data.get(
        "security_validator"
    )
    audit_logger: Optional[AuditLogger] = context.bot_data.get("audit_logger")
    rate_limiter: Optional[RateLimiter] = context.bot_data.get("rate_limiter")

    logger.info(
        "Processing document upload",
        user_id=user_id,
        filename=document.file_name,
        file_size=document.file_size,
    )

    try:
        # Validate filename using security validator
        if security_validator:
            valid, error = security_validator.validate_filename(document.file_name)
            if not valid:
                await update.message.reply_text(
                    f"❌ <b>File Upload Rejected</b>\n\n{escape_html(error)}",
                    parse_mode="HTML",
                )

                # Log security violation
                if audit_logger:
                    await audit_logger.log_security_violation(
                        user_id=user_id,
                        violation_type="invalid_file_upload",
                        details=f"Filename: {document.file_name}, Error: {error}",
                        severity="medium",
                    )
                return

        # Check file size limits
        max_size = 10 * 1024 * 1024  # 10MB
        if document.file_size > max_size:
            await update.message.reply_text(
                f"❌ <b>File Too Large</b>\n\n"
                f"Maximum file size: {max_size // 1024 // 1024}MB\n"
                f"Your file: {document.file_size / 1024 / 1024:.1f}MB",
                parse_mode="HTML",
            )
            return

        # Check rate limit for file processing
        file_cost = _estimate_file_processing_cost(document.file_size)
        if rate_limiter:
            allowed, limit_message = await rate_limiter.check_rate_limit(
                user_id, file_cost
            )
            if not allowed:
                await update.message.reply_text(f"⏱️ {limit_message}")
                return

        # Send processing indicator
        await update.message.chat.send_action("upload_document")

        progress_msg = await update.message.reply_text(
            f"📄 Processing file: <code>{document.file_name}</code>...",
            parse_mode="HTML",
        )

        # Check if enhanced file handler is available
        features = context.bot_data.get("features")
        file_handler = features.get_file_handler() if features else None

        if file_handler:
            # Use enhanced file handler
            try:
                processed_file = await file_handler.handle_document_upload(
                    document,
                    user_id,
                    update.message.caption or "Please review this file:",
                )
                prompt = processed_file.prompt

                # Update progress message with file type info
                await progress_msg.edit_text(
                    f"📄 Processing {processed_file.type} file: <code>{document.file_name}</code>...",
                    parse_mode="HTML",
                )

            except Exception as e:
                logger.warning(
                    "Enhanced file handler failed, falling back to basic handler",
                    error=str(e),
                )
                file_handler = None  # Fall back to basic handling

        if not file_handler:
            # Fall back to basic file handling
            file = await document.get_file()
            file_bytes = await file.download_as_bytearray()

            # Try to decode as text
            try:
                content = file_bytes.decode("utf-8")

                # Check content length
                max_content_length = 50000  # 50KB of text
                if len(content) > max_content_length:
                    content = (
                        content[:max_content_length]
                        + "\n... (file truncated for processing)"
                    )

                # Create prompt with file content
                caption = update.message.caption or "Please review this file:"
                prompt = f"{caption}\n\n**File:** `{document.file_name}`\n\n```\n{content}\n```"

            except UnicodeDecodeError:
                await progress_msg.edit_text(
                    "❌ <b>File Format Not Supported</b>\n\n"
                    "File must be text-based and UTF-8 encoded.\n\n"
                    "<b>Supported formats:</b>\n"
                    "• Source code files (.py, .js, .ts, etc.)\n"
                    "• Text files (.txt, .md)\n"
                    "• Configuration files (.json, .yaml, .toml)\n"
                    "• Documentation files",
                    parse_mode="HTML",
                )
                return

        # Delete progress message
        await progress_msg.delete()

        # Create a new progress message for Claude processing
        claude_progress_msg = await update.message.reply_text(
            "🤖 Processing file with Claude...", parse_mode="HTML"
        )

        # Get Claude integration from context
        claude_integration = context.bot_data.get("claude_integration")

        if not claude_integration:
            await claude_progress_msg.edit_text(
                "❌ <b>Claude integration not available</b>\n\n"
                "The Claude Code integration is not properly configured.",
                parse_mode="HTML",
            )
            return

        # Get current directory and session
        current_dir = context.user_data.get(
            "current_directory", settings.approved_directory
        )
        session_id = context.user_data.get("claude_session_id")

        # Process with Claude
        try:
            claude_response = await claude_integration.run_command(
                prompt=prompt,
                working_directory=current_dir,
                user_id=user_id,
                session_id=session_id,
            )

            # Update session ID
            context.user_data["claude_session_id"] = claude_response.session_id

            # Check if Claude changed the working directory and update our tracking
            _update_working_directory_from_claude_response(
                claude_response, context, settings, user_id
            )

            # Format and send response
            from ..utils.formatting import ResponseFormatter

            formatter = ResponseFormatter(settings)
            formatted_messages = formatter.format_claude_response(
                claude_response.content
            )

            # Delete progress message
            await claude_progress_msg.delete()

            # Send responses
            for i, message in enumerate(formatted_messages):
                await update.message.reply_text(
                    message.text,
                    parse_mode=message.parse_mode,
                    reply_markup=message.reply_markup,
                    reply_to_message_id=(update.message.message_id if i == 0 else None),
                )

                if i < len(formatted_messages) - 1:
                    await asyncio.sleep(0.5)

        except Exception as e:
            await claude_progress_msg.edit_text(
                _format_error_message(str(e)), parse_mode="HTML"
            )
            logger.error("Claude file processing failed", error=str(e), user_id=user_id)

        # Log successful file processing
        if audit_logger:
            await audit_logger.log_file_access(
                user_id=user_id,
                file_path=document.file_name,
                action="upload_processed",
                success=True,
                file_size=document.file_size,
            )

    except Exception as e:
        try:
            await progress_msg.delete()
        except:
            pass

        error_msg = f"❌ <b>Error processing file</b>\n\n{escape_html(str(e))}"
        await update.message.reply_text(error_msg, parse_mode="HTML")

        # Log failed file processing
        if audit_logger:
            await audit_logger.log_file_access(
                user_id=user_id,
                file_path=document.file_name,
                action="upload_failed",
                success=False,
                file_size=document.file_size,
            )

        logger.error("Error processing document", error=str(e), user_id=user_id)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle photo uploads."""
    user_id = update.effective_user.id
    settings: Settings = context.bot_data["settings"]

    # Check if enhanced image handler is available
    features = context.bot_data.get("features")
    image_handler = features.get_image_handler() if features else None

    if image_handler:
        try:
            # Send processing indicator
            progress_msg = await update.message.reply_text(
                "📸 Processing image...", parse_mode="HTML"
            )

            # Get the largest photo size
            photo = update.message.photo[-1]

            # Process image with enhanced handler
            processed_image = await image_handler.process_image(
                photo, update.message.caption
            )

            # Delete progress message
            await progress_msg.delete()

            # Create Claude progress message
            claude_progress_msg = await update.message.reply_text(
                "🤖 Analyzing image with Claude...", parse_mode="HTML"
            )

            # Get Claude integration
            claude_integration = context.bot_data.get("claude_integration")

            if not claude_integration:
                await claude_progress_msg.edit_text(
                    "❌ <b>Claude integration not available</b>\n\n"
                    "The Claude Code integration is not properly configured.",
                    parse_mode="HTML",
                )
                return

            # Get current directory and session
            current_dir = context.user_data.get(
                "current_directory", settings.approved_directory
            )
            session_id = context.user_data.get("claude_session_id")

            # Process with Claude
            try:
                claude_response = await claude_integration.run_command(
                    prompt=processed_image.prompt,
                    working_directory=current_dir,
                    user_id=user_id,
                    session_id=session_id,
                )

                # Update session ID
                context.user_data["claude_session_id"] = claude_response.session_id

                # Format and send response
                from ..utils.formatting import ResponseFormatter

                formatter = ResponseFormatter(settings)
                formatted_messages = formatter.format_claude_response(
                    claude_response.content
                )

                # Delete progress message
                await claude_progress_msg.delete()

                # Send responses
                for i, message in enumerate(formatted_messages):
                    await update.message.reply_text(
                        message.text,
                        parse_mode=message.parse_mode,
                        reply_markup=message.reply_markup,
                        reply_to_message_id=(
                            update.message.message_id if i == 0 else None
                        ),
                    )

                    if i < len(formatted_messages) - 1:
                        await asyncio.sleep(0.5)

            except Exception as e:
                await claude_progress_msg.edit_text(
                    _format_error_message(str(e)), parse_mode="HTML"
                )
                logger.error(
                    "Claude image processing failed", error=str(e), user_id=user_id
                )

        except Exception as e:
            logger.error("Image processing failed", error=str(e), user_id=user_id)
            await update.message.reply_text(
                f"❌ <b>Error processing image</b>\n\n{escape_html(str(e))}",
                parse_mode="HTML",
            )
    else:
        # Fall back to unsupported message
        await update.message.reply_text(
            "📸 <b>Photo Upload</b>\n\n"
            "Photo processing is not yet supported.\n\n"
            "<b>Currently supported:</b>\n"
            "• Text files (.py, .js, .md, etc.)\n"
            "• Configuration files\n"
            "• Documentation files\n\n"
            "<b>Coming soon:</b>\n"
            "• Image analysis\n"
            "• Screenshot processing\n"
            "• Diagram interpretation",
            parse_mode="HTML",
        )


def _estimate_text_processing_cost(text: str) -> float:
    """Estimate cost for processing text message."""
    # Base cost
    base_cost = 0.001

    # Additional cost based on length
    length_cost = len(text) * 0.00001

    # Additional cost for complex requests
    complex_keywords = [
        "analyze",
        "generate",
        "create",
        "build",
        "implement",
        "refactor",
        "optimize",
        "debug",
        "explain",
        "document",
    ]

    text_lower = text.lower()
    complexity_multiplier = 1.0

    for keyword in complex_keywords:
        if keyword in text_lower:
            complexity_multiplier += 0.5

    return (base_cost + length_cost) * min(complexity_multiplier, 3.0)


def _estimate_file_processing_cost(file_size: int) -> float:
    """Estimate cost for processing uploaded file."""
    # Base cost for file handling
    base_cost = 0.005

    # Additional cost based on file size (per KB)
    size_cost = (file_size / 1024) * 0.0001

    return base_cost + size_cost


async def _generate_placeholder_response(
    message_text: str, context: ContextTypes.DEFAULT_TYPE
) -> dict:
    """Generate placeholder response until Claude integration is implemented."""
    settings: Settings = context.bot_data["settings"]
    current_dir = getattr(
        context.user_data, "current_directory", settings.approved_directory
    )
    relative_path = current_dir.relative_to(settings.approved_directory)

    # Analyze the message for intent
    message_lower = message_text.lower()

    if any(
        word in message_lower for word in ["list", "show", "see", "directory", "files"]
    ):
        response_text = (
            f"🤖 <b>Claude Code Response</b> <i>(Placeholder)</i>\n\n"
            f"I understand you want to see files. Try using the /ls command to list files "
            f"in your current directory (<code>{relative_path}/</code>).\n\n"
            f"<b>Available commands:</b>\n"
            f"• /ls - List files\n"
            f"• /cd &lt;dir&gt; - Change directory\n"
            f"• /projects - Show projects\n\n"
            f"<i>Note: Full Claude Code integration will be available in the next phase.</i>"
        )

    elif any(word in message_lower for word in ["create", "generate", "make", "build"]):
        response_text = (
            f"🤖 <b>Claude Code Response</b> <i>(Placeholder)</i>\n\n"
            f"I understand you want to create something! Once the Claude Code integration "
            f"is complete, I'll be able to:\n\n"
            f"• Generate code files\n"
            f"• Create project structures\n"
            f"• Write documentation\n"
            f"• Build complete applications\n\n"
            f"<b>Current directory:</b> <code>{relative_path}/</code>\n\n"
            f"<i>Full functionality coming soon!</i>"
        )

    elif any(word in message_lower for word in ["help", "how", "what", "explain"]):
        response_text = (
            f"🤖 <b>Claude Code Response</b> <i>(Placeholder)</i>\n\n"
            f"I'm here to help! Try using /help for available commands.\n\n"
            f"<b>What I can do now:</b>\n"
            f"• Navigate directories (/cd, /ls, /pwd)\n"
            f"• Show projects (/projects)\n"
            f"• Manage sessions (/new, /status)\n\n"
            f"<b>Coming soon:</b>\n"
            f"• Full Claude Code integration\n"
            f"• Code generation and editing\n"
            f"• File operations\n"
            f"• Advanced programming assistance"
        )

    else:
        response_text = (
            f"🤖 <b>Claude Code Response</b> <i>(Placeholder)</i>\n\n"
            f"I received your message: \"{message_text[:100]}{'...' if len(message_text) > 100 else ''}\"\n\n"
            f"<b>Current Status:</b>\n"
            f"• Directory: <code>{relative_path}/</code>\n"
            f"• Bot core: ✅ Active\n"
            f"• Claude integration: 🔄 Coming soon\n\n"
            f"Once Claude Code integration is complete, I'll be able to process your "
            f"requests fully and help with coding tasks!\n\n"
            f"For now, try the available commands like /ls, /cd, and /help."
        )

    return {"text": response_text, "parse_mode": "HTML"}


def _update_working_directory_from_claude_response(
    claude_response, context, settings, user_id
):
    """Update the working directory based on Claude's response content."""
    import re
    from pathlib import Path

    # Look for directory changes in Claude's response
    # This searches for common patterns that indicate directory changes
    patterns = [
        r"(?:^|\n).*?cd\s+([^\s\n]+)",  # cd command
        r"(?:^|\n).*?Changed directory to:?\s*([^\s\n]+)",  # explicit directory change
        r"(?:^|\n).*?Current directory:?\s*([^\s\n]+)",  # current directory indication
        r"(?:^|\n).*?Working directory:?\s*([^\s\n]+)",  # working directory indication
    ]

    content = claude_response.content.lower()
    current_dir = context.user_data.get(
        "current_directory", settings.approved_directory
    )

    for pattern in patterns:
        matches = re.findall(pattern, content, re.MULTILINE | re.IGNORECASE)
        for match in matches:
            try:
                # Clean up the path
                new_path = match.strip().strip("\"'`")

                # Handle relative paths
                if new_path.startswith("./") or new_path.startswith("../"):
                    new_path = (current_dir / new_path).resolve()
                elif not new_path.startswith("/"):
                    # Relative path without ./
                    new_path = (current_dir / new_path).resolve()
                else:
                    # Absolute path
                    new_path = Path(new_path).resolve()

                # Validate that the new path is within the approved directory
                if (
                    new_path.is_relative_to(settings.approved_directory)
                    and new_path.exists()
                ):
                    context.user_data["current_directory"] = new_path
                    logger.info(
                        "Updated working directory from Claude response",
                        old_dir=str(current_dir),
                        new_dir=str(new_path),
                        user_id=user_id,
                    )
                    return  # Take the first valid match

            except (ValueError, OSError) as e:
                # Invalid path, skip this match
                logger.debug(
                    "Invalid path in Claude response", path=match, error=str(e)
                )
                continue
