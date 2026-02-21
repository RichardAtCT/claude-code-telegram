"""Claude Code Telegram Bot.

A Telegram bot that provides remote access to Claude Code CLI, allowing developers
to interact with their projects from anywhere through a secure, terminal-like
interface within Telegram.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("claude-code-telegram")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

__author__ = "Richard Atkinson"
__email__ = "richardatk01@gmail.com"
__license__ = "MIT"
__homepage__ = "https://github.com/richardatkinson/claude-code-telegram"
