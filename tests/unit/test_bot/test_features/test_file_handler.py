"""Tests for file handler feature."""

import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.bot.features.file_handler import (
    CodebaseAnalysis,
    FileHandler,
    ProcessedFile,
)
from src.config import Settings
from src.security.validators import SecurityValidator


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
def security_validator(temp_dir):
    """Create security validator."""
    return SecurityValidator(temp_dir)


@pytest.fixture
def file_handler(config, security_validator):
    """Create file handler instance."""
    return FileHandler(config, security_validator)


class TestFileHandlerInitialization:
    """Test FileHandler initialization."""

    def test_initialization(self, file_handler, config):
        """Test handler is properly initialized."""
        assert file_handler.config == config
        assert file_handler.temp_dir.exists()
        assert len(file_handler.code_extensions) > 30
        assert len(file_handler.language_map) > 15

    def test_code_extensions_include_common_languages(self, file_handler):
        """Test code extensions include common languages."""
        assert ".py" in file_handler.code_extensions
        assert ".js" in file_handler.code_extensions
        assert ".ts" in file_handler.code_extensions
        assert ".java" in file_handler.code_extensions
        assert ".go" in file_handler.code_extensions
        assert ".rs" in file_handler.code_extensions

    def test_language_map_correctness(self, file_handler):
        """Test language mapping is correct."""
        assert file_handler.language_map[".py"] == "Python"
        assert file_handler.language_map[".js"] == "JavaScript"
        assert file_handler.language_map[".ts"] == "TypeScript"
        assert file_handler.language_map[".go"] == "Go"
        assert file_handler.language_map[".rs"] == "Rust"


class TestFileTypeDetection:
    """Test file type detection."""

    def test_detect_archive_types(self, file_handler, temp_dir):
        """Test detection of archive file types."""
        archive_extensions = [".zip", ".tar", ".gz", ".bz2", ".xz"]
        for ext in archive_extensions:
            file_path = temp_dir / f"test{ext}"
            file_path.touch()
            assert file_handler._detect_file_type(file_path) == "archive"

    def test_detect_code_files(self, file_handler, temp_dir):
        """Test detection of code file types."""
        code_files = ["test.py", "app.js", "main.go", "lib.rs"]
        for filename in code_files:
            file_path = temp_dir / filename
            file_path.write_text("# code")
            assert file_handler._detect_file_type(file_path) == "code"

    def test_detect_text_files(self, file_handler, temp_dir):
        """Test detection of text files."""
        file_path = temp_dir / "readme.txt"
        file_path.write_text("This is a text file")
        assert file_handler._detect_file_type(file_path) == "text"

    def test_detect_binary_files(self, file_handler, temp_dir):
        """Test detection of binary files."""
        file_path = temp_dir / "binary.bin"
        file_path.write_bytes(b"\x00\x01\x02\x03\xff\xfe")
        assert file_handler._detect_file_type(file_path) == "binary"


class TestDocumentDownload:
    """Test document download functionality."""

    @pytest.mark.asyncio
    async def test_download_file_with_filename(self, file_handler):
        """Test downloading file with filename."""
        # Mock document and file
        document = Mock()
        document.file_name = "test.py"
        document.get_file = AsyncMock()

        mock_file = AsyncMock()
        mock_file.download_to_drive = AsyncMock()
        document.get_file.return_value = mock_file

        # Download file
        file_path = await file_handler._download_file(document)

        # Verify
        assert file_path.name == "test.py"
        assert file_path.parent == file_handler.temp_dir
        mock_file.download_to_drive.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_file_without_filename(self, file_handler):
        """Test downloading file without filename (generates UUID)."""
        # Mock document and file
        document = Mock()
        document.file_name = None
        document.get_file = AsyncMock()

        mock_file = AsyncMock()
        mock_file.download_to_drive = AsyncMock()
        document.get_file.return_value = mock_file

        # Download file
        file_path = await file_handler._download_file(document)

        # Verify
        assert file_path.name.startswith("file_")
        assert file_path.parent == file_handler.temp_dir
        mock_file.download_to_drive.assert_called_once()


