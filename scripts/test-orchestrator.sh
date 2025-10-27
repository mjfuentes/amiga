#!/usr/bin/env bash
# Test orchestrator with proper env vars for agent tracking

set -e

TASK="${1:-Improve caching in test_caching.py}"

echo "Testing orchestrator with task: $TASK"
echo ""

export CLAUDE_AGENT_NAME="orchestrator"
export SESSION_ID="test-$(date +%s)"

echo "$TASK" | claude chat --model sonnet --permission-mode bypassPermissions

echo ""
echo "Session: $SESSION_ID"
echo "Check logs at: logs/sessions/$SESSION_ID/"
