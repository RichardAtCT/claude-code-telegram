"""MCP server exposing Telegram-specific tools to Claude.

Runs as a stdio transport server. The ``send_file_to_user`` tool validates
file existence, then returns a success string. Actual Telegram delivery is
handled by the bot's stream callback which intercepts the tool call.
"""

from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("telegram")


@mcp.tool()
async def send_file_to_user(file_path: str, caption: str = "") -> str:
    """Send a file to the Telegram user.

    Supports any file type: images, PDFs, audio, documents, etc.

    Args:
        file_path: Absolute path to the file.
        caption: Optional caption to display with the file.

    Returns:
        Confirmation string when the file is queued for delivery.
    """
    path = Path(file_path)

    if not path.is_absolute():
        return f"Error: path must be absolute, got '{file_path}'"

    if not path.is_file():
        return f"Error: file not found: {file_path}"

    return f"File queued for delivery: {path.name}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
