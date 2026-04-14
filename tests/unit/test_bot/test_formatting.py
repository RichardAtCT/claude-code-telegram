"""Tests for response formatting utilities."""

from unittest.mock import Mock

import pytest

from src.bot.utils.formatting import (
    CodeHighlighter,
    FormattedMessage,
    ProgressIndicator,
    ResponseFormatter,
)
from src.bot.utils.html_format import escape_html, markdown_to_telegram_html
from src.config.settings import Settings


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = Mock(spec=Settings)
    settings.enable_quick_actions = True
    return settings


@pytest.fixture
def formatter(mock_settings):
    """Create response formatter."""
    return ResponseFormatter(mock_settings)


class TestFormattedMessage:
    """Test FormattedMessage dataclass."""

    def test_formatted_message_creation(self):
        """Test FormattedMessage creation."""
        msg = FormattedMessage("Test message")
        assert msg.text == "Test message"
        assert msg.parse_mode == "HTML"
        assert msg.reply_markup is None

    def test_formatted_message_length(self):
        """Test FormattedMessage length calculation."""
        msg = FormattedMessage("Hello, world!")
        assert len(msg) == 13


class TestResponseFormatter:
    """Test ResponseFormatter functionality."""

    def test_formatter_initialization(self, mock_settings):
        """Test formatter initialization."""
        formatter = ResponseFormatter(mock_settings)
        assert formatter.settings == mock_settings
        assert formatter.max_message_length == 4000
        assert formatter.max_code_block_length == 15000

    def test_format_simple_message(self, formatter):
        """Test formatting simple message."""
        text = "Hello, world!"
        messages = formatter.format_claude_response(text)

        assert len(messages) == 1
        assert messages[0].text == text
        assert messages[0].parse_mode == "HTML"

    def test_format_code_blocks(self, formatter):
        """Test code block formatting."""
        text = "Here's some code:\n```python\nprint('hello')\n```"
        messages = formatter.format_claude_response(text)

        assert len(messages) == 1
        assert "<pre>" in messages[0].text
        assert "<code" in messages[0].text
        assert (
            "print(&#x27;hello&#x27;)" in messages[0].text
            or "print('hello')" in messages[0].text
        )

    def test_split_long_message(self, formatter):
        """Test splitting long messages."""
        # Create a message longer than max_message_length
        long_text = "A" * 5000
        messages = formatter.format_claude_response(long_text)

        # Should be split into multiple messages
        assert len(messages) > 1

        # Each message should be under the limit
        for msg in messages:
            assert len(msg.text) <= formatter.max_message_length

    def test_format_error_message(self, formatter):
        """Test error message formatting."""
        error_msg = formatter.format_error_message("Something went wrong", "Error")

        assert "❌" in error_msg.text
        assert "Error" in error_msg.text
        assert "Something went wrong" in error_msg.text
        assert error_msg.parse_mode == "HTML"

    def test_format_success_message(self, formatter):
        """Test success message formatting."""
        success_msg = formatter.format_success_message("Operation completed")

        assert "✅" in success_msg.text
        assert "Success" in success_msg.text
        assert "Operation completed" in success_msg.text

    def test_format_code_output(self, formatter):
        """Test code output formatting."""
        output = "Hello, world!\nThis is output."
        messages = formatter.format_code_output(output, "python", "Test Output")

        assert len(messages) >= 1
        assert "📄" in messages[0].text
        assert "Test Output" in messages[0].text
        assert "<pre>" in messages[0].text
        assert "<code" in messages[0].text

    def test_format_empty_code_output(self, formatter):
        """Test formatting empty code output."""
        messages = formatter.format_code_output("", "python", "Empty Output")

        assert len(messages) == 1
        assert "empty output" in messages[0].text

    def test_format_file_list(self, formatter):
        """Test file list formatting."""
        files = ["file1.py", "file2.js", "directory/"]
        msg = formatter.format_file_list(files, "test_dir")

        assert "📂" in msg.text
        assert "test_dir" in msg.text
        assert "📄 file1.py" in msg.text
        assert "📄 file2.js" in msg.text
        assert "📁 directory/" in msg.text

    def test_format_empty_file_list(self, formatter):
        """Test formatting empty file list."""
        msg = formatter.format_file_list([], "empty_dir")

        assert "📂" in msg.text
        assert "empty_dir" in msg.text
        assert "empty directory" in msg.text

    def test_format_progress_message(self, formatter):
        """Test progress message formatting."""
        msg = formatter.format_progress_message("Processing", 50.0)

        assert "🔄" in msg.text
        assert "Processing" in msg.text
        assert "50%" in msg.text
        assert "▓" in msg.text  # Progress bar

    def test_format_progress_message_no_percentage(self, formatter):
        """Test progress message without percentage."""
        msg = formatter.format_progress_message("Loading")

        assert "🔄" in msg.text
        assert "Loading" in msg.text
        assert "%" not in msg.text

    def test_clean_text(self, formatter):
        """Test text cleaning."""
        messy_text = "Hello\n\n\n\nWorld"
        cleaned = formatter._clean_text(messy_text)

        # Should reduce multiple newlines
        assert "\n\n\n" not in cleaned

    def test_clean_text_converts_markdown_to_html(self, formatter):
        """Test that _clean_text converts markdown bold to HTML."""
        text = "This is **bold** text"
        cleaned = formatter._clean_text(text)
        assert "<b>bold</b>" in cleaned

    def test_code_block_preservation(self, formatter):
        """Test that code blocks preserve special characters."""
        text = "Normal text\n```\ncode_with_underscores\n```"
        cleaned = formatter._clean_text(text)

        # Code block content should be inside <pre><code> tags
        assert "<pre><code>" in cleaned
        assert "code_with_underscores" in cleaned

    def test_truncate_long_code_block(self, formatter):
        """Test truncation of very long code blocks via _format_code_blocks."""
        long_code = "x" * 20000
        # Test _format_code_blocks directly with pre-converted HTML
        html_block = f'<pre><code class="language-python">{long_code}</code></pre>'

        result = formatter._format_code_blocks(html_block)

        # Should be truncated (code block exceeds 15000-char limit)
        assert "truncated" in result.lower()

    def test_long_code_block_split_not_truncated(self, formatter):
        """Test that moderately long code blocks are split, not truncated."""
        long_code = "x" * 5000
        text = f"```python\n{long_code}\n```"

        messages = formatter.format_claude_response(text)

        # Should be split across messages, not truncated
        assert len(messages) >= 1
        full_text = "".join(m.text for m in messages)
        assert "truncated" not in full_text.lower()

    def test_quick_actions_keyboard(self, formatter):
        """Test quick actions keyboard generation."""
        keyboard = formatter._get_quick_actions_keyboard()

        assert keyboard is not None
        assert len(keyboard.inline_keyboard) > 0

        # Check that buttons have callback data
        for row in keyboard.inline_keyboard:
            for button in row:
                assert button.callback_data.startswith("quick:")

    def test_confirmation_keyboard(self, formatter):
        """Test confirmation keyboard creation."""
        keyboard = formatter.create_confirmation_keyboard("confirm:yes")

        assert len(keyboard.inline_keyboard) == 1
        assert len(keyboard.inline_keyboard[0]) == 2

        yes_button, no_button = keyboard.inline_keyboard[0]
        assert "Yes" in yes_button.text
        assert "No" in no_button.text

    def test_navigation_keyboard(self, formatter):
        """Test navigation keyboard creation."""
        options = [
            ("Option 1", "action:1"),
            ("Option 2", "action:2"),
            ("Option 3", "action:3"),
        ]

        keyboard = formatter.create_navigation_keyboard(options)

        # Should create 2 rows (2 buttons per row, plus 1 remaining)
        assert len(keyboard.inline_keyboard) == 2
        assert len(keyboard.inline_keyboard[0]) == 2
        assert len(keyboard.inline_keyboard[1]) == 1

    def test_message_splitting_preserves_code_blocks(self, formatter):
        """Test that message splitting properly handles HTML code blocks."""
        # Create a message with HTML code block that would be split
        code = "x" * 2000
        text = f"Some text\n<pre><code>{code}</code></pre>\nMore text"

        messages = formatter._split_message(text)

        # Should properly close and reopen code blocks across splits
        for msg in messages:
            opening_count = msg.text.count("<pre><code>")
            closing_count = msg.text.count("</code></pre>")

            # Should be balanced or have one extra opening (continued in next message)
            assert abs(opening_count - closing_count) <= 1


