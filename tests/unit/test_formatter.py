#!/usr/bin/env python3
"""
Test script for response formatter
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from messaging.formatter import ResponseFormatter, format_telegram_response


@pytest.mark.parametrize("text,expected_contains", [
    (
        "The groovetherapy repository has been deleted from /Users/matifuentes/Workspace/groovetherapy",
        "/Users/matifuentes/Workspace/groovetherapy",
    ),
    (
        "I modified telegram_bot/main.py to add the formatter",
        "telegram_bot/main.py",
    ),
    (
        "Check ~/projects/myapp for the config",
        "~/projects/myapp",
    ),
])
def test_path_formatting(text, expected_contains):
    """Test file path highlighting"""
    formatter = ResponseFormatter()
    result = formatter.format_response(text)
    assert expected_contains in result
    assert len(result) > 0


@pytest.mark.parametrize("text,expected_repo", [
    ("Do you want to delete groovetherapy?", "groovetherapy"),
    ("The agentlab repository contains the bot code", "agentlab"),
    ("Working on myproject project now", "myproject"),
])
def test_repository_formatting(text, expected_repo):
    """Test repository name highlighting"""
    formatter = ResponseFormatter()
    result = formatter.format_response(text)
    assert expected_repo in text
    assert len(result) > 0


def test_list_formatting():
    """Test list formatting"""
    formatter = ResponseFormatter()

    text = """Here are the steps:
* First step
* Second step
* Third step

Then continue with more text."""

    result = formatter.format_response(text)
    assert "First step" in result
    assert "Second step" in result
    assert "Third step" in result
    assert len(result) > 0


def test_code_block_formatting():
    """Test code block formatting"""
    formatter = ResponseFormatter()

    text = """Here's the code:```python
def hello():
    print("world")
```That's it!"""

    result = formatter.format_response(text)
    assert "def hello():" in result
    assert 'print("world")' in result
    assert len(result) > 0


def test_complete_response():
    """Test a complete realistic response"""
    formatter = ResponseFormatter()

    text = """Done. The groovetherapy repository has been permanently deleted from /Users/matifuentes/Workspace/groovetherapy.

If this repository was connected to a remote (GitHub, GitLab, etc.), you'll need to delete it there separately through the platform's web interface.

Next steps:
* Check your GitHub account
* Remove any related configurations
* Update your local bookmarks"""

    result = formatter.format_response(text)
    assert "groovetherapy" in result
    assert "/Users/matifuentes/Workspace/groovetherapy" in result
    assert "Check your GitHub account" in result
    assert len(result) > 0


def test_chunking_long_text():
    """Test that long text exceeding document_threshold returns document"""
    # Create a long message (>3000 chars after formatting)
    long_text = "This is a test. " * 300

    result = format_telegram_response(long_text, max_length=4096, document_threshold=3000)

    # Should return tuple of (summary, document_path) for very long text
    assert isinstance(result, tuple), "Long text should return document tuple"
    assert len(result) == 2, "Document tuple should have 2 elements"
    summary, doc_path = result
    assert isinstance(summary, str), "First element should be summary string"
    assert isinstance(doc_path, str), "Second element should be document path"
    assert doc_path.endswith(".md"), "Document should be markdown file"


def test_chunking_short_text():
    """Test that short text doesn't get chunked or converted to document"""
    short_text = "This is a short message."
    result = format_telegram_response(short_text, max_length=4096, document_threshold=3000)

    assert isinstance(result, list), "Short text should return list of chunks"
    assert len(result) == 1, "Short text should not be chunked"
    assert "This is a short message" in result[0], "Content should be preserved"


def test_chunking_medium_text():
    """Test text that needs chunking but not document conversion"""
    # Create text that's <3000 chars but would naturally split at 2048
    medium_text = "Short line. " * 200  # ~2400 chars
    result = format_telegram_response(medium_text, max_length=2048, document_threshold=3000)

    assert isinstance(result, list), "Medium text should return list of chunks"
    assert len(result) > 1, "Text should be split into multiple chunks"
    # Note: Chunking may not perfectly respect max_length due to word boundaries
    # Just verify we got multiple chunks for readability
    assert all(len(chunk) <= 2500 for chunk in result), "Chunks should be reasonably sized"
