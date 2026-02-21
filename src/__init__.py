"""Claude Code Telegram Bot.

A Telegram bot that provides remote access to Claude Code CLI, allowing developers
to interact with their projects from anywhere through a secure, terminal-like
interface within Telegram.
"""

import tomllib
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

# Read version from pyproject.toml when running from source (always current).
# Fall back to installed package metadata for pip installs without source tree.
_pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
try:
    with open(_pyproject, "rb") as _f:
        __version__: str = tomllib.load(_f)["project"]["version"]
except Exception:
    try:
        __version__ = _pkg_version("claude-code-telegram")
    except PackageNotFoundError:
        __version__ = "0.0.0-dev"

__author__ = "Richard Atkinson"
__email__ = "richardatk01@gmail.com"
__license__ = "MIT"
__homepage__ = "https://github.com/richardatkinson/claude-code-telegram"
