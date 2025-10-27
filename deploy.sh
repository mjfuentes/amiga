#!/bin/bash
# Unified deployment script for AMIGA frontend components
# Usage: ./deploy.sh [component]
# Components: chat, dashboard, all (default)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

deploy_chat() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📦 Building chat-frontend..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    cd monitoring/dashboard/chat-frontend
    npm run build

    echo ""
    echo "🚀 Deploying to static/chat/..."
    rm -rf ../../../static/chat/*
    cp -r build/* ../../../static/chat/

    cd "$SCRIPT_DIR"
    echo "✅ Chat frontend deployed"
}

deploy_dashboard() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📊 Checking dashboard templates..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Dashboard is server-side rendered, no build step needed
    # Just verify templates exist
    if [ -f "templates/dashboard.html" ]; then
        echo "✅ Dashboard templates present (server-side rendered, no build needed)"
    else
        echo "⚠️  Warning: dashboard.html not found"
        exit 1
    fi
}

restart_server() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔄 Restarting services..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Unload launchd services if running
    launchctl unload ~/Library/LaunchAgents/com.amiga.telegrambot.plist 2>/dev/null || true
    launchctl unload ~/Library/LaunchAgents/com.amiga.monitoring.plist 2>/dev/null || true

    # Kill existing services
    pkill -9 -f "python.*monitoring/server.py" 2>/dev/null || true
    pkill -9 -f "python.*core/main.py" 2>/dev/null || true
    sleep 2

    # Use venv python and set PYTHONPATH
    PYTHON="$SCRIPT_DIR/venv/bin/python"
    export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

    # Start monitoring server
    cd "$SCRIPT_DIR/monitoring"
    nohup "$PYTHON" server.py > ../logs/monitoring.log 2>&1 &
    MONITOR_PID=$!
    cd "$SCRIPT_DIR"
    sleep 3

    # Verify monitoring server
    if curl -s http://localhost:3000 > /dev/null 2>&1; then
        echo "✅ Monitoring server started (PID: $MONITOR_PID)"
    else
        echo "❌ Failed to start monitoring server"
        exit 1
    fi

    # Start bot
    cd "$SCRIPT_DIR"
    nohup env PYTHONPATH="$SCRIPT_DIR" "$PYTHON" core/main.py > logs/bot.log 2>&1 &
    BOT_PID=$!
    sleep 2

    # Verify bot
    if ps -p $BOT_PID > /dev/null 2>&1; then
        echo "✅ Telegram bot started (PID: $BOT_PID)"
    else
        echo "❌ Failed to start bot (check logs/bot.log)"
        tail -20 logs/bot.log
        exit 1
    fi

    echo ""
    echo "🌐 Access points:"
    echo "   Dashboard: http://localhost:3000"
    echo "   Chat:      http://localhost:3000/chat"
    echo ""
    echo "📝 Logs:"
    echo "   Bot:       tail -f logs/bot.log"
    echo "   Monitor:   tail -f logs/monitoring.log"
    echo ""
    echo "💡 Hard refresh browser: Cmd+Shift+R (Mac) or Ctrl+Shift+R (Linux/Windows)"
}

show_usage() {
    echo "Usage: ./deploy.sh [component]"
    echo ""
    echo "Components:"
    echo "  chat       - Deploy chat frontend only"
    echo "  dashboard  - Verify dashboard templates"
    echo "  all        - Deploy all components (default)"
    echo ""
    echo "Examples:"
    echo "  ./deploy.sh           # Deploy everything"
    echo "  ./deploy.sh chat      # Deploy chat only"
    echo "  ./deploy.sh dashboard # Verify dashboard"
}

# Main execution
COMPONENT="${1:-all}"

case "$COMPONENT" in
    chat)
        deploy_chat
        restart_server
        ;;
    dashboard)
        deploy_dashboard
        echo "✅ Dashboard verification complete"
        ;;
    all)
        deploy_chat
        deploy_dashboard
        restart_server
        ;;
    -h|--help)
        show_usage
        ;;
    *)
        echo "❌ Unknown component: $COMPONENT"
        echo ""
        show_usage
        exit 1
        ;;
esac

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨ Deployment complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