class TestCodeFileProcessing:
    """Test code file processing."""

    @pytest.mark.asyncio
    async def test_process_python_file(self, file_handler, temp_dir):
        """Test processing Python code file."""
        # Create test file
        file_path = temp_dir / "test.py"
        code = "def hello():\n    print('Hello, World!')\n"
        file_path.write_text(code)

        # Process file
        result = await file_handler._process_code_file(file_path, "Test context")

        # Verify
        assert isinstance(result, ProcessedFile)
        assert result.type == "code"
        assert "test.py" in result.prompt
        assert "Python" in result.prompt
        assert code in result.prompt
        assert result.metadata["language"] == "Python"
        assert result.metadata["lines"] == 2
        assert result.metadata["size"] > 0

    @pytest.mark.asyncio
    async def test_process_javascript_file(self, file_handler, temp_dir):
        """Test processing JavaScript code file."""
        file_path = temp_dir / "app.js"
        code = "console.log('Hello');"
        file_path.write_text(code)

        result = await file_handler._process_code_file(file_path, "")

        assert result.type == "code"
        assert result.metadata["language"] == "JavaScript"
        assert "app.js" in result.prompt


class TestTextFileProcessing:
    """Test text file processing."""

    @pytest.mark.asyncio
    async def test_process_text_file(self, file_handler, temp_dir):
        """Test processing text file."""
        file_path = temp_dir / "readme.txt"
        content = "This is a README file\nWith multiple lines"
        file_path.write_text(content)

        result = await file_handler._process_text_file(file_path, "Context")

        assert isinstance(result, ProcessedFile)
        assert result.type == "text"
        assert "readme.txt" in result.prompt
        assert content in result.prompt
        assert result.metadata["lines"] == 2


class TestArchiveProcessing:
    """Test archive processing with security checks."""

    @pytest.mark.asyncio
    async def test_process_valid_zip_archive(self, file_handler, temp_dir):
        """Test processing valid ZIP archive."""
        # Create test archive
        archive_path = temp_dir / "test.zip"
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr("file1.py", "print('hello')")
            zf.writestr("file2.js", "console.log('world');")

        # Process archive
        result = await file_handler._process_archive(archive_path, "Test")

        # Verify
        assert result.type == "archive"
        assert result.metadata["file_count"] > 0
        assert result.metadata["code_files"] > 0
        assert "Project structure:" in result.prompt

    @pytest.mark.asyncio
    async def test_zip_bomb_protection(self, file_handler, temp_dir):
        """Test protection against ZIP bombs."""
        # Create archive with files that appear large
        archive_path = temp_dir / "bomb.zip"

        with zipfile.ZipFile(archive_path, "w") as zf:
            # Create a ZipInfo object with inflated size
            info = zipfile.ZipInfo("large_file.txt")
            info.file_size = 150 * 1024 * 1024  # 150MB (over 100MB limit)
            info.compress_size = 1024  # Small compressed size
            # Don't actually write that much data
            zf.writestr(info, b"x" * 1024)

        # Should raise ValueError
        with pytest.raises(ValueError, match="Archive too large"):
            await file_handler._process_archive(archive_path, "")

    @pytest.mark.asyncio
    async def test_path_traversal_protection_zip(self, file_handler, temp_dir):
        """Test protection against path traversal in ZIP files."""
        archive_path = temp_dir / "traversal.zip"

        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Try to write to parent directory
            zf.writestr("../../../etc/passwd", "malicious content")
            zf.writestr("normal_file.txt", "safe content")

        # Process archive - should skip malicious file
        result = await file_handler._process_archive(archive_path, "")

        # Should complete without error but skip traversal files
        assert result.type == "archive"

    @pytest.mark.asyncio
    async def test_absolute_path_protection_zip(self, file_handler, temp_dir):
        """Test protection against absolute paths in ZIP files."""
        archive_path = temp_dir / "absolute.zip"

        with zipfile.ZipFile(archive_path, "w") as zf:
            # Absolute paths should be skipped
            zf.writestr("/etc/passwd", "malicious")
            zf.writestr("safe.txt", "safe")

        result = await file_handler._process_archive(archive_path, "")
        assert result.type == "archive"

    @pytest.mark.asyncio
    async def test_process_tar_archive(self, file_handler, temp_dir):
        """Test processing TAR archive."""
        import tarfile

        # Create test tar archive
        archive_path = temp_dir / "test.tar"
        with tarfile.open(archive_path, "w") as tf:
            # Create temp files to add
            temp_file = temp_dir / "temp_for_tar.py"
            temp_file.write_text("print('test')")
            tf.add(temp_file, arcname="test.py")

        # Process archive
        result = await file_handler._process_archive(archive_path, "Test")

        # Verify
        assert result.type == "archive"
        assert result.metadata["file_count"] > 0

    @pytest.mark.asyncio
    async def test_tar_path_traversal_protection(self, file_handler, temp_dir):
        """Test protection against path traversal in TAR files."""
        import tarfile

        archive_path = temp_dir / "traversal.tar"

        # Create a file with traversal in name
        safe_file = temp_dir / "safe.txt"
        safe_file.write_text("safe")

        with tarfile.open(archive_path, "w") as tf:
            # Add with dangerous path name
            tf.add(safe_file, arcname="../../../etc/passwd")
            tf.add(safe_file, arcname="normal.txt")

        # Should process without error, skipping dangerous files
        result = await file_handler._process_archive(archive_path, "")
        assert result.type == "archive"


