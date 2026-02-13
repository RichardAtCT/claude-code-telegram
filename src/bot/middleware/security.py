"""Security middleware for input validation and threat detection."""

from typing import Any, Callable, Dict

import structlog

from ..utils.html_format import escape_html

logger = structlog.get_logger()


async def security_middleware(
    handler: Callable, event: Any, data: Dict[str, Any]
) -> Any:
    """Validate inputs and detect security threats.

    This middleware:
    1. Validates message content for dangerous patterns
    2. Sanitizes file uploads
    3. Detects potential attacks
    4. Logs security violations
    """
    user_id = event.effective_user.id if event.effective_user else None
    username = (
        getattr(event.effective_user, "username", None)
        if event.effective_user
        else None
    )

    if not user_id:
        logger.warning("No user information in update")
        return await handler(event, data)

    # Get dependencies from context
    security_validator = data.get("security_validator")
    audit_logger = data.get("audit_logger")

    if not security_validator:
        logger.error("Security validator not available in middleware context")
        # Continue without validation (log error but don't block)
        return await handler(event, data)

    # Validate text content if present
    message = event.effective_message
    if message and message.text:
        is_safe, violation_type = await validate_message_content(
            message.text, security_validator, user_id, audit_logger
        )
        if not is_safe:
            await message.reply_text(
                f"🛡️ <b>Security Alert</b>\n\n"
                f"Your message contains potentially dangerous content and has been blocked.\n"
                f"Violation: {escape_html(violation_type)}\n\n"
                "If you believe this is an error, please contact the administrator.",
                parse_mode="HTML",
            )
            return  # Block processing

    # Validate file uploads if present
    if message and message.document:
        is_safe, error_message = await validate_file_upload(
            message.document, security_validator, user_id, audit_logger
        )
        if not is_safe:
            await message.reply_text(
                f"🛡️ <b>File Upload Blocked</b>\n\n"
                f"{escape_html(error_message)}\n\n"
                "Please ensure your file meets security requirements.",
                parse_mode="HTML",
            )
            return  # Block processing

    # Log successful security validation
    logger.debug(
        "Security validation passed",
        user_id=user_id,
        username=username,
        has_text=bool(message and message.text),
        has_document=bool(message and message.document),
    )

    # Continue to handler
    return await handler(event, data)


async def validate_message_content(
    text: str, security_validator: Any, user_id: int, audit_logger: Any
) -> tuple[bool, str]:
    """Validate message text content for security threats."""

    # Check for command injection patterns
    dangerous_patterns = [
        r";\s*rm\s+",
        r";\s*del\s+",
        r";\s*format\s+",
        r"`[^`]*`",
        r"\$\([^)]*\)",
        r"&&\s*rm\s+",
        r"\|\s*mail\s+",
        r">\s*/dev/",
        r"curl\s+.*\|\s*sh",
        r"wget\s+.*\|\s*sh",
        r"exec\s*\(",
        r"eval\s*\(",
    ]

    import re

    for pattern in dangerous_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            if audit_logger:
                await audit_logger.log_security_violation(
                    user_id=user_id,
                    violation_type="command_injection_attempt",
                    details=f"Dangerous pattern detected: {pattern}",
                    severity="high",
                    attempted_action="message_send",
                )

            logger.warning(
                "Command injection attempt detected",
                user_id=user_id,
                pattern=pattern,
                text_preview=text[:100],
            )
            return False, "Command injection attempt"

    # Check for path traversal attempts
    path_traversal_patterns = [
        r"\.\./.*",
        r"~\/.*",
        r"\/etc\/.*",
        r"\/var\/.*",
        r"\/usr\/.*",
        r"\/sys\/.*",
        r"\/proc\/.*",
    ]

    for pattern in path_traversal_patterns:
        if re.search(pattern, text):
            if audit_logger:
                await audit_logger.log_security_violation(
                    user_id=user_id,
                    violation_type="path_traversal_attempt",
                    details=f"Path traversal pattern detected: {pattern}",
                    severity="high",
                    attempted_action="message_send",
                )

            logger.warning(
                "Path traversal attempt detected",
                user_id=user_id,
                pattern=pattern,
                text_preview=text[:100],
            )
            return False, "Path traversal attempt"

    # Check for suspicious URLs or domains
    suspicious_patterns = [
        r"https?://[^/]*\.ru/",
        r"https?://[^/]*\.tk/",
        r"https?://[^/]*\.ml/",
        r"https?://bit\.ly/",
        r"https?://tinyurl\.com/",
        r"javascript:",
        r"data:text/html",
    ]

    for pattern in suspicious_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            if audit_logger:
                await audit_logger.log_security_violation(
                    user_id=user_id,
                    violation_type="suspicious_url",
                    details=f"Suspicious URL pattern detected: {pattern}",
                    severity="medium",
                    attempted_action="message_send",
                )

            logger.warning("Suspicious URL detected", user_id=user_id, pattern=pattern)
            return False, "Suspicious URL detected"

    # Sanitize content using security validator
    sanitized = security_validator.sanitize_command_input(text)
    if len(sanitized) < len(text) * 0.5:  # More than 50% removed
        if audit_logger:
            await audit_logger.log_security_violation(
                user_id=user_id,
                violation_type="excessive_sanitization",
                details="More than 50% of content was dangerous",
                severity="medium",
                attempted_action="message_send",
            )

        logger.warning(
            "Excessive content sanitization required",
            user_id=user_id,
            original_length=len(text),
            sanitized_length=len(sanitized),
        )
        return False, "Content contains too many dangerous characters"

    return True, ""


