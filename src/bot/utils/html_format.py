"""HTML formatting utilities for Telegram messages.

Telegram's HTML mode supports: <b>, <i>, <u>, <s>, <code>, <pre>,
<pre><code class="language-X">, <a href>, <blockquote>,
<blockquote expandable>, <tg-spoiler>.

This module converts Claude's markdown output into that subset.
"""

import re
from typing import List, Tuple


_INLINE_TAGS = {"b", "i", "s", "u", "code"}
_TAG_RE = re.compile(r"<(/?)(\w+)(?:\s[^>]*)?>")


def _repair_html_nesting(html: str) -> str:
    """Fix misnested inline HTML tags that Telegram would reject.

    Telegram requires strict nesting: <b><i>...</i></b> is OK,
    but <i><b>...</i></b> is rejected. This walks the tag stack
    and closes/reopens tags when it detects a mismatch.
    """
    result = []
    stack: List[str] = []
    last_end = 0

    for m in _TAG_RE.finditer(html):
        # Append text before this tag
        result.append(html[last_end:m.start()])
        last_end = m.end()

        is_close = m.group(1) == "/"
        tag = m.group(2).lower()

        # Only repair inline tags; skip <pre>, <blockquote>, <a>, etc.
        if tag not in _INLINE_TAGS:
            result.append(m.group(0))
            continue

        if not is_close:
            stack.append(tag)
            result.append(m.group(0))
        else:
            if tag in stack:
                # Close tags in reverse order up to the matching opener
                idx = len(stack) - 1 - stack[::-1].index(tag)
                tags_to_reopen = stack[idx + 1:]
                # Close everything from top to idx
                for t in reversed(stack[idx:]):
                    result.append(f"</{t}>")
                stack = stack[:idx]
                # Reopen tags that were above the matched one
                for t in tags_to_reopen:
                    result.append(f"<{t}>")
                    stack.append(t)
            else:
                # Orphan close tag — skip it
                pass

    # Append remaining text
    result.append(html[last_end:])

    # Close any unclosed tags
    for t in reversed(stack):
        result.append(f"</{t}>")

    return "".join(result)


