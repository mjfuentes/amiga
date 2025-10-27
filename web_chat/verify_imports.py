#!/usr/bin/env python3
"""
Verify that all required imports work in the web_chat backend.

This script checks that:
1. All telegram_bot modules can be imported
2. All required dependencies are installed
3. Python version is 3.10+

Usage:
    source venv/bin/activate
    python verify_imports.py
"""

import sys
from pathlib import Path

# Color output
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RESET = '\033[0m'


def check_python_version():
    """Check Python version is 3.10+"""
    print("Checking Python version...")
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 10):
        print(f"{RED}✗ Python {version.major}.{version.minor} detected{RESET}")
        print(f"{YELLOW}  Python 3.10+ required (telegram_bot uses PEP 604 type unions){RESET}")
        return False
    print(f"{GREEN}✓ Python {version.major}.{version.minor}.{version.micro}{RESET}")
    return True


def check_import(module_name, package=None):
    """Try to import a module and return success status"""
    try:
        if package:
            __import__(package)
        else:
            __import__(module_name)
        print(f"{GREEN}✓ {module_name}{RESET}")
        return True
    except ImportError as e:
        print(f"{RED}✗ {module_name}: {e}{RESET}")
        return False


def main():
    print("=" * 60)
    print("Web Chat Backend Import Verification")
    print("=" * 60)
    print()

    # Check Python version first
    if not check_python_version():
        print()
        print(f"{RED}FAILED: Python version too old{RESET}")
        print()
        print("Fix: Recreate venv with Python 3.10+")
        print("  rm -rf venv")
        print("  python3 -m venv venv")
        print("  source venv/bin/activate")
        print("  pip install -r requirements.txt")
        sys.exit(1)

    print()
    print("Checking standard library imports...")
    success = True
    for module in ['os', 'sys', 'asyncio', 'logging', 'json', 'uuid', 'datetime', 'pathlib']:
        if not check_import(module):
            success = False

    print()
    print("Checking Flask dependencies...")
    for module in ['flask', 'flask_socketio', 'flask_cors', 'jwt', 'bcrypt', 'dotenv']:
        if not check_import(module):
            success = False

    print()
    print("Checking Anthropic dependencies...")
    if not check_import('anthropic'):
        success = False
        print(f"{YELLOW}  Install: pip install anthropic{RESET}")

    print()
    print("Checking other dependencies...")
    for module in ['pydantic', 'rich', 'aiofiles']:
        if not check_import(module):
            success = False

    print()
    print("Checking telegram_bot module imports...")
    # Add telegram_bot to path
    sys.path.insert(0, str(Path(__file__).parent.parent / "telegram_bot"))

    telegram_modules = [
        'session',
        'tasks',
        'agent_pool',
        'orchestrator',
        'claude_api'
    ]

    for module in telegram_modules:
        if not check_import(module):
            success = False

    print()
    print("Checking local web_chat modules...")
    for module in ['auth', 'api_routes']:
        if not check_import(module):
            success = False

    print()
    print("=" * 60)
    if success:
        print(f"{GREEN}SUCCESS: All imports working!{RESET}")
        print("You can now run: python server.py")
    else:
        print(f"{RED}FAILED: Some imports missing{RESET}")
        print()
        print("Fix: Install missing dependencies")
        print("  pip install -r requirements.txt")
    print("=" * 60)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
