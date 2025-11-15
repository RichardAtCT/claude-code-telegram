"""Tests for image handler feature."""

import base64
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.bot.features.image_handler import ImageHandler, ProcessedImage
from src.config import Settings


@pytest.fixture
def temp_dir():
    """Create temporary directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def config(temp_dir):
    """Create test configuration."""
    return Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(temp_dir),
        allowed_users=[123456789],
    )


@pytest.fixture
def image_handler(config):
    """Create image handler instance."""
    return ImageHandler(config)


# Sample image data (minimal valid images)
PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
JPEG_HEADER = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 100
GIF_HEADER = b"GIF89a" + b"\x00" * 100
WEBP_HEADER = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 100


class TestImageHandlerInitialization:
    """Test ImageHandler initialization."""

    def test_initialization(self, image_handler, config):
        """Test handler is properly initialized."""
        assert image_handler.config == config
        assert len(image_handler.supported_formats) == 5
        assert ".png" in image_handler.supported_formats
        assert ".jpg" in image_handler.supported_formats
        assert ".jpeg" in image_handler.supported_formats
        assert ".gif" in image_handler.supported_formats
        assert ".webp" in image_handler.supported_formats


class TestFormatDetection:
    """Test image format detection."""

    def test_detect_png_format(self, image_handler):
        """Test PNG format detection."""
        format_type = image_handler._detect_format(PNG_HEADER)
        assert format_type == "png"

    def test_detect_jpeg_format(self, image_handler):
        """Test JPEG format detection."""
        format_type = image_handler._detect_format(JPEG_HEADER)
        assert format_type == "jpeg"

    def test_detect_gif_format(self, image_handler):
        """Test GIF format detection."""
        format_type = image_handler._detect_format(GIF_HEADER)
        assert format_type == "gif"

    def test_detect_gif87a_format(self, image_handler):
        """Test GIF87a format detection."""
        gif87_header = b"GIF87a" + b"\x00" * 100
        format_type = image_handler._detect_format(gif87_header)
        assert format_type == "gif"

    def test_detect_webp_format(self, image_handler):
        """Test WEBP format detection."""
        format_type = image_handler._detect_format(WEBP_HEADER)
        assert format_type == "webp"

    def test_detect_unknown_format(self, image_handler):
        """Test unknown format detection."""
        unknown_data = b"\x00\x00\x00\x00" * 25
        format_type = image_handler._detect_format(unknown_data)
        assert format_type == "unknown"

    def test_detect_format_with_short_data(self, image_handler):
        """Test format detection with insufficient data."""
        short_data = b"\x89PNG"
        format_type = image_handler._detect_format(short_data)
        assert format_type == "png"


class TestImageTypeDetection:
    """Test image type classification."""

    def test_detect_image_type_returns_screenshot(self, image_handler):
        """Test image type detection returns screenshot by default."""
        # Currently returns 'screenshot' for all images
        image_type = image_handler._detect_image_type(PNG_HEADER)
        assert image_type == "screenshot"

    def test_detect_image_type_with_jpeg(self, image_handler):
        """Test image type detection with JPEG."""
        image_type = image_handler._detect_image_type(JPEG_HEADER)
        assert image_type == "screenshot"

    def test_detect_image_type_with_empty_data(self, image_handler):
        """Test image type detection with empty data."""
        image_type = image_handler._detect_image_type(b"")
        assert image_type == "screenshot"


class TestPromptGeneration:
    """Test prompt generation for different image types."""

    def test_screenshot_prompt_without_caption(self, image_handler):
        """Test screenshot prompt generation without caption."""
        prompt = image_handler._create_screenshot_prompt(None)
        assert "screenshot" in prompt.lower()
        assert "analyze" in prompt.lower()
        assert "UI elements" in prompt
        assert "Specific request:" not in prompt

    def test_screenshot_prompt_with_caption(self, image_handler):
        """Test screenshot prompt generation with caption."""
        caption = "What's wrong with this button?"
        prompt = image_handler._create_screenshot_prompt(caption)
        assert "screenshot" in prompt.lower()
        assert f"Specific request: {caption}" in prompt

    def test_diagram_prompt_without_caption(self, image_handler):
        """Test diagram prompt generation without caption."""
        prompt = image_handler._create_diagram_prompt(None)
        assert "diagram" in prompt.lower()
        assert "components" in prompt.lower()
        assert "relationships" in prompt.lower()
        assert "Specific request:" not in prompt

    def test_diagram_prompt_with_caption(self, image_handler):
        """Test diagram prompt generation with caption."""
        caption = "Explain the data flow"
        prompt = image_handler._create_diagram_prompt(caption)
        assert "diagram" in prompt.lower()
        assert f"Specific request: {caption}" in prompt

    def test_ui_prompt_without_caption(self, image_handler):
        """Test UI mockup prompt generation without caption."""
        prompt = image_handler._create_ui_prompt(None)
        assert "UI mockup" in prompt
        assert "layout" in prompt.lower()
        assert "accessibility" in prompt.lower()
        assert "Specific request:" not in prompt

    def test_ui_prompt_with_caption(self, image_handler):
        """Test UI mockup prompt generation with caption."""
        caption = "How can I improve this?"
        prompt = image_handler._create_ui_prompt(caption)
        assert "UI mockup" in prompt
        assert f"Specific request: {caption}" in prompt

    def test_generic_prompt_without_caption(self, image_handler):
        """Test generic prompt generation without caption."""
        prompt = image_handler._create_generic_prompt(None)
        assert "analyze" in prompt.lower()
        assert "insights" in prompt.lower()
        assert "Context:" not in prompt

    def test_generic_prompt_with_caption(self, image_handler):
        """Test generic prompt generation with caption."""
        caption = "What is this?"
        prompt = image_handler._create_generic_prompt(caption)
        assert f"Context: {caption}" in prompt


class TestFormatSupport:
    """Test format support checking."""

    def test_supports_png(self, image_handler):
        """Test PNG format is supported."""
        assert image_handler.supports_format("image.png") is True

    def test_supports_jpg(self, image_handler):
        """Test JPG format is supported."""
        assert image_handler.supports_format("image.jpg") is True

    def test_supports_jpeg(self, image_handler):
        """Test JPEG format is supported."""
        assert image_handler.supports_format("image.jpeg") is True

    def test_supports_gif(self, image_handler):
        """Test GIF format is supported."""
        assert image_handler.supports_format("image.gif") is True

    def test_supports_webp(self, image_handler):
        """Test WEBP format is supported."""
        assert image_handler.supports_format("image.webp") is True

    def test_case_insensitive_format_check(self, image_handler):
        """Test format checking is case insensitive."""
        assert image_handler.supports_format("IMAGE.PNG") is True
        assert image_handler.supports_format("Image.JPG") is True
        assert image_handler.supports_format("photo.JPEG") is True

    def test_unsupported_format(self, image_handler):
        """Test unsupported format returns False."""
        assert image_handler.supports_format("document.pdf") is False
        assert image_handler.supports_format("video.mp4") is False

    def test_empty_filename(self, image_handler):
        """Test empty filename returns False."""
        assert image_handler.supports_format("") is False
        assert image_handler.supports_format(None) is False

    def test_filename_without_extension(self, image_handler):
        """Test filename without extension returns False."""
        assert image_handler.supports_format("image") is False


class TestImageValidation:
    """Test image validation."""

    @pytest.mark.asyncio
    async def test_validate_valid_png(self, image_handler):
        """Test validation of valid PNG image."""
        valid, error = await image_handler.validate_image(PNG_HEADER)
        assert valid is True
        assert error is None

    @pytest.mark.asyncio
    async def test_validate_valid_jpeg(self, image_handler):
        """Test validation of valid JPEG image."""
        valid, error = await image_handler.validate_image(JPEG_HEADER)
        assert valid is True
        assert error is None

    @pytest.mark.asyncio
    async def test_validate_image_too_large(self, image_handler):
        """Test validation rejects images over 10MB."""
        large_image = PNG_HEADER + b"\x00" * (11 * 1024 * 1024)
        valid, error = await image_handler.validate_image(large_image)
        assert valid is False
        assert "too large" in error.lower()

    @pytest.mark.asyncio
    async def test_validate_image_at_size_limit(self, image_handler):
        """Test validation accepts image at exactly 10MB."""
        max_size_image = PNG_HEADER + b"\x00" * (10 * 1024 * 1024 - len(PNG_HEADER))
        valid, error = await image_handler.validate_image(max_size_image)
        assert valid is True
        assert error is None

    @pytest.mark.asyncio
    async def test_validate_unknown_format(self, image_handler):
        """Test validation rejects unknown format."""
        unknown_data = b"\x00\x00\x00\x00" * 50
        valid, error = await image_handler.validate_image(unknown_data)
        assert valid is False
        assert "unsupported" in error.lower()

    @pytest.mark.asyncio
    async def test_validate_too_small(self, image_handler):
        """Test validation rejects data too small to be an image."""
        tiny_data = b"\x89PNG\r\n"
        valid, error = await image_handler.validate_image(tiny_data)
        assert valid is False
        assert "invalid" in error.lower()

    @pytest.mark.asyncio
    async def test_validate_empty_data(self, image_handler):
        """Test validation rejects empty data."""
        valid, error = await image_handler.validate_image(b"")
        assert valid is False
        # Empty data fails format detection first, so error is about unsupported format
        assert "unsupported" in error.lower() or "invalid" in error.lower()


class TestImageProcessing:
    """Test image processing workflow."""

    @pytest.mark.asyncio
    async def test_process_image_screenshot(self, image_handler):
        """Test processing an image as screenshot."""
        # Mock PhotoSize
        photo = AsyncMock()
        mock_file = AsyncMock()
        mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(PNG_HEADER))
        photo.get_file = AsyncMock(return_value=mock_file)

        result = await image_handler.process_image(photo)

        assert isinstance(result, ProcessedImage)
        assert result.image_type == "screenshot"
        assert "screenshot" in result.prompt.lower()
        assert result.size == len(PNG_HEADER)
        assert result.metadata["format"] == "png"
        assert result.metadata["has_caption"] is False

    @pytest.mark.asyncio
    async def test_process_image_with_caption(self, image_handler):
        """Test processing image with caption."""
        photo = AsyncMock()
        mock_file = AsyncMock()
        mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(JPEG_HEADER))
        photo.get_file = AsyncMock(return_value=mock_file)

        caption = "What is this error?"
        result = await image_handler.process_image(photo, caption)

        assert isinstance(result, ProcessedImage)
        assert caption in result.prompt
        assert result.metadata["has_caption"] is True

    @pytest.mark.asyncio
    async def test_process_image_base64_encoding(self, image_handler):
        """Test that image is properly base64 encoded."""
        photo = AsyncMock()
        mock_file = AsyncMock()
        mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(PNG_HEADER))
        photo.get_file = AsyncMock(return_value=mock_file)

        result = await image_handler.process_image(photo)

        # Verify base64 encoding
        decoded = base64.b64decode(result.base64_data)
        assert decoded == PNG_HEADER

    @pytest.mark.asyncio
    async def test_process_image_different_formats(self, image_handler):
        """Test processing images of different formats."""
        formats_to_test = [
            (PNG_HEADER, "png"),
            (JPEG_HEADER, "jpeg"),
            (GIF_HEADER, "gif"),
            (WEBP_HEADER, "webp"),
        ]

        for image_data, expected_format in formats_to_test:
            photo = AsyncMock()
            mock_file = AsyncMock()
            mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(image_data))
            photo.get_file = AsyncMock(return_value=mock_file)

            result = await image_handler.process_image(photo)

            assert result.metadata["format"] == expected_format

    @pytest.mark.asyncio
    async def test_process_image_size_metadata(self, image_handler):
        """Test that size metadata is correct."""
        # Create image of known size
        image_data = PNG_HEADER + b"\x00" * 500
        photo = AsyncMock()
        mock_file = AsyncMock()
        mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(image_data))
        photo.get_file = AsyncMock(return_value=mock_file)

        result = await image_handler.process_image(photo)

        assert result.size == len(image_data)


class TestProcessedImageDataclass:
    """Test ProcessedImage dataclass."""

    def test_processed_image_creation(self):
        """Test creating ProcessedImage instance."""
        result = ProcessedImage(
            prompt="Test prompt",
            image_type="screenshot",
            base64_data="base64encodeddata",
            size=1024,
            metadata={"format": "png"},
        )

        assert result.prompt == "Test prompt"
        assert result.image_type == "screenshot"
        assert result.base64_data == "base64encodeddata"
        assert result.size == 1024
        assert result.metadata["format"] == "png"

    def test_processed_image_without_metadata(self):
        """Test ProcessedImage with default metadata."""
        result = ProcessedImage(
            prompt="Test prompt",
            image_type="screenshot",
            base64_data="data",
            size=100,
        )

        assert result.metadata is None
