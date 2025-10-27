# Test Suite

## Running Tests

### All Tests (Fast)
```bash
pytest telegram_bot/tests/
```

### With Coverage
```bash
pytest telegram_bot/tests/ --cov=telegram_bot --cov-report=html
```

### Specific Test File
```bash
pytest telegram_bot/tests/test_message_queue.py -v
```

### By Category

**Game tests only:**
```bash
pytest telegram_bot/tests/ -m game
```

**Exclude game tests:**
```bash
pytest telegram_bot/tests/ -m "not game"
```

## Test Categories

Tests are organized using pytest markers:

- `@pytest.mark.game` - Game functionality tests (Pacman, etc.)
- `@pytest.mark.slow` - Slow-running tests
- `@pytest.mark.integration` - Integration tests requiring external services
- `@pytest.mark.ui` - UI tests requiring browser/display

## Skipped Tests

Some tests are automatically skipped if dependencies are missing:

- **test_monitoring_server.py** - Requires `flask_socketio` (optional)
- **test_websocket.py** - Requires `flask_socketio` (optional)
- **test_dashboard_frontend.py** - Requires Selenium for browser automation

To run these tests, install optional dependencies:
```bash
pip install flask-socketio selenium
```

## Current Test Status

All core tests passing:
- ✅ test_filepath_logging.py (2 tests)
- ✅ test_formatter.py (6 tests)
- ✅ test_log_formatter.py (7 tests)
- ✅ test_message_queue.py (6 tests)
- ✅ test_pacman.py (21 tests)
- ✅ test_queue_simple.py (6 tests)
- ⏭️ test_dashboard_frontend.py (skipped - needs Selenium)
- ⏭️ test_monitoring_server.py (skipped - needs flask_socketio)
- ⏭️ test_websocket.py (skipped - needs flask_socketio)

**Total: 48 tests passing, 3 skipped**

## Notes

- Tests use Python 3.13+
- Virtual environment required (`venv` directory)
- Async tests use `pytest-asyncio` plugin
- Test configuration in `pyproject.toml`
