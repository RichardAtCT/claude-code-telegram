"""Tests for image type detection and dimension parsing."""

import struct

import pytest

from src.bot.features.image_handler import ImageHandler
from src.config.settings import Settings


def _make_png(width: int, height: int) -> bytes:
    """Build a minimal PNG header with the given dimensions."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00"
    ihdr_len = struct.pack(">I", len(ihdr_data))
    return sig + ihdr_len + b"IHDR" + ihdr_data


def _make_gif(width: int, height: int) -> bytes:
    """Build a minimal GIF header with the given dimensions."""
    header = b"GIF89a"
    dims = struct.pack("<HH", width, height)
    return header + dims + b"\x00" * 10


def _make_jpeg_sof(width: int, height: int) -> bytes:
    """Build a minimal JPEG with an SOF0 marker containing dimensions."""
    data = b"\xff\xd8"
    sof_length = struct.pack(">H", 8)
    precision = b"\x08"
    h_bytes = struct.pack(">H", height)
    w_bytes = struct.pack(">H", width)
    data += b"\xff\xc0" + sof_length + precision + h_bytes + w_bytes
    return data


class TestImageDimensionParsing:
    """Test _get_dimensions for each supported format."""

    def test_png_dimensions(self):
        data = _make_png(1920, 1080)
        w, h = ImageHandler._get_dimensions(data, "png")
        assert (w, h) == (1920, 1080)

    def test_gif_dimensions(self):
        data = _make_gif(800, 600)
        w, h = ImageHandler._get_dimensions(data, "gif")
        assert (w, h) == (800, 600)

    def test_jpeg_dimensions(self):
        data = _make_jpeg_sof(1440, 900)
        w, h = ImageHandler._get_dimensions(data, "jpeg")
        assert (w, h) == (1440, 900)

    def test_unknown_format_returns_zero(self):
        w, h = ImageHandler._get_dimensions(b"\x00" * 50, "bmp")
        assert (w, h) == (0, 0)

    def test_truncated_png_returns_zero(self):
        w, h = ImageHandler._get_dimensions(b"\x89PNG\r\n\x1a\n" + b"\x00" * 5, "png")
        assert (w, h) == (0, 0)

    def test_empty_bytes_returns_zero(self):
        w, h = ImageHandler._get_dimensions(b"", "png")
        assert (w, h) == (0, 0)


class TestImageTypeDetection:
    """Test _detect_image_type heuristic classifications."""

    @pytest.fixture
    def handler(self, tmp_path):
        config = Settings(
            telegram_bot_token="fake:token",
            telegram_bot_username="test_bot",
            approved_directory=str(tmp_path),
        )
        return ImageHandler(config)

    def test_desktop_screenshot_detected(self, handler):
        """1920x1080 (16:9, width >= 800) should be screenshot."""
        data = _make_png(1920, 1080)
        assert handler._detect_image_type(data) == "screenshot"

    def test_wide_diagram_detected(self, handler):
        """Very wide image (aspect > 2.5) should be diagram."""
        data = _make_png(3000, 400)
        assert handler._detect_image_type(data) == "diagram"

    def test_tall_mobile_screenshot(self, handler):
        """Very tall image (aspect < 0.4) should be screenshot."""
        data = _make_png(400, 1200)
        assert handler._detect_image_type(data) == "screenshot"

    def test_phone_portrait_screenshot(self, handler):
        """Phone-portrait dimensions should be screenshot."""
        data = _make_png(750, 1334)
        assert handler._detect_image_type(data) == "screenshot"

    def test_square_moderate_is_ui_mockup(self, handler):
        """Square-ish moderate resolution should be ui_mockup."""
        data = _make_png(500, 500)
        assert handler._detect_image_type(data) == "ui_mockup"

    def test_small_image_is_generic(self, handler):
        """Small images (< 256x256) should be generic."""
        data = _make_png(100, 100)
        assert handler._detect_image_type(data) == "generic"

    def test_unrecognised_format_is_generic(self, handler):
        """Unknown format returns generic."""
        data = b"\x00" * 100
        assert handler._detect_image_type(data) == "generic"

    def test_gif_dimensions_parsed(self, handler):
        """GIF with desktop dimensions should be screenshot."""
        data = _make_gif(1920, 1080)
        assert handler._detect_image_type(data) == "screenshot"

    def test_jpeg_dimensions_parsed(self, handler):
        """JPEG with desktop dimensions should be screenshot."""
        data = _make_jpeg_sof(1440, 900)
        assert handler._detect_image_type(data) == "screenshot"
