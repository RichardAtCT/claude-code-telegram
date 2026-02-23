"""Tests for image extraction from Claude responses."""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.bot.utils.image_extractor import (
    IMAGE_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
    MAX_IMAGES_PER_RESPONSE,
    PHOTO_SIZE_LIMIT,
    TELEGRAM_PHOTO_EXTENSIONS,
    ImageAttachment,
    extract_images_from_response,
    should_send_as_photo,
)


@pytest.fixture
def work_dir(tmp_path: Path) -> Path:
    """Create a working directory with some image files."""
    img_dir = tmp_path / "project"
    img_dir.mkdir()
    # Create some image files
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
    # Create a subdirectory with images
    sub = img_dir / "output"
    sub.mkdir()
    (sub / "result.png").write_bytes(b"\x00" * 100)
    return img_dir


@pytest.fixture
def approved_dir(tmp_path: Path) -> Path:
    """The approved directory is tmp_path itself."""
    return tmp_path


# --- Path detection patterns ---


class TestBacktickPaths:
    def test_backtick_wrapped_absolute(self, work_dir: Path, approved_dir: Path):
        text = f"I saved the chart to `{work_dir}/chart.png`."
        result = extract_images_from_response(text, work_dir, approved_dir)
        assert len(result) == 1
        assert result[0].path == (work_dir / "chart.png").resolve()

    def test_backtick_wrapped_relative(self, work_dir: Path, approved_dir: Path):
        text = "The output is at `output/result.png`."
        result = extract_images_from_response(text, work_dir, approved_dir)
        assert len(result) == 1
        assert result[0].path == (work_dir / "output" / "result.png").resolve()


class TestQuotedPaths:
    def test_double_quoted(self, work_dir: Path, approved_dir: Path):
        text = f'Saved to "{work_dir}/photo.jpg" successfully.'
        result = extract_images_from_response(text, work_dir, approved_dir)
        assert len(result) == 1
        assert result[0].mime_type == "image/jpeg"

    def test_single_quoted(self, work_dir: Path, approved_dir: Path):
        text = f"Saved to '{work_dir}/diagram.svg' successfully."
        result = extract_images_from_response(text, work_dir, approved_dir)
        assert len(result) == 1
        assert result[0].mime_type == "image/svg+xml"


class TestMarkdownImageSyntax:
    def test_markdown_image(self, work_dir: Path, approved_dir: Path):
        text = f"![Chart](/{work_dir}/chart.png)"
        result = extract_images_from_response(text, work_dir, approved_dir)
        assert len(result) == 1

    def test_markdown_image_with_alt_text(self, work_dir: Path, approved_dir: Path):
        text = f"![My fancy chart](/{work_dir}/chart.png)"
        result = extract_images_from_response(text, work_dir, approved_dir)
        assert len(result) == 1


class TestBarePaths:
    def test_bare_absolute_path(self, work_dir: Path, approved_dir: Path):
        text = f"The file is at {work_dir}/chart.png and it looks great."
        result = extract_images_from_response(text, work_dir, approved_dir)
        assert len(result) == 1

    def test_bare_relative_path_with_dot_slash(
        self, work_dir: Path, approved_dir: Path
    ):
        text = "Created ./chart.png in the current directory."
        result = extract_images_from_response(text, work_dir, approved_dir)
        assert len(result) == 1


class TestMultipleImages:
    def test_multiple_images_in_response(self, work_dir: Path, approved_dir: Path):
        text = (
            f"Created `{work_dir}/chart.png` and `{work_dir}/photo.jpg`.\n"
            f"Also saved `{work_dir}/diagram.svg`."
        )
        result = extract_images_from_response(text, work_dir, approved_dir)
        assert len(result) == 3


# --- Security tests ---


class TestSecurityValidation:
    def test_reject_path_outside_approved_dir(self, work_dir: Path, tmp_path: Path):
        """Paths outside approved_directory must be rejected."""
        outside = tmp_path / "outside"
        outside.mkdir()
        img = outside / "evil.png"
        img.write_bytes(b"\x00" * 100)

        text = f"`{img}`"
        # approved_dir is work_dir (a subdir of tmp_path), not tmp_path
        result = extract_images_from_response(text, work_dir, work_dir)
        assert len(result) == 0

    def test_reject_symlink_escaping_boundary(self, work_dir: Path, tmp_path: Path):
        """Symlinks that resolve outside approved_directory must be rejected."""
        outside = tmp_path / "secret"
        outside.mkdir()
        secret_img = outside / "secret.png"
        secret_img.write_bytes(b"\x00" * 100)

        # Create symlink inside work_dir pointing outside
        link = work_dir / "link.png"
        link.symlink_to(secret_img)

        text = f"`{link}`"
        result = extract_images_from_response(text, work_dir, work_dir)
        assert len(result) == 0

    def test_path_traversal_rejected(self, work_dir: Path, approved_dir: Path):
        """Paths with .. that escape the boundary must be rejected."""
        # Create file outside
        outside = approved_dir.parent / "outside_img.png"
        outside.write_bytes(b"\x00" * 100)

        text = f"`{work_dir}/../../outside_img.png`"
        result = extract_images_from_response(text, work_dir, approved_dir)
        assert len(result) == 0


