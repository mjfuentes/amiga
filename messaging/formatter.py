"""
Response formatter for Telegram messages
Enhances plain text responses with HTML formatting for better display
"""

import re
import tempfile


class ResponseFormatter:
    """Format agent responses for better Telegram display using HTML"""

    def __init__(self, workspace_path: str | None = None):
        self.workspace_path = workspace_path

    def format_response(self, text: str) -> str:
        """
        Apply HTML formatting to response text

        Enhancements:
        - Escape HTML entities for safety
        - Highlight file paths with <code>
        - Highlight repository names with <b>
        - Format code blocks with <pre>
        - Format lists properly
        """
        if not text:
            return text

        # Apply formatters in order
        formatted = text
        formatted = self._strip_existing_markdown(formatted)
        # Extract and process code blocks first (they need special handling)
        formatted, code_blocks = self._extract_code_blocks(formatted)
        # Escape HTML in the remaining text
        formatted = self._escape_html_entities(formatted)
        # Restore code blocks (already escaped internally)
        formatted = self._restore_code_blocks(formatted, code_blocks)
        formatted = self._format_paths(formatted)
        formatted = self._format_repositories(formatted)
        formatted = self._format_lists(formatted)

        return formatted

    def _strip_existing_markdown(self, text: str) -> str:
        """Remove markdown asterisks and underscores for plain text"""
        # Remove bold/italic markdown syntax but keep the text
        # Only remove if they're markdown formatting, not literal asterisks

        # Remove bold: **text** or __text__
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"__(.+?)__", r"\1", text)

        # Remove italic: *text* or _text_ (but be careful not to break paths)
        text = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"\1", text)
        text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", text)

        return text

    def _extract_code_blocks(self, text: str) -> tuple[str, list[str]]:
        """
        Extract code blocks and replace them with placeholders
        Returns: (text_with_placeholders, list_of_code_blocks)
        """
        code_blocks = []
        # Use a placeholder that won't be affected by HTML escaping
        placeholder_template = "\x00CODE_BLOCK_{}\x00"

        # Extract triple backtick code blocks
        def replace_code_block(match):
            code = match.group(1)
            # Escape HTML in code
            code = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            formatted_code = f"<pre>{code}</pre>"
            idx = len(code_blocks)
            code_blocks.append(formatted_code)
            return placeholder_template.format(idx)

        text = re.sub(r"```(?:\w+)?\n?(.*?)```", replace_code_block, text, flags=re.DOTALL)

        # Extract inline `code`
        def replace_inline_code(match):
            code = match.group(1)
            code = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            formatted_code = f"<code>{code}</code>"
            idx = len(code_blocks)
            code_blocks.append(formatted_code)
            return placeholder_template.format(idx)

        text = re.sub(r"`([^`]+)`", replace_inline_code, text)

        return text, code_blocks

    def _escape_html_entities(self, text: str) -> str:
        """
        Escape HTML entities in plain text
        This prevents Telegram parsing errors from special characters like < > &
        """
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        return text

    def _restore_code_blocks(self, text: str, code_blocks: list[str]) -> str:
        """Restore code blocks from placeholders"""
        # Use the same placeholder format as in _extract_code_blocks
        placeholder_template = "\x00CODE_BLOCK_{}\x00"
        for idx, code_block in enumerate(code_blocks):
            placeholder = placeholder_template.format(idx)
            text = text.replace(placeholder, code_block)
        return text

    def _format_paths(self, text: str) -> str:
        """
        Detect and format file/directory paths with <code>
        Note: text is already HTML-escaped at this point, so we need to match escaped patterns
        """
        # Match common path patterns (order matters - more specific first)
        patterns = [
            # Home directory paths: ~/path/to/file
            r"(~(?:/[\w\-./]+)+)",
            # Absolute paths: /Users/path/to/file
            r"(/(?:[\w\-./]+/)+[\w\-.]+)",
            # Relative paths with extensions: src/file.py
            r"([\w\-]+/[\w\-./]+\.\w+)",
        ]

        for pattern in patterns:
            # Find all matches
            matches = list(re.finditer(pattern, text))
            replacements = []

            for match in matches:
                path = match.group(1)
                start = match.start()
                end = match.end()

                # Skip if already in HTML tags (check for &lt;code&gt; or <code> patterns)
                context_before = text[max(0, start - 20) : start]
                if "&lt;code&gt;" in context_before or "<code>" in context_before:
                    continue
                if "&lt;pre&gt;" in context_before or "<pre>" in context_before:
                    continue

                # Skip URLs
                if "http://" in path or "https://" in path:
                    continue

                # Remove trailing punctuation from path
                clean_path = path.rstrip(".,;:!?")
                if len(clean_path) < len(path):
                    # Adjust end position to exclude punctuation
                    end = start + len(clean_path)
                    path = clean_path

                replacements.append((start, end, f"<code>{path}</code>"))

            # Apply replacements in reverse order to maintain indices
            for start, end, replacement in reversed(replacements):
                text = text[:start] + replacement + text[end:]

        return text

    def _format_repositories(self, text: str) -> str:
        """
        Highlight repository/project names with bold
        Disabled for now as it's too aggressive - can be re-enabled with better patterns
        """
        # DISABLED: Too aggressive, matches common words
        # patterns = [
        #     (r'\b([\w\-]+)\s+(repository|repo|project)\b', lambda m: f'<b>{m.group(1)}</b> {m.group(2)}'),
        #     (r'\b(repository|repo|project)\s+([\w\-]+)\b', lambda m: f'{m.group(1)} <b>{m.group(2)}</b>'),
        # ]
        #
        # for pattern, replacement in patterns:
        #     text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        return text

    def _format_lists(self, text: str) -> str:
        """Format bullet lists and numbered lists"""
        lines = text.split("\n")
        formatted_lines = []
        in_list = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Check if line is a list item
            is_bullet = stripped.startswith("- ") or stripped.startswith("* ") or stripped.startswith("• ")
            is_numbered = bool(re.match(r"^\d+\.\s", stripped))
            is_list_item = is_bullet or is_numbered

            # Add spacing before list if needed
            if is_list_item and not in_list and i > 0 and formatted_lines and formatted_lines[-1].strip():
                formatted_lines.append("")

            # Convert bullets to consistent format
            if is_bullet:
                content = re.sub(r"^[*\-•]\s+", "", stripped)
                formatted_lines.append(f"  • {content}")
            else:
                formatted_lines.append(line)

            in_list = is_list_item

        return "\n".join(formatted_lines)


