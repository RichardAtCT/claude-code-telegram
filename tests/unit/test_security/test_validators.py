"""Tests for security validators."""

import tempfile
from pathlib import Path

import pytest

from src.security.validators import SecurityValidator


class TestSecurityValidator:
    """Test security validation functionality."""

    @pytest.fixture
    def temp_approved_dir(self):
        """Create temporary approved directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            approved_dir = Path(temp_dir) / "approved"
            approved_dir.mkdir()
            yield approved_dir

    @pytest.fixture
    def validator(self, temp_approved_dir):
        """Create security validator with temporary directory."""
        return SecurityValidator(temp_approved_dir)

    def test_validator_initialization(self, validator, temp_approved_dir):
        """Test validator initialization."""
        assert validator.approved_directory == temp_approved_dir.resolve()

    def test_validator_initialization_with_pattern_checks_disabled(
        self, temp_approved_dir
    ):
        """Validator should allow disabling dangerous pattern checks."""
        validator = SecurityValidator(temp_approved_dir, disable_security_patterns=True)
        assert validator.disable_security_patterns is True

    def test_valid_relative_path(self, validator, temp_approved_dir):
        """Test validation of valid relative paths."""
        # Create a test subdirectory
        (temp_approved_dir / "project").mkdir()

        current_dir = temp_approved_dir
        valid, path, error = validator.validate_path("project", current_dir)

        assert valid is True
        assert path == (temp_approved_dir / "project").resolve()
        assert error is None

    def test_valid_absolute_path(self, validator, temp_approved_dir):
        """Test validation of valid absolute paths (within approved dir)."""
        # Create a test subdirectory
        (temp_approved_dir / "project").mkdir()

        # Use the full path within approved directory
        test_path = str(temp_approved_dir / "project")
        valid, path, error = validator.validate_path(test_path)

        assert valid is True
        assert path == (temp_approved_dir / "project").resolve()
        assert error is None

    def test_path_traversal_attempts(self, validator, temp_approved_dir):
        """Test detection of path traversal attempts."""
        dangerous_paths = [
            "../../../etc/passwd",
            "project/../../../",
            "project/./../../sensitive",
            "~/sensitive",
            "$HOME/sensitive",
        ]

        for dangerous_path in dangerous_paths:
            valid, path, error = validator.validate_path(dangerous_path)
            assert valid is False
            assert path is None
            assert error is not None
            # Error could be either pattern detection or outside directory
            assert (
                "forbidden pattern" in error.lower()
                or "outside approved directory" in error.lower()
            )

    def test_path_outside_approved_directory(self, validator, temp_approved_dir):
        """Test rejection of paths outside approved directory."""
        # Try to access parent directory
        valid, path, error = validator.validate_path("../outside")

        assert valid is False
        assert path is None
        # Could be caught by pattern or directory check
        assert "outside approved directory" in error or "forbidden pattern" in error

    def test_empty_path_validation(self, validator):
        """Test validation of empty paths."""
        empty_paths = ["", "   ", None]

        for empty_path in empty_paths:
            if empty_path is not None:
                valid, path, error = validator.validate_path(empty_path)
                assert valid is False
                assert error == "Empty path not allowed"

    def test_dangerous_patterns_detection(self, validator):
        """Test detection of dangerous patterns in paths."""
        dangerous_patterns = [
            "test;rm -rf /",
            "test && malicious",
            "test | mail attacker",
            "test > /dev/null",
            "test < input",
            "test `whoami`",
            "test$(malicious)",
        ]

        for pattern in dangerous_patterns:
            valid, path, error = validator.validate_path(pattern)
            assert valid is False
            assert "forbidden pattern" in error

    def test_dangerous_patterns_can_be_disabled(self, temp_approved_dir):
        """Dangerous pattern checks can be disabled for trusted environments."""
        validator = SecurityValidator(temp_approved_dir, disable_security_patterns=True)

        # Pattern check is bypassed; traversal protections still apply separately.
        valid, path, error = validator.validate_path("safe|name")

        assert valid is True
        assert path == (temp_approved_dir / "safe|name").resolve()
        assert error is None

    def test_filename_validation_valid(self, validator):
        """Test validation of valid filenames."""
        valid_filenames = [
            "test.py",
            "script.js",
            "config.json",
            "README.md",
            "style.css",
            "data.sql",
            "build.sh",
        ]

        for filename in valid_filenames:
            valid, error = validator.validate_filename(filename)
            assert valid is True
            assert error is None

    def test_filename_validation_invalid_extensions(self, validator):
        """Test rejection of invalid file extensions."""
        invalid_filenames = [
            "malware.exe",
            "script.bat",
            "library.dll",
            "archive.rar",
            "installer.msi",
        ]

        for filename in invalid_filenames:
            valid, error = validator.validate_filename(filename)
            assert valid is False
            assert "not allowed" in error

    def test_filename_path_separators(self, validator):
        """Test rejection of filenames with path separators."""
        invalid_filenames = ["path/to/file.txt", "..\\file.txt", "directory/script.py"]

        for filename in invalid_filenames:
            valid, error = validator.validate_filename(filename)
            assert valid is False
            assert "path separators" in error

    def test_filename_forbidden_names(self, validator):
        """Test rejection of forbidden filenames."""
        forbidden_filenames = [
            ".env",
            ".ssh",
            "passwd",
            "shadow",
            "id_rsa",
            ".bash_history",
        ]

        for filename in forbidden_filenames:
            valid, error = validator.validate_filename(filename)
            assert valid is False
            assert "Forbidden filename" in error or "not allowed" in error

    def test_filename_hidden_files(self, validator):
        """Test rejection of hidden files (with exceptions)."""
        # Should reject most hidden files
        valid, error = validator.validate_filename(".hidden_file")
        assert valid is False
        assert "Hidden files not allowed" in error

        # But allow specific ones
        valid, error = validator.validate_filename(".gitignore")
        assert valid is True

        valid, error = validator.validate_filename(".gitkeep")
        assert valid is True

    def test_filename_too_long(self, validator):
        """Test rejection of overly long filenames."""
        long_filename = "a" * 256 + ".txt"

        valid, error = validator.validate_filename(long_filename)
        assert valid is False
        assert "too long" in error

    def test_command_input_sanitization(self, validator):
        """Test command input sanitization."""
        dangerous_inputs = [
            "ls; rm -rf /",
            "cat file && malicious",
            "echo `whoami`",
            "test | mail evil@hacker.com",
            "input > /dev/null",
            "test < /etc/passwd",
        ]

        for dangerous_input in dangerous_inputs:
            sanitized = validator.sanitize_command_input(dangerous_input)

            # Should remove dangerous characters
            assert ";" not in sanitized
            assert "&&" not in sanitized
            assert "`" not in sanitized
            assert "|" not in sanitized
            assert ">" not in sanitized
            assert "<" not in sanitized

    def test_command_input_length_limit(self, validator):
        """Test command input length limiting."""
        long_input = "a" * 1500  # Longer than 1000 char limit

        sanitized = validator.sanitize_command_input(long_input)
        assert len(sanitized) <= 1000

    def test_command_args_validation(self, validator):
        """Test command arguments validation."""
        # Valid args
        valid_args = ["--help", "file.txt", "output.json"]
        valid, sanitized, error = validator.validate_command_args(valid_args)

        assert valid is True
        assert sanitized == valid_args
        assert error is None

        # Invalid args with dangerous patterns
        invalid_args = ["--help", "; rm -rf /", "file.txt"]
        valid, sanitized, error = validator.validate_command_args(invalid_args)

        assert valid is False
        assert error is not None
        assert "forbidden pattern" in error

    def test_command_args_empty_list(self, validator):
        """Test validation of empty command args."""
        valid, sanitized, error = validator.validate_command_args([])

        assert valid is True
        assert sanitized == []
        assert error is None

    def test_safe_directory_name_validation(self, validator):
        """Test safe directory name validation."""
        # Valid directory names
        valid_names = ["project", "my_app", "test-dir", "src"]
        for name in valid_names:
            assert validator.is_safe_directory_name(name) is True

        # Invalid directory names
        invalid_names = [
            "",
            "   ",
            "dir/subdir",
            "dir\\subdir",
            "../parent",
            ".hidden",
            "dir; rm -rf /",
            "a" * 101,  # Too long
            ".env",
            "passwd",
        ]

        for name in invalid_names:
            assert validator.is_safe_directory_name(name) is False

    def test_security_summary(self, validator):
        """Test security summary generation."""
        summary = validator.get_security_summary()

        assert "approved_directory" in summary
        assert "allowed_extensions" in summary
        assert "forbidden_filenames" in summary
        assert "dangerous_patterns_count" in summary
        assert "max_filename_length" in summary
        assert "max_command_length" in summary

        # Check that counts make sense
        assert summary["dangerous_patterns_count"] > 0
        assert summary["max_filename_length"] == 255
        assert summary["max_command_length"] == 1000
        assert len(summary["allowed_extensions"]) > 10

    def test_path_validation_with_symlinks(self, validator, temp_approved_dir):
        """Test path validation with symbolic links."""
        # Create a directory and file inside approved directory
        target_dir = temp_approved_dir / "target"
        target_dir.mkdir()
        target_file = target_dir / "file.txt"
        target_file.write_text("test content")

        # Symlink inside approved dir pointing to file in approved dir
        link_path = temp_approved_dir / "link_to_file"
        link_path.symlink_to(target_file)

        # Should be valid - symlink resolves within approved directory
        valid, path, error = validator.validate_path("link_to_file")
        assert valid is True
        assert path == target_file.resolve()

    def test_case_insensitive_pattern_matching(self, validator):
        """Test that pattern matching is case insensitive where appropriate."""
        # Test dangerous patterns with different cases
        dangerous_cases = [
            "test; RM -rf /",
            "test && MALICIOUS",
            "test | MAIL evil@domain.com",
        ]

        for case in dangerous_cases:
            valid, path, error = validator.validate_path(case)
            assert valid is False
            assert "forbidden pattern" in error

    def test_whitespace_handling(self, validator):
        """Test handling of whitespace in paths and commands."""
        # Test path with whitespace
        valid, path, error = validator.validate_path("  project/file.txt  ")
        # Should handle whitespace appropriately (likely by stripping)

        # Test command sanitization with whitespace
        input_with_spaces = "  command   arg1    arg2  "
        sanitized = validator.sanitize_command_input(input_with_spaces)

        # Should normalize whitespace
        assert "  " not in sanitized  # No double spaces
        assert not sanitized.startswith(" ")  # No leading space
        assert not sanitized.endswith(" ")  # No trailing space
