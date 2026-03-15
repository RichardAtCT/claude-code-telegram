"""Tests for the Telegram MCP server tool functions."""

from pathlib import Path

import pytest

from src.mcp.telegram_server import send_file_to_user


@pytest.fixture
def image_file(tmp_path: Path) -> Path:
    """Create a sample image file."""
    img = tmp_path / "chart.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    return img


class TestSendFileToUser:
    async def test_valid_image(self, image_file: Path) -> None:
        result = await send_file_to_user(str(image_file))
        assert "File queued for delivery" in result
        assert "chart.png" in result

    async def test_valid_image_with_caption(self, image_file: Path) -> None:
        result = await send_file_to_user(str(image_file), caption="My chart")
        assert "File queued for delivery" in result

    async def test_relative_path_rejected(self, image_file: Path) -> None:
        result = await send_file_to_user("relative/path/chart.png")
        assert "Error" in result
        assert "absolute" in result

    async def test_missing_file_rejected(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.png"
        result = await send_file_to_user(str(missing))
        assert "Error" in result
        assert "not found" in result

    async def test_any_extension_accepted(self, tmp_path: Path) -> None:
        """send_file_to_user accepts any file type, not just images."""
        for ext in [".png", ".jpg", ".pdf", ".docx", ".mp3", ".zip", ".txt"]:
            f = tmp_path / f"test{ext}"
            f.write_bytes(b"\x00" * 10)
            result = await send_file_to_user(str(f))
            assert "File queued for delivery" in result, f"Failed for {ext}"

    async def test_case_insensitive_extension(self, tmp_path: Path) -> None:
        img = tmp_path / "photo.JPG"
        img.write_bytes(b"\x00" * 10)
        result = await send_file_to_user(str(img))
        assert "File queued for delivery" in result