# --- File validation ---


class TestFileValidation:
    def test_skip_nonexistent_files(self, work_dir: Path, approved_dir: Path):
        text = f"`{work_dir}/nonexistent.png`"
        result = extract_images_from_response(text, work_dir, approved_dir)
        assert len(result) == 0

    def test_skip_large_files(self, work_dir: Path, approved_dir: Path):
        """Files over 50 MB should be skipped."""
        big = work_dir / "huge.png"
        big.write_bytes(b"\x00" * 100)

        text = f"`{big}`"
        # Mock stat to report huge size
        with patch.object(Path, "stat") as mock_stat:
            mock_stat.return_value.st_size = MAX_FILE_SIZE_BYTES + 1
            # Also need is_file to return True
            with patch.object(Path, "is_file", return_value=True):
                result = extract_images_from_response(text, work_dir, approved_dir)
        assert len(result) == 0

    def test_skip_non_image_extensions(self, work_dir: Path, approved_dir: Path):
        """Only recognised image extensions should be extracted."""
        txt_file = work_dir / "notes.txt"
        txt_file.write_text("hello")

        text = f"`{txt_file}`"
        result = extract_images_from_response(text, work_dir, approved_dir)
        assert len(result) == 0


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


# --- Deduplication ---


class TestDeduplication:
    def test_duplicate_paths_deduplicated(self, work_dir: Path, approved_dir: Path):
        text = f"`{work_dir}/chart.png` is the same as `{work_dir}/chart.png`"
        result = extract_images_from_response(text, work_dir, approved_dir)
        assert len(result) == 1

    def test_same_file_different_references(self, work_dir: Path, approved_dir: Path):
        """Same resolved path via relative and absolute should deduplicate."""
        text = f"`{work_dir}/chart.png` and `chart.png`"
        result = extract_images_from_response(text, work_dir, approved_dir)
        assert len(result) == 1


# --- Cap ---


class TestMaxCap:
    def test_max_images_cap(self, tmp_path: Path):
        """Should not return more than MAX_IMAGES_PER_RESPONSE images."""
        img_dir = tmp_path / "many"
        img_dir.mkdir()
        names = []
        for i in range(MAX_IMAGES_PER_RESPONSE + 5):
            name = f"img_{i:03d}.png"
            (img_dir / name).write_bytes(b"\x00" * 10)
            names.append(name)

        text = " ".join(f"`{img_dir / n}`" for n in names)
        result = extract_images_from_response(text, img_dir, tmp_path)
        assert len(result) == MAX_IMAGES_PER_RESPONSE


# --- Edge cases ---


