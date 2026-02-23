"""Tests for image validation and Telegram delivery helpers."""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.bot.utils.image_extractor import (
    IMAGE_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
    PHOTO_SIZE_LIMIT,
    TELEGRAM_PHOTO_EXTENSIONS,
    ImageAttachment,
    should_send_as_photo,
    validate_image_path,
)


@pytest.fixture
def work_dir(tmp_path: Path) -> Path:
    """Create a working directory with some image files."""
    img_dir = tmp_path / "project"
    img_dir.mkdir()
    for name in [
        "chart.png",
        "photo.jpg",
        "diagram.svg",
        "anim.gif",
        "pic.webp",
        "old.bmp",
        "shot.jpeg",
    ]:
        (img_dir / name).write_bytes(b"\x00" * 100)
    return img_dir


@pytest.fixture
def approved_dir(tmp_path: Path) -> Path:
    """The approved directory is tmp_path itself."""
    return tmp_path


# --- should_send_as_photo ---


class TestShouldSendAsPhoto:
    def test_raster_small_as_photo(self, tmp_path: Path):
        img = tmp_path / "small.png"
        img.write_bytes(b"\x00" * 100)
        assert should_send_as_photo(img) is True

    def test_svg_as_document(self, tmp_path: Path):
        img = tmp_path / "diagram.svg"
        img.write_bytes(b"<svg></svg>")
        assert should_send_as_photo(img) is False

    def test_large_raster_as_document(self, tmp_path: Path):
        img = tmp_path / "big.png"
        img.write_bytes(b"\x00" * 100)
        with patch.object(Path, "stat") as mock_stat:
            mock_stat.return_value.st_size = PHOTO_SIZE_LIMIT + 1
            assert should_send_as_photo(img) is False

    def test_nonexistent_file(self, tmp_path: Path):
        img = tmp_path / "gone.png"
        assert should_send_as_photo(img) is False


# --- Constants ---


class TestConstants:
    def test_telegram_photo_extensions_subset(self):
        """TELEGRAM_PHOTO_EXTENSIONS should be a subset of IMAGE_EXTENSIONS keys."""
        for ext in TELEGRAM_PHOTO_EXTENSIONS:
            assert ext in IMAGE_EXTENSIONS

    def test_svg_not_in_photo_extensions(self):
        assert ".svg" not in TELEGRAM_PHOTO_EXTENSIONS


# --- validate_image_path (MCP tool validation) ---


class TestValidateImagePath:
    def test_valid_absolute_image(self, work_dir: Path, approved_dir: Path):
        img = work_dir / "chart.png"
        result = validate_image_path(str(img), approved_dir)
        assert result is not None
        assert result.path == img.resolve()
        assert result.mime_type == "image/png"

    def test_relative_path_rejected(self, approved_dir: Path):
        result = validate_image_path("relative/chart.png", approved_dir)
        assert result is None

    def test_nonexistent_file_rejected(self, work_dir: Path, approved_dir: Path):
        result = validate_image_path(str(work_dir / "missing.png"), approved_dir)
        assert result is None

    def test_non_image_extension_rejected(self, work_dir: Path, approved_dir: Path):
        txt = work_dir / "notes.txt"
        txt.write_text("hello")
        result = validate_image_path(str(txt), approved_dir)
        assert result is None

    def test_outside_approved_dir_rejected(self, tmp_path: Path):
        outside = tmp_path / "outside"
        outside.mkdir()
        img = outside / "evil.png"
        img.write_bytes(b"\x00" * 100)
        # approved is a subdirectory, image is outside it
        approved = tmp_path / "approved"
        approved.mkdir()
        result = validate_image_path(str(img), approved)
        assert result is None

    def test_caption_stored_as_original_reference(
        self, work_dir: Path, approved_dir: Path
    ):
        img = work_dir / "chart.png"
        result = validate_image_path(str(img), approved_dir, caption="My chart")
        assert result is not None
        assert result.original_reference == "My chart"

    def test_no_caption_uses_path(self, work_dir: Path, approved_dir: Path):
        img = work_dir / "chart.png"
        result = validate_image_path(str(img), approved_dir)
        assert result is not None
        assert result.original_reference == str(img)

    def test_large_file_rejected(self, work_dir: Path, approved_dir: Path):
        big = work_dir / "huge.png"
        big.write_bytes(b"\x00" * 100)
        with patch.object(Path, "stat") as mock_stat:
            mock_stat.return_value.st_size = MAX_FILE_SIZE_BYTES + 1
            with patch.object(Path, "is_file", return_value=True):
                result = validate_image_path(str(big), approved_dir)
        assert result is None

    def test_symlink_escaping_rejected(self, tmp_path: Path):
        approved = tmp_path / "approved"
        approved.mkdir()
        outside = tmp_path / "secret"
        outside.mkdir()
        secret_img = outside / "secret.png"
        secret_img.write_bytes(b"\x00" * 100)
        link = approved / "link.png"
        link.symlink_to(secret_img)
        result = validate_image_path(str(link), approved)
        assert result is None

    def test_all_supported_extensions(self, work_dir: Path, approved_dir: Path):
        """Every extension in IMAGE_EXTENSIONS should be accepted."""
        for ext in IMAGE_EXTENSIONS:
            fname = f"test_file{ext}"
            (work_dir / fname).write_bytes(b"\x00" * 10)
            result = validate_image_path(str(work_dir / fname), approved_dir)
            assert result is not None, f"Failed for {ext}"
            assert result.mime_type == IMAGE_EXTENSIONS[ext]

    def test_case_insensitive_extension(self, work_dir: Path, approved_dir: Path):
        """Extensions like .PNG or .JPG should still match."""
        upper = work_dir / "UPPER.PNG"
        upper.write_bytes(b"\x00" * 100)
        result = validate_image_path(str(upper), approved_dir)
        assert result is not None

    def test_image_attachment_fields(self, work_dir: Path, approved_dir: Path):
        img = work_dir / "chart.png"
        result = validate_image_path(str(img), approved_dir)
        assert result is not None
        assert isinstance(result, ImageAttachment)
        assert result.mime_type == "image/png"
        assert result.original_reference == str(img)
