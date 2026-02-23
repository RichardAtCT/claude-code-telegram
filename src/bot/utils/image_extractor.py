"""Extract image file paths from Claude responses and prepare them for Telegram delivery."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

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
MAX_IMAGES_PER_RESPONSE = 10
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
PHOTO_SIZE_LIMIT = 10 * 1024 * 1024  # 10 MB — Telegram photo API limit

# Regex patterns to find image file paths in text.
# Order matters: more specific patterns first to avoid partial matches.
_IMAGE_EXT_PATTERN = r"\.(?:png|jpe?g|gif|webp|bmp|svg)"

_PATH_PATTERNS = [
    # Markdown image syntax: ![alt](path)
    re.compile(
        rf"!\[[^\]]*\]\(([^)]+{_IMAGE_EXT_PATTERN})\)",
        re.IGNORECASE,
    ),
    # Backtick-wrapped path: `path/to/image.png`
    re.compile(
        rf"`([^`\n]+{_IMAGE_EXT_PATTERN})`",
        re.IGNORECASE,
    ),
    # Double-quoted path: "path/to/image.png"
    re.compile(
        rf'"([^"\n]+{_IMAGE_EXT_PATTERN})"',
        re.IGNORECASE,
    ),
    # Single-quoted path: 'path/to/image.png'
    re.compile(
        rf"'([^'\n]+{_IMAGE_EXT_PATTERN})'",
        re.IGNORECASE,
    ),
    # Bare absolute path: /home/user/image.png (must start with /)
    re.compile(
        rf"(?:^|[\s])(/[^\s,;\"'`\])<>]+{_IMAGE_EXT_PATTERN})(?=[\s,;\"'`\])<>]|$)",
        re.IGNORECASE | re.MULTILINE,
    ),
    # Bare relative path: ./dir/image.png or dir/image.png (must contain /)
    re.compile(
        rf"(?:^|[\s])(\.?\.?/[^\s,;\"'`\])<>]+{_IMAGE_EXT_PATTERN})(?=[\s,;\"'`\])<>]|$)",
        re.IGNORECASE | re.MULTILINE,
    ),
]


@dataclass
class ImageAttachment:
    """An image file to attach to a Telegram response."""

    path: Path
    mime_type: str
    original_reference: str


def _validate_and_add(
    raw_path: str,
    working_directory: Path,
    approved_directory: Path,
    seen_paths: set[Path],
    results: List[ImageAttachment],
) -> bool:
    """Validate a single candidate path and append to results if valid.

    Returns True if the cap has been reached.
    """
    try:
        path = Path(raw_path)

        # Resolve relative paths against working directory
        if not path.is_absolute():
            path = working_directory / path

        # Resolve symlinks for security check
        resolved = path.resolve()

        # Security: must be within approved directory
        try:
            resolved.relative_to(approved_directory.resolve())
        except ValueError:
            logger.debug(
                "Image path outside approved directory",
                path=str(resolved),
                approved=str(approved_directory),
            )
            return False

        # Skip duplicates
        if resolved in seen_paths:
            return False

        # Check file exists
        if not resolved.is_file():
            return False

        # Check file size
        file_size = resolved.stat().st_size
        if file_size > MAX_FILE_SIZE_BYTES:
            logger.debug(
                "Image file too large",
                path=str(resolved),
                size=file_size,
            )
            return False

        # Determine MIME type
        ext = resolved.suffix.lower()
        mime_type = IMAGE_EXTENSIONS.get(ext)
        if not mime_type:
            return False

        seen_paths.add(resolved)
        results.append(
            ImageAttachment(
                path=resolved,
                mime_type=mime_type,
                original_reference=raw_path,
            )
        )

        return len(results) >= MAX_IMAGES_PER_RESPONSE

    except (OSError, ValueError) as e:
        logger.debug(
            "Failed to process image path",
            raw_path=raw_path,
            error=str(e),
        )
        return False


def _extract_image_paths_from_tools(
    tools_used: List[Dict[str, Any]],
) -> List[str]:
    """Extract candidate image file paths from Claude's tool calls.

    Looks at file_path in Read/Write/Edit inputs and command output in Bash.
    """
    candidates: List[str] = []
    image_ext_set = set(IMAGE_EXTENSIONS.keys())

    for tool in tools_used:
        name = tool.get("name", "")
        tool_input = tool.get("input", {})
        if not isinstance(tool_input, dict):
            continue

        # Read, Write, Edit — check file_path
        if name in ("Read", "Write", "Edit", "MultiEdit"):
            file_path = tool_input.get("file_path", "")
            if file_path and isinstance(file_path, str):
                ext = Path(file_path).suffix.lower()
                if ext in image_ext_set:
                    candidates.append(file_path)

        # Bash — scan command for output redirection to image files
        elif name == "Bash":
            cmd = tool_input.get("command", "")
            if isinstance(cmd, str):
                # Look for image paths in the command string
                for ext in image_ext_set:
                    if ext in cmd.lower():
                        # Extract paths from the command
                        for token in cmd.split():
                            token = token.strip("\"';(){}[]")
                            if Path(token).suffix.lower() in image_ext_set:
                                candidates.append(token)

    return candidates


def extract_images_from_response(
    text: str,
    working_directory: Path,
    approved_directory: Path,
    tools_used: Optional[List[Dict[str, Any]]] = None,
) -> List[ImageAttachment]:
    """Scan response text and tool calls for image file paths.

    Only returns images that:
    - Have a recognised image extension
    - Exist on disk
    - Resolve to within ``approved_directory`` (follows symlinks)
    - Are ≤ 50 MB
    """
    seen_paths: set[Path] = set()
    results: List[ImageAttachment] = []

    # 1) Scan response text for image paths
    if text:
        for pattern in _PATH_PATTERNS:
            for match in pattern.finditer(text):
                raw_path = match.group(1).strip()
                if not raw_path:
                    continue
                if _validate_and_add(
                    raw_path,
                    working_directory,
                    approved_directory,
                    seen_paths,
                    results,
                ):
                    return results

    # 2) Scan tool calls for image file paths (Read, Write, Bash, etc.)
    if tools_used:
        for raw_path in _extract_image_paths_from_tools(tools_used):
            if _validate_and_add(
                raw_path,
                working_directory,
                approved_directory,
                seen_paths,
                results,
            ):
                return results

    return results


def should_send_as_photo(path: Path) -> bool:
    """Return True if the image should be sent via reply_photo().

    Raster images ≤ 10 MB are sent as photos (inline preview).
    SVGs and large files are sent as documents.
    """
    ext = path.suffix.lower()
    if ext not in TELEGRAM_PHOTO_EXTENSIONS:
        return False

    try:
        return path.stat().st_size <= PHOTO_SIZE_LIMIT
    except OSError:
        return False
