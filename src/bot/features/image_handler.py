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
from typing import Any, Dict, Optional

from telegram import PhotoSize

from src.config import Settings


@dataclass
class ProcessedImage:
    """Processed image result"""

    prompt: str
    image_type: str
    base64_data: str
    size: int
    metadata: Optional[Dict[str, Any]] = None


class ImageHandler:
    """Process image uploads"""

    def __init__(self, config: Settings):
        self.config = config
        self.supported_formats = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

    async def process_image(
        self, photo: PhotoSize, caption: Optional[str] = None
    ) -> ProcessedImage:
        """Process uploaded image"""

        # Download image
        file = await photo.get_file()
        image_bytes = await file.download_as_bytearray()

        # Detect image type
        image_type = self._detect_image_type(image_bytes)

        # Create appropriate prompt
        if image_type == "screenshot":
            prompt = self._create_screenshot_prompt(caption)
        elif image_type == "diagram":
            prompt = self._create_diagram_prompt(caption)
        elif image_type == "ui_mockup":
            prompt = self._create_ui_prompt(caption)
        else:
            prompt = self._create_generic_prompt(caption)

        # Convert to base64 for Claude (if supported in future)
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        return ProcessedImage(
            prompt=prompt,
            image_type=image_type,
            base64_data=base64_image,
            size=len(image_bytes),
            metadata={
                "format": self._detect_format(image_bytes),
                "has_caption": caption is not None,
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

    def _create_screenshot_prompt(self, caption: Optional[str]) -> str:
        """Create prompt for screenshot analysis"""
        base_prompt = """I'm sharing a screenshot with you. Please analyze it and help me with:

1. Identifying what application or website this is from
2. Understanding the UI elements and their purpose
3. Any issues or improvements you notice
4. Answering any specific questions I have

"""
        if caption:
            base_prompt += f"Specific request: {caption}"

        return base_prompt

    def _create_diagram_prompt(self, caption: Optional[str]) -> str:
        """Create prompt for diagram analysis"""
        base_prompt = """I'm sharing a diagram with you. Please help me:

1. Understand the components and their relationships
2. Identify the type of diagram (flowchart, architecture, etc.)
3. Explain any technical concepts shown
4. Suggest improvements or clarifications

"""
        if caption:
            base_prompt += f"Specific request: {caption}"

        return base_prompt

    def _create_ui_prompt(self, caption: Optional[str]) -> str:
        """Create prompt for UI mockup analysis"""
        base_prompt = """I'm sharing a UI mockup with you. Please analyze:

1. The layout and visual hierarchy
2. User experience considerations
3. Accessibility aspects
4. Implementation suggestions
5. Any potential improvements

"""
        if caption:
            base_prompt += f"Specific request: {caption}"

        return base_prompt

    def _create_generic_prompt(self, caption: Optional[str]) -> str:
        """Create generic image analysis prompt"""
        base_prompt = """I'm sharing an image with you. Please analyze it and provide relevant insights.

"""
        if caption:
            base_prompt += f"Context: {caption}"

        return base_prompt

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
