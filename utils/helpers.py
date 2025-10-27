"""Utility functions for the Telegram bot.

This module provides basic mathematical and string manipulation utilities:
- add_numbers: Performs integer addition
- multiply_numbers: Performs integer multiplication
- reverse_string: Reverses string characters

These are simple helper functions demonstrating the bot's utility module structure.
"""


def add_numbers(a: int, b: int) -> int:
    """
    Add two numbers together.

    Args:
        a: First number
        b: Second number

    Returns:
        Sum of a and b
    """
    return a + b


def multiply_numbers(a: int, b: int) -> int:
    """
    Multiply two numbers together.

    Args:
        a: First number
        b: Second number

    Returns:
        Product of a and b
    """
    return a * b


def reverse_string(text: str) -> str:
    """
    Reverse a string.

    Args:
        text: String to reverse

    Returns:
        Reversed string
    """
    return text[::-1]