async def validate_file_upload(
    document: Any, security_validator: Any, user_id: int, audit_logger: Any
) -> tuple[bool, str]:
    """Validate file uploads for security."""

    filename = getattr(document, "file_name", "unknown")
    file_size = getattr(document, "file_size", 0)
    mime_type = getattr(document, "mime_type", "unknown")

    # Validate filename
    is_valid, error_message = security_validator.validate_filename(filename)
    if not is_valid:
        if audit_logger:
            await audit_logger.log_security_violation(
                user_id=user_id,
                violation_type="dangerous_filename",
                details=f"Filename validation failed: {error_message}",
                severity="medium",
                attempted_action="file_upload",
            )

        logger.warning(
            "Dangerous filename detected",
            user_id=user_id,
            filename=filename,
            error=error_message,
        )
        return False, error_message

    # Check file size limits
    max_file_size = 10 * 1024 * 1024  # 10MB
    if file_size > max_file_size:
        if audit_logger:
            await audit_logger.log_security_violation(
                user_id=user_id,
                violation_type="file_too_large",
                details=f"File size {file_size} exceeds limit {max_file_size}",
                severity="low",
                attempted_action="file_upload",
            )

        return False, f"File too large. Maximum size: {max_file_size // (1024*1024)}MB"

    # Check MIME type
    dangerous_mime_types = [
        "application/x-executable",
        "application/x-msdownload",
        "application/x-msdos-program",
        "application/x-dosexec",
        "application/x-winexe",
        "application/x-sh",
        "application/x-shellscript",
    ]

    if mime_type in dangerous_mime_types:
        if audit_logger:
            await audit_logger.log_security_violation(
                user_id=user_id,
                violation_type="dangerous_mime_type",
                details=f"Dangerous MIME type: {mime_type}",
                severity="high",
                attempted_action="file_upload",
            )

        logger.warning(
            "Dangerous MIME type detected",
            user_id=user_id,
            filename=filename,
            mime_type=mime_type,
        )
        return False, f"File type not allowed: {mime_type}"

    # Log successful file validation
    if audit_logger:
        await audit_logger.log_file_access(
            user_id=user_id,
            file_path=filename,
            action="upload_validated",
            success=True,
            file_size=file_size,
        )

    logger.info(
        "File upload validated",
        user_id=user_id,
        filename=filename,
        file_size=file_size,
        mime_type=mime_type,
    )

    return True, ""


async def threat_detection_middleware(
    handler: Callable, event: Any, data: Dict[str, Any]
) -> Any:
    """Advanced threat detection middleware.

    This middleware looks for patterns that might indicate
    sophisticated attacks or reconnaissance attempts.
    """
    user_id = event.effective_user.id if event.effective_user else None
    if not user_id:
        return await handler(event, data)

    audit_logger = data.get("audit_logger")

    # Track user behavior patterns
    user_behavior = data.setdefault("user_behavior", {})
    user_data = user_behavior.setdefault(
        user_id,
        {
            "message_count": 0,
            "failed_commands": 0,
            "path_requests": 0,
            "file_requests": 0,
            "first_seen": None,
        },
    )

    import time

    current_time = time.time()

    if user_data["first_seen"] is None:
        user_data["first_seen"] = current_time

    user_data["message_count"] += 1

    # Check for reconnaissance patterns
    message = event.effective_message
    text = message.text if message else ""

    # Suspicious commands that might indicate reconnaissance
    recon_patterns = [
        r"ls\s+/",
        r"find\s+/",
        r"locate\s+",
        r"which\s+",
        r"whereis\s+",
        r"ps\s+",
        r"netstat\s+",
        r"lsof\s+",
        r"env\s*$",
        r"printenv\s*$",
        r"whoami\s*$",
        r"id\s*$",
        r"uname\s+",
        r"cat\s+/etc/",
        r"cat\s+/proc/",
    ]

    import re

    recon_attempts = sum(
        1 for pattern in recon_patterns if re.search(pattern, text, re.IGNORECASE)
    )

    if recon_attempts > 0:
        user_data["recon_attempts"] = (
            user_data.get("recon_attempts", 0) + recon_attempts
        )

        # Alert if too many reconnaissance attempts
        if user_data["recon_attempts"] > 5:
            if audit_logger:
                await audit_logger.log_security_violation(
                    user_id=user_id,
                    violation_type="reconnaissance_attempt",
                    details=f"Multiple reconnaissance patterns detected: {user_data['recon_attempts']}",
                    severity="high",
                    attempted_action="reconnaissance",
                )

            logger.warning(
                "Reconnaissance attempt pattern detected",
                user_id=user_id,
                total_attempts=user_data["recon_attempts"],
                current_message=text[:100],
            )

            if event.effective_message:
                await event.effective_message.reply_text(
                    "🔍 <b>Suspicious Activity Detected</b>\n\n"
                    "Multiple reconnaissance-style commands detected. "
                    "This activity has been logged.\n\n"
                    "If you have legitimate needs, please contact the administrator.",
                    parse_mode="HTML",
                )

    return await handler(event, data)
