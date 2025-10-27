"""Tests for utility functions using pytest parametrization."""

import sys
from pathlib import Path

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.helpers import add_numbers, multiply_numbers, reverse_string


class TestMathOperations:
    """Test mathematical utility functions."""

    @pytest.mark.parametrize(
        "a,b,expected",
        [
            (5, 3, 8),  # positive numbers
            (-5, -3, -8),  # negative numbers
            (5, -3, 2),  # mixed numbers
            (5, 0, 5),  # add zero
            (0, 5, 5),  # add zero (commutative)
            (0, 0, 0),  # both zero
        ],
    )
    def test_add_numbers(self, a, b, expected):
        """Test adding two numbers with various input combinations."""
        assert add_numbers(a, b) == expected

    @pytest.mark.parametrize(
        "a,b,expected",
        [
            (5, 3, 15),  # positive numbers
            (-5, -3, 15),  # negative numbers
            (5, -3, -15),  # mixed numbers
            (5, 0, 0),  # multiply by zero
            (0, 5, 0),  # multiply by zero (commutative)
            (5, 1, 5),  # multiply by one
            (1, 5, 5),  # multiply by one (commutative)
        ],
    )
    def test_multiply_numbers(self, a, b, expected):
        """Test multiplying two numbers with various input combinations."""
        assert multiply_numbers(a, b) == expected


class TestStringOperations:
    """Test string utility functions."""

    @pytest.mark.parametrize(
        "input_str,expected",
        [
            ("hello", "olleh"),  # simple string
            ("", ""),  # empty string
            ("a", "a"),  # single character
            ("racecar", "racecar"),  # palindrome
            ("hello world", "dlrow olleh"),  # string with spaces
            ("123", "321"),  # numeric string
            ("A", "A"),  # single uppercase
        ],
    )
    def test_reverse_string(self, input_str, expected):
        """Test reversing strings with various input types."""
        assert reverse_string(input_str) == expected
