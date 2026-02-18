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
        """Detect type of image using format and dimension heuristics."""
        fmt = self._detect_format(image_bytes)
        width, height = self._get_dimensions(image_bytes, fmt)

        if width == 0 or height == 0:
            return "generic"

        aspect = width / height

        # Very wide images are likely diagrams or flowcharts
        if aspect > 2.5:
            return "diagram"

        # Very tall images are likely mobile screenshots or scrolling captures
        if aspect < 0.4:
            return "screenshot"

        # Common desktop/mobile screenshot aspect ratios (16:9, 16:10, 9:16, etc.)
        if 1.2 < aspect < 2.0 and width >= 800:
            return "screenshot"

        # Phone-portrait screenshots
        if 0.4 <= aspect <= 0.65 and height >= 1000:
            return "screenshot"

        # Square-ish images with moderate resolution are often UI mockups
        if 0.8 <= aspect <= 1.25 and width >= 400:
            return "ui_mockup"

        # Small images are likely icons or thumbnails
        if width < 256 and height < 256:
            return "generic"

        return "generic"

    @staticmethod
    def _get_dimensions(image_bytes: bytes, fmt: str) -> tuple:
        """Extract width and height from image bytes without PIL."""
        try:
            if fmt == "png" and len(image_bytes) >= 24:
                # PNG: width at offset 16 (4 bytes BE), height at offset 20 (4 bytes BE)
                w = int.from_bytes(image_bytes[16:20], "big")
                h = int.from_bytes(image_bytes[20:24], "big")
                return w, h
            elif fmt == "jpeg" and len(image_bytes) > 2:
                # JPEG: scan for SOF0/SOF2 markers (0xFF 0xC0 / 0xFF 0xC2)
                i = 2
                while i < len(image_bytes) - 9:
                    if image_bytes[i] != 0xFF:
                        i += 1
                        continue
                    marker = image_bytes[i + 1]
                    if marker in (0xC0, 0xC2):
                        h = int.from_bytes(image_bytes[i + 5 : i + 7], "big")
                        w = int.from_bytes(image_bytes[i + 7 : i + 9], "big")
                        return w, h
                    # Skip to next marker
                    length = int.from_bytes(image_bytes[i + 2 : i + 4], "big")
                    i += 2 + length
            elif fmt == "gif" and len(image_bytes) >= 10:
                # GIF: width at offset 6 (2 bytes LE), height at offset 8 (2 bytes LE)
                w = int.from_bytes(image_bytes[6:8], "little")
                h = int.from_bytes(image_bytes[8:10], "little")
                return w, h
            elif fmt == "webp" and len(image_bytes) >= 30:
                # WebP VP8: dimensions at offset 26-30
                if image_bytes[12:16] == b"VP8 " and len(image_bytes) >= 30:
                    w = int.from_bytes(image_bytes[26:28], "little") & 0x3FFF
                    h = int.from_bytes(image_bytes[28:30], "little") & 0x3FFF
                    return w, h
        except Exception:
            pass
        return 0, 0

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
