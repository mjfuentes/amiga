"""pytest configuration for telegram_bot tests"""

import sys
from pathlib import Path

# Add parent directory to path so tests can import telegram_bot modules
sys.path.insert(0, str(Path(__file__).parent.parent))


def pytest_configure(config):
    """Register custom markers for test categorization"""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (require external services or dependencies)"
    )
    config.addinivalue_line("markers", "ui: marks tests as UI tests (require browser/display)")
    config.addinivalue_line("markers", "game: marks tests for game functionality")
