"""
Handle image uploads for UI/screenshot analysis

Features:
- OCR for text extraction
- UI element detection
- Image description
- Diagram analysis
"""

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from telegram import PhotoSize

from src.config import Settings


@dataclass
class ProcessedImage:
    """Processed image result"""

    prompt: str
    image_type: str
    base64_data: str
    size: int
    metadata: Dict[str, any] = None


class ImageHandler:
    """Process image uploads"""

    def __init__(self, config: Settings):
        self.config = config
        self.supported_formats = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

    async def process_image(
        self, photo: PhotoSize, caption: Optional[str] = None
    ) -> ProcessedImage:
        """Process uploaded image — save to temp file and build a path-based prompt."""
        import uuid

        # Download image bytes
        file = await photo.get_file()
        image_bytes = await file.download_as_bytearray()

        # Detect format and save to temp file so Claude CLI can read it
        fmt = self._detect_format(bytes(image_bytes))
        ext = fmt if fmt != "unknown" else "jpg"
        temp_dir = Path("/tmp/claude_bot_files")
        temp_dir.mkdir(exist_ok=True)
        image_path = temp_dir / f"image_{uuid.uuid4()}.{ext}"
        image_path.write_bytes(bytes(image_bytes))

        # Detect image type for prompt tailoring
        image_type = self._detect_image_type(bytes(image_bytes))

        # Build prompt with actual file path so Claude CLI can see the image
        if image_type == "screenshot":
            prompt = self._create_screenshot_prompt(caption, image_path)
        elif image_type == "diagram":
            prompt = self._create_diagram_prompt(caption, image_path)
        elif image_type == "ui_mockup":
            prompt = self._create_ui_prompt(caption, image_path)
        else:
            prompt = self._create_generic_prompt(caption, image_path)

        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        return ProcessedImage(
            prompt=prompt,
            image_type=image_type,
            base64_data=base64_image,
            size=len(image_bytes),
            metadata={
                "format": fmt,
                "has_caption": caption is not None,
                "temp_path": str(image_path),
            },
        )

    def _detect_image_type(self, image_bytes: bytes) -> str:
        """Detect type of image"""
        # Simple heuristic based on image characteristics
        # In practice, could use ML model for better detection

        # For now, return generic type
        return "screenshot"

    def _detect_format(self, image_bytes: bytes) -> str:
        """Detect image format from magic bytes"""
        # Check magic bytes for common formats
        if image_bytes.startswith(b"\x89PNG"):
            return "png"
        elif image_bytes.startswith(b"\xff\xd8\xff"):
            return "jpeg"
        elif image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a"):
            return "gif"
        elif image_bytes.startswith(b"RIFF") and b"WEBP" in image_bytes[:12]:
            return "webp"
        else:
            return "unknown"

    def _create_screenshot_prompt(
        self, caption: Optional[str], image_path: Path
    ) -> str:
        """Create prompt for screenshot analysis"""
        base = f"I'm sharing a screenshot with you. The image is saved at: {image_path}\n\nPlease analyze it and help me with:\n1. Identifying what application or website this is from\n2. Understanding the UI elements and their purpose\n3. Any issues or improvements you notice\n4. Answering any specific questions I have\n"
        if caption:
            base += f"\nSpecific request: {caption}"
        return base

    def _create_diagram_prompt(self, caption: Optional[str], image_path: Path) -> str:
        """Create prompt for diagram analysis"""
        base = f"I'm sharing a diagram with you. The image is saved at: {image_path}\n\nPlease help me:\n1. Understand the components and their relationships\n2. Identify the type of diagram\n3. Explain any technical concepts shown\n4. Suggest improvements or clarifications\n"
        if caption:
            base += f"\nSpecific request: {caption}"
        return base

    def _create_ui_prompt(self, caption: Optional[str], image_path: Path) -> str:
        """Create prompt for UI mockup analysis"""
        base = f"I'm sharing a UI mockup with you. The image is saved at: {image_path}\n\nPlease analyze:\n1. The layout and visual hierarchy\n2. UX improvements\n3. Accessibility concerns\n"
        if caption:
            base += f"\nSpecific request: {caption}"
        return base

    def _create_generic_prompt(self, caption: Optional[str], image_path: Path) -> str:
        """Create generic image analysis prompt"""
        base = f"I'm sharing an image with you. The image is saved at: {image_path}\n\nPlease analyze and describe what you see.\n"
        if caption:
            base += f"\nSpecific request: {caption}"
        return base

    def supports_format(self, filename: str) -> bool:
        """Check if image format is supported"""
        if not filename:
            return False

        # Extract extension
        parts = filename.lower().split(".")
        if len(parts) < 2:
            return False

        extension = f".{parts[-1]}"
        return extension in self.supported_formats

    async def validate_image(self, image_bytes: bytes) -> tuple[bool, Optional[str]]:
        """Validate image data"""
        # Check size
        max_size = 10 * 1024 * 1024  # 10MB
        if len(image_bytes) > max_size:
            return False, "Image too large (max 10MB)"

        # Check format
        format_type = self._detect_format(image_bytes)
        if format_type == "unknown":
            return False, "Unsupported image format"

        # Basic validity check
        if len(image_bytes) < 100:  # Too small to be a real image
            return False, "Invalid image data"

        return True, None
