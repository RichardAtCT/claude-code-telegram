"""Validate file paths and prepare them for Telegram delivery.

Used by the MCP ``send_file_to_user`` tool intercept — the stream callback
validates each path via :func:`validate_file_path` and collects
:class:`FileAttachment` objects for later Telegram delivery.

Backwards-compatible aliases (:class:`ImageAttachment`,
:func:`validate_image_path`) are kept so existing code continues to work.
"""

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger()

# Supported image extensions -> MIME types
IMAGE_EXTENSIONS = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
}

# Raster formats that can be sent via reply_photo() (Telegram supports these natively)
TELEGRAM_PHOTO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

# Safety caps
MAX_FILES_PER_RESPONSE = 10
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
PHOTO_SIZE_LIMIT = 10 * 1024 * 1024  # 10 MB — Telegram photo API limit

# Backwards-compat alias
MAX_IMAGES_PER_RESPONSE = MAX_FILES_PER_RESPONSE


@dataclass
class FileAttachment:
    """A file to attach to a Telegram response."""

    path: Path
    mime_type: str
    original_reference: str


# Backwards-compat alias
ImageAttachment = FileAttachment


def validate_file_path(
    file_path: str,
    approved_directory: Path,
    caption: str = "",
) -> Optional[FileAttachment]:
    """Validate a file path from an MCP ``send_file_to_user`` call.

    Returns a :class:`FileAttachment` if the path is a valid, existing file
    inside *approved_directory*, or ``None`` otherwise.
    Accepts **any** file type (images, PDFs, audio, etc.).
    """
    try:
        path = Path(file_path)
        if not path.is_absolute():
            return None

        resolved = path.resolve()

        # Security: must be within approved directory
        try:
            resolved.relative_to(approved_directory.resolve())
        except ValueError:
            logger.debug(
                "MCP file path outside approved directory",
                path=str(resolved),
                approved=str(approved_directory),
            )
            return None

        if not resolved.is_file():
            return None

        file_size = resolved.stat().st_size
        if file_size > MAX_FILE_SIZE_BYTES:
            logger.debug("MCP file too large", path=str(resolved), size=file_size)
            return None

        ext = resolved.suffix.lower()
        mime_type = IMAGE_EXTENSIONS.get(ext) or mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"

        return FileAttachment(
            path=resolved,
            mime_type=mime_type,
            original_reference=caption or file_path,
        )
    except (OSError, ValueError) as e:
        logger.debug("MCP file path validation failed", path=file_path, error=str(e))
        return None


# Backwards-compat alias
validate_image_path = validate_file_path


def should_send_as_photo(path: Path) -> bool:
    """Return True if the image should be sent via reply_photo().

    Raster images <= 10 MB are sent as photos (inline preview).
    SVGs and large files are sent as documents.
    """
    ext = path.suffix.lower()
    if ext not in TELEGRAM_PHOTO_EXTENSIONS:
        return False

    try:
        return path.stat().st_size <= PHOTO_SIZE_LIMIT
    except OSError:
        return False