class TestEscapeHtml:
    """Test HTML escaping utility."""

    def test_escape_ampersand(self):
        assert escape_html("a & b") == "a &amp; b"

    def test_escape_angle_brackets(self):
        assert escape_html("<script>") == "&lt;script&gt;"

    def test_no_change_for_safe_text(self):
        assert escape_html("hello world") == "hello world"

    def test_escape_all_three(self):
        assert escape_html("a & <b> & c") == "a &amp; &lt;b&gt; &amp; c"


class TestMarkdownToTelegramHtml:
    """Test markdown to HTML conversion."""

    def test_bold(self):
        assert "<b>bold</b>" in markdown_to_telegram_html("**bold**")

    def test_italic_asterisk(self):
        assert "<i>italic</i>" in markdown_to_telegram_html("*italic*")

    def test_italic_underscore_word_boundary(self):
        result = markdown_to_telegram_html("_italic_")
        assert "<i>italic</i>" in result

    def test_underscore_in_identifier_not_converted(self):
        result = markdown_to_telegram_html("my_var_name")
        # Should NOT wrap in <i> tags since underscores are inside a word
        assert "<i>" not in result

    def test_inline_code(self):
        result = markdown_to_telegram_html("`code here`")
        assert "<code>code here</code>" in result

    def test_fenced_code_block(self):
        result = markdown_to_telegram_html("```python\nprint('hi')\n```")
        assert "<pre>" in result
        assert "<code" in result
        assert "print" in result

    def test_fenced_code_block_escapes_html(self):
        result = markdown_to_telegram_html("```\n<script>alert(1)</script>\n```")
        assert "&lt;script&gt;" in result

    def test_link(self):
        result = markdown_to_telegram_html("[text](https://example.com)")
        assert '<a href="https://example.com">text</a>' in result

    def test_header(self):
        result = markdown_to_telegram_html("# My Header")
        assert "<b>My Header</b>" in result

    def test_strikethrough(self):
        result = markdown_to_telegram_html("~~deleted~~")
        assert "<s>deleted</s>" in result

    def test_angle_brackets_escaped_in_text(self):
        result = markdown_to_telegram_html("x < y > z")
        assert "&lt;" in result
        assert "&gt;" in result

    def test_mixed_content(self):
        text = "**Bold** and `code` and *italic*"
        result = markdown_to_telegram_html(text)
        assert "<b>Bold</b>" in result
        assert "<code>code</code>" in result
        assert "<i>italic</i>" in result


