#!/bin/bash
# Start Telegram bot (monitoring server runs independently via launchd)

# Get the script's directory and change to project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

# Activate virtual environment
source venv/bin/activate

# Start main bot
python telegram_bot/main.py