class TestFileTreeBuilding:
    """Test file tree building."""

    def test_build_simple_file_tree(self, file_handler, temp_dir):
        """Test building file tree for simple directory."""
        # Create structure
        (temp_dir / "file1.txt").write_text("content")
        (temp_dir / "file2.py").write_text("code")
        subdir = temp_dir / "subdir"
        subdir.mkdir()
        (subdir / "file3.js").write_text("js code")

        # Build tree
        tree = file_handler._build_file_tree(temp_dir)

        # Verify
        assert "file1.txt" in tree
        assert "file2.py" in tree
        assert "subdir/" in tree
        assert "file3.js" in tree

    def test_file_tree_sorting(self, file_handler, temp_dir):
        """Test file tree shows directories before files."""
        # Create files and directories
        (temp_dir / "z_file.txt").write_text("content")
        (temp_dir / "a_dir").mkdir()
        (temp_dir / "m_file.py").write_text("code")

        tree = file_handler._build_file_tree(temp_dir)

        # Directory should come before files in the tree
        assert tree.index("a_dir/") < tree.index("m_file.py")

    def test_format_size(self, file_handler):
        """Test file size formatting."""
        assert "B" in file_handler._format_size(100)
        assert "KB" in file_handler._format_size(2048)
        assert "MB" in file_handler._format_size(5 * 1024 * 1024)
        assert "GB" in file_handler._format_size(3 * 1024 * 1024 * 1024)


class TestCodeFileFinding:
    """Test finding and sorting code files."""

    def test_find_code_files(self, file_handler, temp_dir):
        """Test finding code files in directory."""
        # Create code files
        (temp_dir / "app.py").write_text("code")
        (temp_dir / "script.js").write_text("code")
        (temp_dir / "readme.txt").write_text("text")
        subdir = temp_dir / "src"
        subdir.mkdir()
        (subdir / "module.py").write_text("code")

        # Find code files
        code_files = file_handler._find_code_files(temp_dir)

        # Verify
        assert len(code_files) == 3  # .py and .js files
        assert any(f.name == "app.py" for f in code_files)
        assert any(f.name == "script.js" for f in code_files)
        assert any(f.name == "module.py" for f in code_files)

    def test_skip_common_directories(self, file_handler, temp_dir):
        """Test skipping common non-code directories."""
        # Create files in excluded directories
        for excluded in ["node_modules", "__pycache__", ".git", "dist", "build"]:
            excluded_dir = temp_dir / excluded
            excluded_dir.mkdir()
            (excluded_dir / "file.py").write_text("code")

        # Create normal file
        (temp_dir / "app.py").write_text("code")

        # Find code files
        code_files = file_handler._find_code_files(temp_dir)

        # Should only find the normal file
        assert len(code_files) == 1
        assert code_files[0].name == "app.py"

    def test_prioritize_main_files(self, file_handler, temp_dir):
        """Test prioritization of main/index files."""
        # Create files in non-priority order
        (temp_dir / "utils.py").write_text("code")
        (temp_dir / "main.py").write_text("code")
        (temp_dir / "helper.py").write_text("code")
        (temp_dir / "index.js").write_text("code")

        code_files = file_handler._find_code_files(temp_dir)

        # main.py and index.js should be prioritized
        assert code_files[0].name in ["main.py", "index.js"]


