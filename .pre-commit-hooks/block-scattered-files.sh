#!/bin/bash
# Block scattered file additions that violate project organization
# See CLAUDE.md - File Organization section

set -e

# Get staged files (additions only, not deletions)
staged_files=$(git diff --name-only --cached --diff-filter=A)

# Check for .playwright-mcp/ additions
playwright_files=$(echo "$staged_files" | grep "^\.playwright-mcp/" || true)
if [ -n "$playwright_files" ]; then
    echo "ERROR: .playwright-mcp/ files should not be committed"
    echo "Found: $playwright_files"
    echo ""
    echo "Screenshots should go to:"
    echo "  - docs/screenshots/ for documentation"
    echo "  - telegram_bot/static/ for served assets"
    exit 1
fi

# Check for .claude/hooks.backup/ additions
hook_backup_files=$(echo "$staged_files" | grep "^\.claude/hooks\.backup/" || true)
if [ -n "$hook_backup_files" ]; then
    echo "ERROR: .claude/hooks.backup/ files should not be committed"
    echo "Found: $hook_backup_files"
    exit 1
fi

# Check for data/archive/ additions
archive_files=$(echo "$staged_files" | grep "^data/archive/" || true)
if [ -n "$archive_files" ]; then
    echo "ERROR: data/archive/ files should not be committed (auto-generated backups)"
    echo "Found: $archive_files"
    exit 1
fi

# Check for duplicate files in root that belong in telegram_bot/
duplicate_files=$(echo "$staged_files" | grep -E "^(database|config)\.py$" || true)
if [ -n "$duplicate_files" ]; then
    echo "ERROR: Root-level Python module files should be in telegram_bot/"
    echo "Found: $duplicate_files"
    echo ""
    echo "These files belong in telegram_bot/ directory"
    exit 1
fi

# Success
exit 0
