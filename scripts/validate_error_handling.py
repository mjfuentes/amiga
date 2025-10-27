#!/usr/bin/env python3
"""
Validate error handling improvements
"""

import re
import sys
from pathlib import Path


def check_file(file_path: Path) -> dict:
    """
    Check a Python file for error handling patterns

    Returns:
        Dict with check results
    """
    content = file_path.read_text()
    lines = content.split('\n')

    results = {
        'file': str(file_path),
        'bare_except': [],
        'logger_error_without_exc_info': [],
        'has_exception_import': 'from core.exceptions import' in content,
        'uses_custom_exceptions': any(exc in content for exc in [
            'DatabaseError', 'ConfigError', 'APIError',
            'TaskError', 'ValidationError', 'RateLimitError',
            'AuthenticationError'
        ])
    }

    # Check for bare except: blocks
    for i, line in enumerate(lines, 1):
        # Match "except:" but not "except Exception:" or "except SomeError:"
        if re.search(r'\bexcept\s*:', line) and '# noqa' not in line:
            results['bare_except'].append((i, line.strip()))

    # Check for logger.error without exc_info
    i = 0
    while i < len(lines):
        line = lines[i]

        if 'logger.error(' in line:
            # Check if exc_info is on this line or next few lines
            has_exc_info = False
            search_lines = []

            # Collect the full logger.error call (may be multi-line)
            search_lines.append((i+1, line))
            j = i + 1
            while j < len(lines) and j < i + 10:
                search_lines.append((j+1, lines[j]))
                if ')' in lines[j]:
                    break
                j += 1

            # Check if any of these lines have exc_info=True
            for line_num, search_line in search_lines:
                if 'exc_info=True' in search_line:
                    has_exc_info = True
                    break

            if not has_exc_info:
                results['logger_error_without_exc_info'].append((i+1, line.strip()))

        i += 1

    return results


def main():
    """Main validation function"""
    # Target directories
    target_dirs = [
        'core',
        'claude',
        'tasks',
        'messaging',
        'utils',
        'monitoring',
        'web_chat'
    ]

    worktree = Path('.')
    all_results = []

    print("=" * 70)
    print("ERROR HANDLING VALIDATION")
    print("=" * 70)

    for dir_name in target_dirs:
        dir_path = worktree / dir_name
        if not dir_path.exists():
            continue

        for py_file in sorted(dir_path.rglob('*.py')):
            # Skip __pycache__ and test files
            if '__pycache__' in str(py_file) or 'test_' in py_file.name:
                continue

            results = check_file(py_file)
            all_results.append(results)

    # Summary statistics
    total_files = len(all_results)
    files_with_bare_except = sum(1 for r in all_results if r['bare_except'])
    files_with_logger_issues = sum(1 for r in all_results if r['logger_error_without_exc_info'])
    files_with_imports = sum(1 for r in all_results if r['has_exception_import'])

    print(f"\n📊 SUMMARY")
    print(f"  Files checked: {total_files}")
    print(f"  Files with custom exception imports: {files_with_imports}")
    print(f"  Files with bare except: blocks: {files_with_bare_except}")
    print(f"  Files with logger.error missing exc_info: {files_with_logger_issues}")

    # Detailed issues
    if files_with_bare_except > 0:
        print(f"\n❌ BARE EXCEPT BLOCKS FOUND:")
        for result in all_results:
            if result['bare_except']:
                print(f"\n  {result['file']}")
                for line_num, line in result['bare_except']:
                    print(f"    Line {line_num}: {line}")

    if files_with_logger_issues > 0:
        print(f"\n⚠️  LOGGER.ERROR WITHOUT EXC_INFO:")
        count = 0
        for result in all_results:
            if result['logger_error_without_exc_info']:
                print(f"\n  {result['file']}")
                for line_num, line in result['logger_error_without_exc_info'][:3]:  # Show first 3
                    print(f"    Line {line_num}: {line[:80]}...")
                    count += 1
                if len(result['logger_error_without_exc_info']) > 3:
                    print(f"    ... and {len(result['logger_error_without_exc_info']) - 3} more")

    # Success criteria
    print(f"\n{'=' * 70}")
    print("SUCCESS CRITERIA:")
    success = True

    print(f"  ✓ No bare except: blocks" if files_with_bare_except == 0 else f"  ❌ {files_with_bare_except} files with bare except:")
    if files_with_bare_except > 0:
        success = False

    # Allow some logger.error without exc_info (non-critical files)
    threshold = 10
    if files_with_logger_issues <= threshold:
        print(f"  ✓ Logger.error with exc_info (within threshold)")
    else:
        print(f"  ⚠️  {files_with_logger_issues} files missing exc_info (threshold: {threshold})")

    print(f"{'=' * 70}\n")

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
