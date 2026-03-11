---
name: testing-requirements
description: AMIGA mandatory testing policy and coverage requirements
---

## Policy
Tests are MANDATORY for all implementations. NO EXCEPTIONS.

## Coverage Targets
- Critical paths: 80%+
- Utility functions: 100%
- Handlers: Best effort

## Test Location
All tests in `tests/` directory at project root. Named `test_*.py`.

## Test Structure
```python
import pytest

class TestFeatureName:
    def test_typical_case(self):
        result = function_to_test(input)
        assert result == expected

    def test_edge_case(self):
        pass

    def test_error_handling(self):
        with pytest.raises(ExpectedError):
            function_to_test(invalid_input)
```

## Requirements by Task Type
- New features: Unit + integration tests
- Bug fixes: Regression test (fails without fix, passes with fix)
- Refactoring: Existing tests must pass before and after
- API changes: Test all endpoints + error cases

## Running Tests
```bash
pytest tests/ -v
pytest tests/ --cov=. --cov-report=html
```