class TestProgressIndicator:
    """Test ProgressIndicator utility functions."""

    def test_create_progress_bar(self):
        """Test progress bar creation."""
        bar = ProgressIndicator.create_bar(50, 10)

        assert len(bar) == 10
        assert "▓" in bar
        assert "░" in bar

    def test_create_progress_bar_full(self):
        """Test full progress bar."""
        bar = ProgressIndicator.create_bar(100, 10)

        assert bar == "▓" * 10

    def test_create_progress_bar_empty(self):
        """Test empty progress bar."""
        bar = ProgressIndicator.create_bar(0, 10)

        assert bar == "░" * 10

    def test_create_spinner(self):
        """Test spinner creation."""
        spinner1 = ProgressIndicator.create_spinner(0)
        spinner2 = ProgressIndicator.create_spinner(1)

        assert len(spinner1) == 1
        assert len(spinner2) == 1
        assert spinner1 != spinner2

    def test_create_dots(self):
        """Test dots indicator."""
        dots0 = ProgressIndicator.create_dots(0)
        dots1 = ProgressIndicator.create_dots(1)
        dots3 = ProgressIndicator.create_dots(3)

        assert dots0 == ""
        assert dots1 == "."
        assert dots3 == "..."


class TestCodeHighlighter:
    """Test CodeHighlighter utility functions."""

    def test_detect_language_python(self):
        """Test Python language detection."""
        lang = CodeHighlighter.detect_language("test.py")
        assert lang == "python"

    def test_detect_language_javascript(self):
        """Test JavaScript language detection."""
        lang = CodeHighlighter.detect_language("test.js")
        assert lang == "javascript"

    def test_detect_language_unknown(self):
        """Test unknown file extension."""
        lang = CodeHighlighter.detect_language("test.unknown")
        assert lang == ""

    def test_format_code_with_language(self):
        """Test code formatting with language."""
        code = "print('hello')"
        formatted = CodeHighlighter.format_code(code, "python")

        assert formatted.startswith('<pre><code class="language-python">')
        assert formatted.endswith("</code></pre>")
        assert "print" in formatted

    def test_format_code_without_language(self):
        """Test code formatting without language."""
        code = "some code"
        formatted = CodeHighlighter.format_code(code)

        assert formatted.startswith("<pre><code>")
        assert formatted.endswith("</code></pre>")
        assert code in formatted

    def test_format_code_with_filename(self):
        """Test code formatting with filename detection."""
        code = "console.log('hello')"
        formatted = CodeHighlighter.format_code(code, filename="test.js")

        assert 'class="language-javascript"' in formatted

    def test_format_code_escapes_html(self):
        """Test that code formatting escapes HTML characters."""
        code = "if (a < b && c > d) {}"
        formatted = CodeHighlighter.format_code(code, "javascript")
        assert "&lt;" in formatted
        assert "&gt;" in formatted
        assert "&amp;" in formatted

    def test_language_extensions_coverage(self):
        """Test that language extensions are properly mapped."""
        # Test a few key extensions
        assert CodeHighlighter.detect_language("test.py") == "python"
        assert CodeHighlighter.detect_language("test.js") == "javascript"
        assert CodeHighlighter.detect_language("test.ts") == "typescript"
        assert CodeHighlighter.detect_language("test.java") == "java"
        assert CodeHighlighter.detect_language("test.cpp") == "cpp"
        assert CodeHighlighter.detect_language("test.go") == "go"
        assert CodeHighlighter.detect_language("test.rs") == "rust"


