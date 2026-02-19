"""Test Claude output parsing."""

import pytest

from src.claude.parser import OutputParser, ResponseFormatter


class TestOutputParser:
    """Test output parser."""

    def test_parse_json_output(self):
        """Test JSON output parsing."""
        json_str = '{"type": "result", "content": "Hello world"}'
        result = OutputParser.parse_json_output(json_str)

        assert result["type"] == "result"
        assert result["content"] == "Hello world"

    def test_parse_invalid_json(self):
        """Test invalid JSON handling."""
        with pytest.raises(Exception):  # ClaudeParsingError
            OutputParser.parse_json_output("invalid json")

    def test_extract_code_blocks(self):
        """Test code block extraction."""
        content = """
Here's some Python code:

```python
def hello():
    print("Hello, world!")
```

And some JavaScript:

```javascript
console.log("Hello, world!");
```

And plain text:

```
Some plain text
```
"""

        blocks = OutputParser.extract_code_blocks(content)

        assert len(blocks) == 3
        assert blocks[0]["language"] == "python"
        assert "def hello():" in blocks[0]["code"]
        assert blocks[1]["language"] == "javascript"
        assert "console.log" in blocks[1]["code"]
        assert blocks[2]["language"] == "text"

    def test_extract_file_operations(self):
        """Test file operation extraction."""
        messages = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Write",
                            "input": {
                                "file_path": "/test/file.py",
                                "content": "print('hello')",
                            },
                        }
                    ]
                },
                "timestamp": "2024-01-01T00:00:00Z",
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Read",
                            "input": {"file_path": "/test/another.py"},
                        }
                    ]
                },
                "timestamp": "2024-01-01T00:01:00Z",
            },
        ]

        ops = OutputParser.extract_file_operations(messages)

        assert len(ops) == 2
        assert ops[0]["operation"] == "Write"
        assert ops[0]["path"] == "/test/file.py"
        assert ops[0]["content"] == "print('hello')"
        assert ops[1]["operation"] == "Read"
        assert ops[1]["path"] == "/test/another.py"

    def test_extract_shell_commands(self):
        """Test shell command extraction."""
        messages = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {"command": "ls -la", "description": "List files"},
                        }
                    ]
                },
                "timestamp": "2024-01-01T00:00:00Z",
            }
        ]

        commands = OutputParser.extract_shell_commands(messages)

        assert len(commands) == 1
        assert commands[0]["operation"] == "Bash"
        assert commands[0]["command"] == "ls -la"
        assert commands[0]["description"] == "List files"

    def test_extract_response_text(self):
        """Test response text extraction."""
        messages = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "Hello, "},
                        {"type": "tool_use", "name": "sometool"},
                        {"type": "text", "text": "world!"},
                    ]
                },
            }
        ]

        text = OutputParser.extract_response_text(messages)
        assert text == "Hello, \nworld!"

    def test_detect_errors(self):
        """Test error detection."""
        messages = [
            {
                "type": "error",
                "message": "Something went wrong",
                "timestamp": "2024-01-01T00:00:00Z",
            },
            {
                "type": "tool_result",
                "tool_use_id": "123",
                "result": {"is_error": True, "content": "Tool failed"},
                "timestamp": "2024-01-01T00:01:00Z",
            },
        ]

        errors = OutputParser.detect_errors(messages)

        assert len(errors) == 2
        assert errors[0]["type"] == "error"
        assert errors[0]["message"] == "Something went wrong"
        assert errors[1]["type"] == "tool_error"
        assert errors[1]["message"] == "Tool failed"

    def test_summarize_session(self):
        """Test session summary."""
        messages = [
            {"type": "user", "message": "Hello"},
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": "Here's some code:\n\n"
                            "```python\nprint('hello')\n```",
                        },
                        {
                            "type": "tool_use",
                            "name": "Write",
                            "input": {"file_path": "test.py"},
                        },
                    ]
                },
            },
            {"type": "tool_result", "result": {"content": "File written"}},
        ]

        summary = OutputParser.summarize_session(messages)

        assert summary["total_messages"] == 3
        assert summary["user_messages"] == 1
        assert summary["assistant_messages"] == 1
        assert summary["tool_calls"] == 1
        assert summary["tool_results"] == 1
        assert summary["code_blocks"] == 1
        assert summary["file_operations"] == 1


class TestResponseFormatter:
    """Test response formatter."""

    def test_format_short_response(self):
        """Test formatting short response."""
        formatter = ResponseFormatter(max_message_length=1000)
        content = "This is a short response."

        messages = formatter.format_response(content)

        assert len(messages) == 1
        assert messages[0] == content

    def test_format_long_response(self):
        """Test formatting long response."""
        formatter = ResponseFormatter(max_message_length=100)
        content = "A" * 300  # Long content

        messages = formatter.format_response(content)

        assert len(messages) > 1
        assert all(len(msg) <= 100 for msg in messages)
        assert "".join(messages) == content

    def test_format_with_code_blocks(self):
        """Test formatting preserves code blocks."""
        formatter = ResponseFormatter(max_message_length=200)
        content = """
Here's some code:

```python
def very_long_function_name_that_might_cause_splitting():
    print("This is a long line that should not be split")
    return "success"
```

End of response.
"""

        messages = formatter.format_response(content)

        # Should preserve code block integrity
        full_content = "\n".join(messages)
        assert "```python" in full_content
        assert "```" in full_content
        assert "def very_long_function_name" in full_content

    def test_format_empty_response(self):
        """Test formatting empty response."""
        formatter = ResponseFormatter()

        messages = formatter.format_response("")
        assert messages == ["_(Empty response)_"]

        messages = formatter.format_response("   ")
        assert messages == ["_(Empty response)_"]
