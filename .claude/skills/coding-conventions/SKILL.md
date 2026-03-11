---
name: coding-conventions
description: AMIGA project coding conventions and style requirements
---

## Python Style
- Formatter: Black (line length 120)
- Import order: isort
- Linter: Ruff
- Type hints: Required for public APIs
- Async by default for handlers and long-running operations

## Naming
- Files: snake_case.py
- Classes: PascalCase
- Functions: snake_case()
- Constants: UPPER_SNAKE_CASE
- Private: Prefix with _

## Immutability
Always create new objects, never mutate existing ones.

## File Organization
- High cohesion, low coupling
- 200-400 lines typical, 800 max
- Functions under 50 lines
- No deep nesting (>4 levels)

## Error Handling
- Always handle errors with try/except
- Log errors with context
- Raise descriptive user-friendly messages
- No bare except clauses
