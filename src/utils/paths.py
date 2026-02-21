"""Shared path utility helpers."""

from pathlib import Path

# Error message used when neither approved_directory nor approved_directories is supplied.
DIRECTORY_PARAM_ERROR = (
    "Either approved_directory or approved_directories must be provided"
)


def is_relative_to(path: Path, directory: Path) -> bool:
    """Return True when *path* is inside *directory* (inclusive of directory itself).

    Uses ``Path.relative_to`` so it is immune to simple string-prefix tricks
    (e.g. ``/foo/bar`` is not considered inside ``/foo/b``).
    """
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False