class TestLanguageDetection:
    """Test programming language detection."""

    def test_detect_common_languages(self, file_handler):
        """Test detection of common programming languages."""
        tests = {
            ".py": "Python",
            ".js": "JavaScript",
            ".ts": "TypeScript",
            ".java": "Java",
            ".go": "Go",
            ".rs": "Rust",
            ".rb": "Ruby",
            ".php": "PHP",
        }

        for ext, expected_lang in tests.items():
            assert file_handler._detect_language(ext) == expected_lang

    def test_detect_unknown_extension(self, file_handler):
        """Test detection of unknown file extension."""
        assert file_handler._detect_language(".unknown") == "text"


class TestCodebaseAnalysis:
    """Test codebase analysis functionality."""

    @pytest.mark.asyncio
    async def test_analyze_python_project(self, file_handler, temp_dir):
        """Test analyzing a Python project."""
        # Create Python project structure
        (temp_dir / "main.py").write_text("# TODO: implement\nprint('hello')")
        (temp_dir / "utils.py").write_text("def helper(): pass")
        (temp_dir / "requirements.txt").write_text("flask==2.0.0")

        test_dir = temp_dir / "tests"
        test_dir.mkdir()
        (test_dir / "test_main.py").write_text("def test_main(): pass")

        # Analyze
        analysis = await file_handler.analyze_codebase(temp_dir)

        # Verify
        assert isinstance(analysis, CodebaseAnalysis)
        assert "Python" in analysis.languages
        assert analysis.languages["Python"] >= 2
        assert analysis.test_coverage is True
        assert analysis.todo_count >= 1
        assert len(analysis.frameworks) > 0

    @pytest.mark.asyncio
    async def test_find_entry_points(self, file_handler, temp_dir):
        """Test finding entry points in codebase."""
        # Create entry point files
        (temp_dir / "main.py").write_text("code")
        (temp_dir / "app.py").write_text("code")
        (temp_dir / "index.js").write_text("code")

        entry_points = file_handler._find_entry_points(temp_dir)

        assert len(entry_points) >= 3
        assert any("main.py" in ep for ep in entry_points)
        assert any("app.py" in ep for ep in entry_points)
        assert any("index.js" in ep for ep in entry_points)

    @pytest.mark.asyncio
    async def test_detect_frameworks(self, file_handler, temp_dir):
        """Test detecting frameworks and libraries."""
        # Create Django project
        (temp_dir / "manage.py").write_text("django management")
        (temp_dir / "requirements.txt").write_text("django==3.2.0\nflask==2.0.0")

        frameworks = file_handler._detect_frameworks(temp_dir)

        assert "Django" in frameworks
        assert "Flask" in frameworks

    @pytest.mark.asyncio
    async def test_detect_frameworks_nodejs(self, file_handler, temp_dir):
        """Test detecting Node.js frameworks."""
        (temp_dir / "package.json").write_text('{"dependencies": {"react": "^17.0.0"}}')

        frameworks = file_handler._detect_frameworks(temp_dir)

        assert "React" in frameworks

    @pytest.mark.asyncio
    async def test_find_todos_and_fixmes(self, file_handler, temp_dir):
        """Test finding TODO and FIXME comments."""
        (temp_dir / "code.py").write_text(
            "# TODO: implement this\n# FIXME: bug here\n# todo: also this"
        )

        todo_count = await file_handler._find_todos(temp_dir)

        assert todo_count >= 3  # Case insensitive

    def test_find_test_files(self, file_handler, temp_dir):
        """Test finding test files."""
        # Create test files
        (temp_dir / "test_app.py").write_text("test")
        (temp_dir / "utils_test.py").write_text("test")
        (temp_dir / "app.test.js").write_text("test")

        tests_dir = temp_dir / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_utils.py").write_text("test")

        test_files = file_handler._find_test_files(temp_dir)

        assert len(test_files) >= 4


