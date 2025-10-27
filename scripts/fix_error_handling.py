#!/usr/bin/env python3
"""
Script to systematically add exc_info=True to logger.error calls
"""

import re
import sys
from pathlib import Path


def fix_logger_errors(file_path: Path) -> int:
    """
    Add exc_info=True to logger.error calls that don't have it

    Returns:
        Number of fixes applied
    """
    content = file_path.read_text()
    fixes = 0

    # Pattern to find logger.error calls without exc_info=True
    # Matches: logger.error(...)
    # But NOT if it already has exc_info=True

    lines = content.split('\n')
    new_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Check if this line has logger.error
        if 'logger.error(' in line and 'exc_info=True' not in line:
            # Check if it's already a multi-line call with exc_info on next lines
            has_exc_info_ahead = False
            for j in range(i+1, min(i+5, len(lines))):
                if 'exc_info=True' in lines[j]:
                    has_exc_info_ahead = True
                    break
                if ')' in lines[j] and 'logger' not in lines[j]:
                    break

            if not has_exc_info_ahead:
                # Count indentation
                indent = len(line) - len(line.lstrip())
                indent_str = line[:indent]

                # Check if it's a single-line call
                if line.strip().endswith(')'):
                    # Single line call - modify it
                    # Find the closing paren
                    close_paren_idx = line.rfind(')')
                    modified_line = line[:close_paren_idx] + ', exc_info=True' + line[close_paren_idx:]
                    new_lines.append(modified_line)
                    fixes += 1
                else:
                    # Multi-line call - find the closing paren
                    new_lines.append(line)
                    i += 1

                    # Find closing paren
                    while i < len(lines):
                        current_line = lines[i]
                        new_lines.append(current_line)

                        if ')' in current_line:
                            # Found closing paren - add exc_info before it
                            close_paren_idx = current_line.rfind(')')
                            # Remove the last line we just added
                            new_lines.pop()
                            # Add it with exc_info
                            modified_line = current_line[:close_paren_idx] + ', exc_info=True' + current_line[close_paren_idx:]
                            new_lines.append(modified_line)
                            fixes += 1
                            break

                        i += 1
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

        i += 1

    if fixes > 0:
        file_path.write_text('\n'.join(new_lines))
        print(f"✓ {file_path}: {fixes} fixes applied")

    return fixes


def main():
    """Main function"""
    # Target directories
    target_dirs = [
        'core',
        'claude',
        'tasks',
        'monitoring',
        'web_chat'
    ]

    worktree = Path('/tmp/agentlab-worktrees/1761561241')
    total_fixes = 0
    files_fixed = 0

    for dir_name in target_dirs:
        dir_path = worktree / dir_name
        if not dir_path.exists():
            continue

        for py_file in dir_path.rglob('*.py'):
            fixes = fix_logger_errors(py_file)
            if fixes > 0:
                total_fixes += fixes
                files_fixed += 1

    print(f"\n✓ Total: {files_fixed} files, {total_fixes} fixes applied")


if __name__ == '__main__':
    main()
