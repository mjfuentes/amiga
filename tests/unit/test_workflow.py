import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestWorkflow:
    """Simple test to verify code workflow."""

    def test_simple_addition(self):
        """Test basic arithmetic to verify workflow."""
        result = 2 + 2
        assert result == 4

    def test_string_concatenation(self):
        """Test string operations."""
        result = "hello" + " " + "world"
        assert result == "hello world"