class TestDocumentUploadHandling:
    """Test document upload handling."""

    @pytest.mark.asyncio
    async def test_handle_code_file_upload(self, file_handler):
        """Test handling code file upload."""
        # Mock document
        document = Mock()
        document.file_name = "test.py"
        document.get_file = AsyncMock()

        mock_file = AsyncMock()
        mock_file.download_to_drive = AsyncMock(
            side_effect=lambda path: Path(path).write_text("print('hello')")
        )
        document.get_file.return_value = mock_file

        # Handle upload
        result = await file_handler.handle_document_upload(document, 123, "Context")

        # Verify
        assert isinstance(result, ProcessedFile)
        assert result.type == "code"

    @pytest.mark.asyncio
    async def test_handle_unsupported_file_type(self, file_handler):
        """Test handling unsupported file type."""
        # Mock document with binary file
        document = Mock()
        document.file_name = "image.bin"
        document.get_file = AsyncMock()

        mock_file = AsyncMock()
        mock_file.download_to_drive = AsyncMock(
            side_effect=lambda path: Path(path).write_bytes(b"\x00\x01\x02")
        )
        document.get_file.return_value = mock_file

        # Should raise ValueError
        with pytest.raises(ValueError, match="Unsupported file type"):
            await file_handler.handle_document_upload(document, 123, "")

    @pytest.mark.asyncio
    async def test_cleanup_after_upload(self, file_handler):
        """Test file cleanup after upload processing."""
        document = Mock()
        document.file_name = "test.py"
        document.get_file = AsyncMock()

        test_file_path = None

        def save_path_and_write(path):
            nonlocal test_file_path
            test_file_path = Path(path)
            test_file_path.write_text("print('hello')")

        mock_file = AsyncMock()
        mock_file.download_to_drive = AsyncMock(side_effect=save_path_and_write)
        document.get_file.return_value = mock_file

        # Handle upload
        await file_handler.handle_document_upload(document, 123, "")

        # File should be cleaned up
        assert test_file_path is not None
        assert not test_file_path.exists()


class TestErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_handle_corrupted_zip(self, file_handler, temp_dir):
        """Test handling corrupted ZIP file."""
        # Create corrupted zip
        corrupted_zip = temp_dir / "corrupted.zip"
        corrupted_zip.write_bytes(b"not a zip file")

        # Should raise an error
        with pytest.raises(Exception):
            await file_handler._process_archive(corrupted_zip, "")

    @pytest.mark.asyncio
    async def test_handle_missing_file(self, file_handler, temp_dir):
        """Test handling missing file."""
        missing_file = temp_dir / "nonexistent.py"

        with pytest.raises(FileNotFoundError):
            await file_handler._process_code_file(missing_file, "")

    @pytest.mark.asyncio
    async def test_analyze_empty_directory(self, file_handler, temp_dir):
        """Test analyzing empty directory."""
        analysis = await file_handler.analyze_codebase(temp_dir)

        assert isinstance(analysis, CodebaseAnalysis)
        assert len(analysis.languages) == 0
        assert analysis.todo_count == 0
        assert analysis.test_coverage is False

    @pytest.mark.asyncio
    async def test_handle_unicode_errors_gracefully(self, file_handler, temp_dir):
        """Test handling files with unicode errors."""
        # Create file with invalid UTF-8
        bad_file = temp_dir / "bad.py"
        bad_file.write_bytes(b"print('hello')\x80\x81\x82")

        # Should handle gracefully with errors='ignore'
        result = await file_handler._process_code_file(bad_file, "")
        assert isinstance(result, ProcessedFile)


class TestSecurityIntegration:
    """Test integration with security validator."""

    def test_uses_security_validator(self, file_handler, security_validator):
        """Test that file handler uses security validator."""
        assert file_handler.security == security_validator

    @pytest.mark.asyncio
    async def test_respects_temp_directory_isolation(self, file_handler):
        """Test that operations are isolated to temp directory."""
        # All downloaded files should go to temp_dir
        document = Mock()
        document.file_name = "test.py"
        document.get_file = AsyncMock()

        mock_file = AsyncMock()
        mock_file.download_to_drive = AsyncMock()
        document.get_file.return_value = mock_file

        file_path = await file_handler._download_file(document)

        # Should be in temp directory
        assert file_handler.temp_dir in file_path.parents