def escape_html(text: str) -> str:
    """Escape the 3 HTML-special characters for Telegram."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def markdown_to_telegram_html(text: str) -> str:
    """Convert Claude's markdown output to Telegram-compatible HTML.

    Order of operations (early steps extract content into placeholders
    to protect it from later regex passes):

    0.  Markdown tables → aligned <pre> blocks
    1.  Fenced code blocks → <pre><code>
    2.  Inline code → <code>
    3.  Blockquotes (> text) → <blockquote>
    4.  HTML-escape remaining text
    5.  Horizontal rules (--- / ***) → ── separator
    6.  Bold (**text** / __text__)
    7.  Italic (*text* / _text_)
    8.  Links [text](url)
    9.  Headers (# Header → <b>Header</b>)
    10. Strikethrough (~~text~~)
    11. Unordered lists (- item / * item)
    12. Ordered lists (1. item)
    13. Restore placeholders
    """
    placeholders: List[Tuple[str, str]] = []
    placeholder_counter = 0

    def _make_placeholder(html_content: str) -> str:
        nonlocal placeholder_counter
        key = f"\x00PH{placeholder_counter}\x00"
        placeholder_counter += 1
        placeholders.append((key, html_content))
        return key

    # --- 0. Extract markdown tables → monospace <pre> blocks ---
    def _replace_table(m: re.Match) -> str:  # type: ignore[type-arg]
        table_text = m.group(0)
        lines = table_text.strip().split("\n")
        rows = []
        for line in lines:
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            if re.match(r"^\|[\s\-:|]+\|$", stripped):
                continue
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            if cells:
                rows.append(cells)

        if not rows:
            return table_text

        num_cols = max(len(r) for r in rows)
        col_widths = [0] * num_cols
        for row in rows:
            for i, cell in enumerate(row):
                if i < num_cols:
                    col_widths[i] = max(col_widths[i], len(cell))

        formatted_lines = []
        for row in rows:
            parts = []
            for i in range(num_cols):
                cell = row[i] if i < len(row) else ""
                parts.append(cell.ljust(col_widths[i]))
            formatted_lines.append(" │ ".join(parts))
            if len(formatted_lines) == 1:
                sep_parts = ["─" * w for w in col_widths]
                formatted_lines.append("─┼─".join(sep_parts))

        pre_content = "\n".join(formatted_lines)
        return _make_placeholder(f"<pre>{escape_html(pre_content)}</pre>")

    text = re.sub(
        r"(?:^\|.+\|$\n?){2,}",
        _replace_table,
        text,
        flags=re.MULTILINE,
    )

    # --- 1. Extract fenced code blocks ---
    def _replace_fenced(m: re.Match) -> str:  # type: ignore[type-arg]
        lang = m.group(1) or ""
        code = m.group(2)
        escaped_code = escape_html(code)
        if lang:
            html = f'<pre><code class="language-{escape_html(lang)}">{escaped_code}</code></pre>'
        else:
            html = f"<pre><code>{escaped_code}</code></pre>"
        return _make_placeholder(html)

    text = re.sub(
        r"```(\w+)?\n(.*?)```",
        _replace_fenced,
        text,
        flags=re.DOTALL,
    )

    # --- 2. Extract inline code ---
    def _replace_inline_code(m: re.Match) -> str:  # type: ignore[type-arg]
        code = m.group(1)
        escaped_code = escape_html(code)
        return _make_placeholder(f"<code>{escaped_code}</code>")

    text = re.sub(r"`([^`\n]+)`", _replace_inline_code, text)

    # --- 3. Blockquotes: > text → <blockquote> ---
    def _replace_blockquote(m: re.Match) -> str:  # type: ignore[type-arg]
        block = m.group(0)
        # Strip the leading > (and optional space) from each line
        lines = []
        for line in block.split("\n"):
            stripped = re.sub(r"^>\s?", "", line)
            lines.append(stripped)
        inner = "\n".join(lines)
        # Recursively format the blockquote content
        inner_html = escape_html(inner)
        return _make_placeholder(f"<blockquote>{inner_html}</blockquote>")

    text = re.sub(
        r"(?:^>.*$\n?)+",
        _replace_blockquote,
        text,
        flags=re.MULTILINE,
    )

    # --- 4. HTML-escape remaining text ---
    text = escape_html(text)

    # --- 5. Horizontal rules: --- or *** or ___ → visual separator ---
    text = re.sub(
        r"^(?:---+|\*\*\*+|___+)\s*$",
        "──────────",
        text,
        flags=re.MULTILINE,
    )

    # --- 6. Bold: **text** or __text__ ---
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)

    # --- 7. Italic: *text* (require non-space after/before) ---
    text = re.sub(r"\*(\S.*?\S|\S)\*", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_(\S.*?\S|\S)_(?!\w)", r"<i>\1</i>", text)

    # --- 8. Links: [text](url) ---
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2">\1</a>',
        text,
    )

    # --- 9. Headers: # Header → <b>Header</b> ---
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    # --- 10. Strikethrough: ~~text~~ ---
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)

    # --- 11. Unordered lists: - item / * item → bullet ---
    text = re.sub(r"^[\-\*]\s+", "• ", text, flags=re.MULTILINE)

    # --- 12. Ordered lists: 1. item → keep number with period ---
    # (Telegram has no <ol>, so just clean up the formatting)
    text = re.sub(r"^(\d+)\.\s+", r"\1. ", text, flags=re.MULTILINE)

    # --- 13. Restore placeholders ---
    for key, html_content in placeholders:
        text = text.replace(key, html_content)

    # --- 14. Repair HTML tag nesting ---
    # Telegram is strict about nesting: <b><i>...</i></b> is OK,
    # but <i><b>...</i></b> is rejected. Fix any mismatches.
    text = _repair_html_nesting(text)

    return text
