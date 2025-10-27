#!/bin/bash
# Setup iTerm2 development environment with 4-pane layout
# Usage: ./scripts/setup_iterm_dev.sh

# Run the AppleScript to create the layout and run agentlab in each pane
osascript "$(dirname "$0")/setup_iterm_layout.applescript"

echo "iTerm2 layout created with 'agentlab' running in all 4 panes."