def format_telegram_response(
    text: str, workspace_path: str | None = None, max_length: int = 4096, document_threshold: int = 3000
) -> list[str] | tuple[str, str]:
    """
    Format response and split into Telegram-compatible chunks, or create .md document for long responses

    Args:
        text: Raw response text
        workspace_path: Workspace path for context
        max_length: Maximum message length (Telegram limit is 4096)
        document_threshold: If formatted response exceeds this length, return as .md document

    Returns:
        - List of formatted message chunks (for normal responses)
        - Tuple of (summary_message, document_path) for long responses
    """
    formatter = ResponseFormatter(workspace_path)
    formatted = formatter.format_response(text)

    # Check if response is too long and should be sent as document
    if len(formatted) > document_threshold:
        # Create summary message
        lines = text.split("\n")
        summary_lines = []
        char_count = 0

        # Take first few lines as summary (max 500 chars)
        for line in lines:
            if char_count + len(line) > 500:
                break
            summary_lines.append(line)
            char_count += len(line) + 1

        summary = "\n".join(summary_lines)
        if len(text) > char_count:
            summary += "\n\n📄 Full response attached as document..."

        # Create temporary markdown file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, prefix="response_") as tmp:
            tmp.write(text)
            tmp_path = tmp.name

        # Return tuple indicating document mode: (summary, document_path)
        return (formatter.format_response(summary), tmp_path)

    # Normal flow: split into chunks if needed
    if len(formatted) <= max_length:
        return [formatted]

    # Smart chunking: try to split on paragraphs/sections
    chunks = []
    current_chunk = ""

    for line in formatted.split("\n"):
        # If adding this line exceeds limit, save current chunk
        if len(current_chunk) + len(line) + 1 > max_length:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = line + "\n"
            else:
                # Line itself is too long, force split
                chunks.append(line[:max_length])
                current_chunk = line[max_length:] + "\n"
        else:
            current_chunk += line + "\n"

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks
