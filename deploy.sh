#!/bin/bash
# Unified deployment script for AMIGA frontend components
# Usage: ./deploy.sh [component]
# Components: chat, dashboard, all (default)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Minimum required free space in GB
MIN_FREE_SPACE_GB=2

check_disk_space() {
    echo "🔍 Checking disk space..."

    # Get available space in GB (works on macOS and Linux)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS: df -g shows gigabytes
        AVAIL_GB=$(df -g "$SCRIPT_DIR" | tail -1 | awk '{print $4}')
    else
        # Linux: df -BG shows gigabytes
        AVAIL_GB=$(df -BG "$SCRIPT_DIR" | tail -1 | awk '{print $4}' | sed 's/G//')
    fi

    echo "   Available: ${AVAIL_GB}GB"
    echo "   Required:  ${MIN_FREE_SPACE_GB}GB"

    if [ "$AVAIL_GB" -lt "$MIN_FREE_SPACE_GB" ]; then
        echo ""
        echo "❌ INSUFFICIENT DISK SPACE"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "Only ${AVAIL_GB}GB available, need at least ${MIN_FREE_SPACE_GB}GB"
        echo ""
        echo "📝 Cleanup recommendations:"
        echo "   1. Clear npm cache:     npm cache clean --force"
        echo "   2. Remove old builds:   rm -rf monitoring/dashboard/chat-frontend/build"
        echo "   3. Clean Docker:        docker system prune -a"
        echo "   4. Clear system cache:  sudo periodic daily weekly monthly"
        echo "   5. Check logs:          du -sh logs/"
        echo ""
        echo "💾 Check space usage:"
        echo "   du -sh */ | sort -h"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        exit 1
    fi

    echo "✅ Sufficient disk space available"
    echo ""
}

deploy_chat() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📦 Building chat-frontend..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Only check disk space when building
    check_disk_space

    cd monitoring/dashboard/chat-frontend

    # Check if node_modules exists, if not, warn about disk space
    if [ ! -d "node_modules" ]; then
        echo "⚠️  node_modules not found - running npm install"
        echo "   This requires ~250MB disk space"
        npm install || {
            echo ""
            echo "❌ npm install failed"
            echo "   This is often caused by insufficient disk space"
            echo "   Check available space: df -h ."
            exit 1
        }
    fi

    npm run build || {
        echo ""
        echo "❌ Build failed"
        echo "   Common causes:"
        echo "   - Insufficient disk space"
        echo "   - Corrupted node_modules (try: rm -rf node_modules && npm install)"
        echo "   - Build cache issues (try: rm -rf build)"
        exit 1
    }

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
    echo "🔄 Restarting monitoring server..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Unload launchd service if running
    launchctl unload ~/Library/LaunchAgents/com.amiga.monitoring.plist 2>/dev/null || true

    # Kill existing monitoring server
    pkill -9 -f "python.*monitoring/server.py" 2>/dev/null || true
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

    echo ""
    echo "🌐 Access points:"
    echo "   Chat:      http://localhost:3000"
    echo "   Dashboard: http://localhost:3000/dashboard"
    echo ""
    echo "📝 Logs:"
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