TELEGRAM_HARD_LIMIT = 4096


class TestOversizedResponseIntegration:
    """End-to-end tests ensuring no formatted chunk exceeds Telegram's 4096-char limit.

    These exercise the full format_claude_response pipeline: markdown→HTML
    conversion, HTML escaping, code block handling, semantic chunking, and
    message splitting.
    """

    def test_large_plain_text_stays_under_limit(self, formatter):
        """Plain text response much larger than one message."""
        # 12 000 chars of prose-like text with paragraph breaks
        paragraph = "The quick brown fox jumps over the lazy dog. " * 10 + "\n\n"
        text = paragraph * 30  # ~13 500 chars

        messages = formatter.format_claude_response(text)

        assert len(messages) > 1
        for i, msg in enumerate(messages):
            assert (
                len(msg.text) <= TELEGRAM_HARD_LIMIT
            ), f"Chunk {i} is {len(msg.text)} chars (limit {TELEGRAM_HARD_LIMIT})"

    def test_large_code_block_stays_under_limit(self, formatter):
        """A single huge code block must be split, not just truncated."""
        # 10 000 chars of code — well above one message but below truncation
        code_lines = [f"    result += process(item_{i})" for i in range(500)]
        text = "```python\ndef big_function():\n" + "\n".join(code_lines) + "\n```"

        messages = formatter.format_claude_response(text)

        assert len(messages) > 1
        for i, msg in enumerate(messages):
            assert (
                len(msg.text) <= TELEGRAM_HARD_LIMIT
            ), f"Chunk {i} is {len(msg.text)} chars (limit {TELEGRAM_HARD_LIMIT})"

    def test_html_entity_expansion_stays_under_limit(self, formatter):
        """Characters that expand during HTML escaping (& → &amp; etc.)."""
        # Each '&' becomes '&amp;' (5 chars), '<' becomes '&lt;' (4 chars)
        # Build a response heavy with these characters
        line = "if (a < b && c > d) { e &= f; }\n"
        text = "```go\n" + line * 200 + "```"

        messages = formatter.format_claude_response(text)

        for i, msg in enumerate(messages):
            assert len(msg.text) <= TELEGRAM_HARD_LIMIT, (
                f"Chunk {i} is {len(msg.text)} chars after HTML escaping "
                f"(limit {TELEGRAM_HARD_LIMIT})"
            )

    def test_mixed_content_stays_under_limit(self, formatter):
        """Mixed markdown: headings, bold, code blocks, file-op lines."""
        sections = []
        for n in range(5):
            sections.append(f"## Section {n}\n\n")
            sections.append(f"Here is an **explanation** of step {n}.\n\n")
            code = "\n".join([f'    print("step {n} line {j}")' for j in range(60)])
            sections.append(f"```python\n{code}\n```\n\n")
            sections.append(f"Creating file `output_{n}.py`\n\n")

        text = "".join(sections)

        messages = formatter.format_claude_response(text)

        assert len(messages) > 1
        for i, msg in enumerate(messages):
            assert (
                len(msg.text) <= TELEGRAM_HARD_LIMIT
            ), f"Chunk {i} is {len(msg.text)} chars (limit {TELEGRAM_HARD_LIMIT})"
        # All content should be present (not silently truncated)
        full = "".join(m.text for m in messages)
        assert "Section 0" in full
        assert "Section 4" in full

    def test_format_code_output_stays_under_limit(self, formatter):
        """format_code_output (used for tool output) must also respect limit."""
        output = "x = 1\n" * 2000  # ~12 000 chars

        messages = formatter.format_code_output(output, "python", "Build Output")

        for i, msg in enumerate(messages):
            assert (
                len(msg.text) <= TELEGRAM_HARD_LIMIT
            ), f"Chunk {i} is {len(msg.text)} chars (limit {TELEGRAM_HARD_LIMIT})"

    def test_colon_ending_pattern_not_truncated(self, formatter):
        """Claude's 'header:\\n\\ncontent' pattern must NOT leave ':' as last char of a chunk.

        Regression test for the primary bug: _split_message now prefers paragraph
        boundaries (\\n\\n) over line boundaries, so 'Here are the changes:\\n\\n'
        splits *after* the blank line, not after the ':' line.
        """
        header = "I've made the following changes:\n\n"
        items = "\n".join(
            f"{i}. **Step {i}**: Modified the function to handle edge case {i}"
            for i in range(1, 80)
        )
        text = header + items  # > 4000 chars

        messages = formatter.format_claude_response(text)
        assert len(messages) > 1
        first = messages[0].text.rstrip()
        assert not first.endswith(":"), (
            f"First chunk must NOT end with ':', got: ...{first[-80:]!r}"
        )
        for i, msg in enumerate(messages):
            assert len(msg.text) <= TELEGRAM_HARD_LIMIT, (
                f"Chunk {i} is {len(msg.text)} chars"
            )

    def test_split_prefers_paragraph_boundary(self, formatter):
        """_split_message should prefer paragraph boundary over bare line boundary.

        When the split point falls in the middle of a paragraph, _split_message
        looks for the nearest \\n\\n and splits there — not mid-sentence.
        This means 'header:\\n\\nbody' splits after the blank line, not after ':'.
        """
        # Build text where the first paragraph ends with ':' and the second is long
        para1 = "Summary of changes:\n\n"
        body_lines = [
            f"{i}. **Item {i}**: description for item number {i}"
            for i in range(1, 250)  # enough to exceed 4000 chars
        ]
        body = "\n".join(body_lines)
        text = para1 + body  # > 4000 chars, ':' is at end of para1

        assert len(text) > formatter.max_message_length, (
            f"Test setup error: text is {len(text)} chars but limit is "
            f"{formatter.max_message_length}"
        )

        messages = formatter._split_message(text)
        assert len(messages) > 1, (
            f"Text is {len(text)} chars, should split (limit={formatter.max_message_length})"
        )
        first = messages[0].text.rstrip()
        # The split should be at \\n\\n (after para1), so first msg ends at the blank line,
        # NOT at ':'
        assert not first.endswith(":"), (
            f"First chunk must not end with ':' (should split at \\n\\n), "
            f"got: ...{first[-60:]!r}"
        )

    def test_split_preserves_code_block_language_class(self, formatter):
        """Code blocks split across messages must preserve the language class attribute."""
        code_lines = "\n".join(f"    x_{i} = process(item_{i})" for i in range(200))
        text = f"```python\ndef big_fn():\n{code_lines}\n```"

        messages = formatter.format_claude_response(text)
        # Find messages that reopen a code block (contain <pre><code> without </code>)
        reopened = [
            m for m in messages
            if "<pre><code>" in m.text and "</code></pre>" not in m.text
        ]
        if reopened:
            # At least one reopened block should carry the language class
            found_lang = any(
                'class="language-python"' in m.text for m in reopened
            )
            assert found_lang, (
                "Reopened code blocks should preserve language class; "
                f"got: {[m.text[:60] for m in reopened]!r}"
            )

    def test_semantic_chunking_detects_html_code_blocks(self, formatter):
        """_should_use_semantic_chunking must count <pre> tags (not ```) in HTML text."""
        code_block = '<pre><code class="language-python">x = 1\n</code></pre>'
        text_with_3_blocks = (
            f"intro\n\n{code_block}\n\nmiddle\n\n"
            f"{code_block}\n\nend\n\n{code_block}"
        )
        result = formatter._should_use_semantic_chunking(text_with_3_blocks)
        assert result is True, "3 <pre> blocks should trigger semantic chunking"

    def test_no_double_escape_in_truncated_code_block(self, formatter):
        """_format_code_blocks must NOT double-escape HTML entities on truncation."""
        # Simulate HTML-escaped content (what markdown_to_telegram_html produces)
        inner = "if (a &lt; b &amp;&amp; c &gt; d) {}" * 500
        html_block = f"<pre><code>{inner}</code></pre>"
        result = formatter._format_code_blocks(html_block)
        # Double-escape would produce &amp;lt; or &amp;amp;
        assert "&amp;lt;" not in result, "must not double-escape &lt;"
        assert "&amp;amp;" not in result, "must not double-escape &amp;"
        assert "&lt;" in result or "truncated" in result  # original entities preserved

    def test_split_paragraph_boundary_min_chunk_guard(self, formatter):
        """Paragraph split must not produce trivially-small chunks (1/8 guard)."""
        short_header = "Title:\n\n"
        big_body = "A" * 4500  # single paragraph > 4000 chars
        text = short_header + big_body

        messages = formatter.format_claude_response(text)
        assert len(messages) > 1
        # Each chunk must be under Telegram's hard limit
        for i, msg in enumerate(messages):
            assert len(msg.text) <= TELEGRAM_HARD_LIMIT, (
                f"Chunk {i} exceeds limit: {len(msg.text)} chars"
            )

    def test_identify_sections_single_line_code_block(self, formatter):
        """_identify_sections must handle <pre>...</pre> on a single line."""
        single_line = '<pre><code>short = 1</code></pre>'
        sections = formatter._identify_sections(single_line)
        assert len(sections) == 1
        assert sections[0]["type"] == "code_block"
        assert "short = 1" in sections[0]["content"]

    def test_identify_sections_html_after_markdown_conversion(self, formatter):
        """_identify_sections works on already-HTML text (not raw markdown)."""
        # This is the exact state text is in when _identify_sections is called
        html_text = (
            "Normal paragraph.\n\n"
            '<pre><code class="language-js">console.log("hi")\n</code></pre>\n\n'
            "Another paragraph."
        )
        sections = formatter._identify_sections(html_text)
        types = [s["type"] for s in sections]
        assert "text" in types
        assert "code_block" in types
