#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test QA workflow pattern matching for validation and complexity assessment."""

import re

# Sample QA agent responses
VALIDATION_REJECTED = """
## VALIDATION STATUS: REJECTED

**CRITICAL ISSUES:**
- Critical: Password hashing not implemented (using plaintext) in auth.py:45
- High: No SQL injection protection in login query at database.py:123

**MISSING COMPONENTS:**
- Password strength validation
- Rate limiting for login attempts

**RECOMMENDATION:**
Fix critical security issues before deployment.
"""

VALIDATION_APPROVED = """
## VALIDATION STATUS: APPROVED

**Implementation Quality Assessment:** HIGH

All requirements met. No critical issues found.
"""

COMPLEXITY_HIGH = """
**Complexity Assessment:** High

**Key Issues Found:**
1. Critical: Unnecessary Redis cache layer for 10-user app (auth_cache.py:12-89)
2. High: Over-abstraction with 5 middleware layers for simple routing (middleware/*.py)
3. Medium: Duplicate validation logic in 3 files

**Recommended Simplifications:**
1. Remove Redis - use in-memory dict for session cache
2. Consolidate middleware to single error handler
"""

COMPLEXITY_LOW = """
**Complexity Assessment:** Low

**Key Issues Found:**
1. Medium: Variable naming could be more descriptive in auth.py:23
2. Low: Missing docstring for helper function

**Recommended Simplifications:**
Minor improvements only. Code is appropriately simple.
"""


def parse_validation_status(result: str) -> str:
    """Parse validation status from task-completion-validator result."""
    approved_pattern = r'VALIDATION STATUS.*APPROVED'
    rejected_pattern = r'VALIDATION STATUS.*REJECTED'

    if re.search(approved_pattern, result, re.IGNORECASE):
        return "APPROVED"
    elif re.search(rejected_pattern, result, re.IGNORECASE):
        return "REJECTED"
    return "UNKNOWN"


def has_critical_issues(result: str) -> bool:
    """Check if validation result contains critical/high severity issues."""
    critical_pattern = r'CRITICAL ISSUES.*(Critical|High)'
    return bool(re.search(critical_pattern, result, re.IGNORECASE | re.DOTALL))


def parse_complexity(result: str) -> str:
    """Parse complexity assessment from code-quality-pragmatist result."""
    # More flexible pattern to handle bold/asterisks
    complexity_pattern = r'Complexity Assessment[:\*\s]+(Low|Medium|High)'
    match = re.search(complexity_pattern, result, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    # Debug: print first 100 chars if not found
    print(f"DEBUG: Pattern not found. First 100 chars: {result[:100]}")
    return "UNKNOWN"


def has_high_severity_issues(result: str) -> bool:
    """Check if complexity result contains Critical/High severity issues."""
    issue_pattern = r'Key Issues Found.*(Critical|High):'
    return bool(re.search(issue_pattern, result, re.IGNORECASE | re.DOTALL))


def test_validation_parsing():
    """Test validation status parsing."""
    print("=" * 60)
    print("Testing Validation Status Parsing")
    print("=" * 60)

    # Test REJECTED
    status = parse_validation_status(VALIDATION_REJECTED)
    has_issues = has_critical_issues(VALIDATION_REJECTED)
    print(f"✓ REJECTED case: status={status}, has_critical={has_issues}")
    assert status == "REJECTED" and has_issues

    # Test APPROVED
    status = parse_validation_status(VALIDATION_APPROVED)
    has_issues = has_critical_issues(VALIDATION_APPROVED)
    print(f"✓ APPROVED case: status={status}, has_critical={has_issues}")
    assert status == "APPROVED" and not has_issues

    print()


def test_complexity_parsing():
    """Test complexity assessment parsing."""
    print("=" * 60)
    print("Testing Complexity Assessment Parsing")
    print("=" * 60)

    # Test HIGH complexity with critical issues
    complexity = parse_complexity(COMPLEXITY_HIGH)
    has_issues = has_high_severity_issues(COMPLEXITY_HIGH)
    print(f"✓ HIGH complexity: complexity={complexity}, has_high_issues={has_issues}")
    assert complexity == "HIGH" and has_issues

    # Test LOW complexity with minor issues
    complexity = parse_complexity(COMPLEXITY_LOW)
    has_issues = has_high_severity_issues(COMPLEXITY_LOW)
    print(f"✓ LOW complexity: complexity={complexity}, has_high_issues={has_issues}")
    assert complexity == "LOW" and not has_issues

    print()


def test_workflow_decision():
    """Test workflow decision logic."""
    print("=" * 60)
    print("Testing Workflow Decision Logic")
    print("=" * 60)

    # Scenario 1: REJECTED validation
    status = parse_validation_status(VALIDATION_REJECTED)
    if status == "REJECTED":
        print("✓ Decision: Invoke code_agent to fix critical issues → Re-validate")

    # Scenario 2: APPROVED + HIGH complexity with critical issues
    status = parse_validation_status(VALIDATION_APPROVED)
    complexity = parse_complexity(COMPLEXITY_HIGH)
    has_issues = has_high_severity_issues(COMPLEXITY_HIGH)

    if status == "APPROVED" and complexity == "HIGH" and has_issues:
        print("✓ Decision: Invoke code_agent to simplify implementation")

    # Scenario 3: APPROVED + LOW complexity
    status = parse_validation_status(VALIDATION_APPROVED)
    complexity = parse_complexity(COMPLEXITY_LOW)
    has_issues = has_high_severity_issues(COMPLEXITY_LOW)

    if status == "APPROVED" and (complexity == "LOW" or not has_issues):
        print("✓ Decision: Proceed to git-merge (no fixes needed)")

    print()


if __name__ == "__main__":
    test_validation_parsing()
    test_complexity_parsing()
    test_workflow_decision()

    print("=" * 60)
    print("All tests passed! ✓")
    print("=" * 60)