class TestEdgeCases:
    def test_empty_text(self, work_dir: Path, approved_dir: Path):
        result = extract_images_from_response("", work_dir, approved_dir)
        assert result == []

    def test_no_image_references(self, work_dir: Path, approved_dir: Path):
        text = "Here is some text with no image paths at all."
        result = extract_images_from_response(text, work_dir, approved_dir)
        assert result == []

    def test_case_insensitive_extension(self, work_dir: Path, approved_dir: Path):
        """Extensions like .PNG or .Jpg should still match."""
        upper = work_dir / "UPPER.PNG"
        upper.write_bytes(b"\x00" * 100)
        text = f"`{upper}`"
        result = extract_images_from_response(text, work_dir, approved_dir)
        assert len(result) == 1

    def test_path_with_spaces(self, work_dir: Path, approved_dir: Path):
        spaced = work_dir / "my chart.png"
        spaced.write_bytes(b"\x00" * 100)
        text = f'"{spaced}"'
        result = extract_images_from_response(text, work_dir, approved_dir)
        assert len(result) == 1

    def test_all_supported_extensions(self, work_dir: Path, approved_dir: Path):
        """Verify every extension in IMAGE_EXTENSIONS is detected."""
        for ext in IMAGE_EXTENSIONS:
            fname = f"test_file{ext}"
            (work_dir / fname).write_bytes(b"\x00" * 10)

        text = " ".join(f"`{work_dir / f'test_file{ext}'}`" for ext in IMAGE_EXTENSIONS)
        result = extract_images_from_response(text, work_dir, approved_dir)
        assert len(result) == len(IMAGE_EXTENSIONS)

    def test_telegram_photo_extensions_subset(self):
        """TELEGRAM_PHOTO_EXTENSIONS should be a subset of IMAGE_EXTENSIONS keys."""
        for ext in TELEGRAM_PHOTO_EXTENSIONS:
            assert ext in IMAGE_EXTENSIONS

    def test_svg_not_in_photo_extensions(self):
        assert ".svg" not in TELEGRAM_PHOTO_EXTENSIONS

    def test_image_attachment_fields(self, work_dir: Path, approved_dir: Path):
        text = f"`{work_dir}/chart.png`"
        result = extract_images_from_response(text, work_dir, approved_dir)
        assert len(result) == 1
        img = result[0]
        assert isinstance(img, ImageAttachment)
        assert img.mime_type == "image/png"
        assert img.original_reference == f"{work_dir}/chart.png"


# --- Tool-based extraction ---


class TestToolBasedExtraction:
    def test_read_tool_image_detected(self, work_dir: Path, approved_dir: Path):
        """Images from Read tool calls should be detected even without text refs."""
        tools_used = [
            {"name": "Read", "input": {"file_path": f"{work_dir}/chart.png"}},
        ]
        result = extract_images_from_response(
            "Here are the slides.", work_dir, approved_dir, tools_used=tools_used
        )
        assert len(result) == 1
        assert result[0].path == (work_dir / "chart.png").resolve()

    def test_write_tool_image_detected(self, work_dir: Path, approved_dir: Path):
        """Images from Write tool calls should be detected."""
        tools_used = [
            {"name": "Write", "input": {"file_path": f"{work_dir}/photo.jpg"}},
        ]
        result = extract_images_from_response(
            "", work_dir, approved_dir, tools_used=tools_used
        )
        assert len(result) == 1

    def test_non_image_tool_calls_ignored(self, work_dir: Path, approved_dir: Path):
        """Read of non-image files should not produce results."""
        tools_used = [
            {"name": "Read", "input": {"file_path": f"{work_dir}/readme.txt"}},
        ]
        # Create the txt file so it exists
        (work_dir / "readme.txt").write_text("hello")
        result = extract_images_from_response(
            "", work_dir, approved_dir, tools_used=tools_used
        )
        assert len(result) == 0

    def test_tool_and_text_deduplicate(self, work_dir: Path, approved_dir: Path):
        """Same image found in text and tool calls should not duplicate."""
        tools_used = [
            {"name": "Read", "input": {"file_path": f"{work_dir}/chart.png"}},
        ]
        text = f"I read `{work_dir}/chart.png`."
        result = extract_images_from_response(
            text, work_dir, approved_dir, tools_used=tools_used
        )
        assert len(result) == 1

    def test_multiple_tool_images(self, work_dir: Path, approved_dir: Path):
        """Multiple image tool calls should all be detected."""
        tools_used = [
            {"name": "Read", "input": {"file_path": f"{work_dir}/chart.png"}},
            {"name": "Read", "input": {"file_path": f"{work_dir}/photo.jpg"}},
            {"name": "Read", "input": {"file_path": f"{work_dir}/diagram.svg"}},
        ]
        result = extract_images_from_response(
            "Here are the images.", work_dir, approved_dir, tools_used=tools_used
        )
        assert len(result) == 3

    def test_tool_image_outside_approved_dir_rejected(
        self, work_dir: Path, tmp_path: Path
    ):
        """Tool image paths outside approved dir should be rejected."""
        outside = tmp_path / "outside"
        outside.mkdir()
        img = outside / "evil.png"
        img.write_bytes(b"\x00" * 100)

        tools_used = [{"name": "Read", "input": {"file_path": str(img)}}]
        result = extract_images_from_response(
            "", work_dir, work_dir, tools_used=tools_used
        )
        assert len(result) == 0

    def test_no_tools_used(self, work_dir: Path, approved_dir: Path):
        """None tools_used should work fine."""
        result = extract_images_from_response(
            "No images here.", work_dir, approved_dir, tools_used=None
        )
        assert len(result) == 0
