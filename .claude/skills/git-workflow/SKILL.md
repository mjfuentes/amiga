---
name: git-workflow
description: AMIGA git commit and workflow conventions
---

## Commit Messages
Start with verb: Add, Fix, Update, Refactor
Be specific: "Fix null pointer in auth.py:42" not "Fix bug"

## Never Commit
- .env files
- data/* (runtime state)
- logs/* (application logs)
- __pycache__/, *.pyc

## Always Commit After Code Changes
Agents must commit after file modifications to prevent git dirty state blocking.

## Pre-commit Hooks
Installed: black, isort, ruff, bandit, pytest, secret detection
Run manually: `pre-commit run --all-files`
