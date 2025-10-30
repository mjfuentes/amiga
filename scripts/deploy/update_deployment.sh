#!/bin/bash
# Update existing AMIGA deployment
# Syncs code changes and restarts service

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Load configuration
if [ ! -f "$PROJECT_ROOT/.env.deploy" ]; then
    echo "❌ .env.deploy not found"
    exit 1
fi

source "$PROJECT_ROOT/.env.deploy"

# Load state
if [ ! -f "$SCRIPT_DIR/.state/droplet_ip" ]; then
    echo "❌ No deployment found. Run deploy_production.sh first"
    exit 1
fi

DROPLET_IP=$(cat "$SCRIPT_DIR/.state/droplet_ip")
SSH_KEY_PATH=$(cat "$SCRIPT_DIR/.state/ssh_key_path")
REMOTE_USER="${REMOTE_USER:-amiga}"
INSTALL_PATH="${INSTALL_PATH:-/opt/amiga}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔄 Updating AMIGA Deployment"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   Domain: $DOMAIN_NAME"
echo "   IP:     $DROPLET_IP"
echo ""

# Build frontend locally
echo "📦 Building frontend..."
cd "$PROJECT_ROOT/monitoring/dashboard/chat-frontend"
npm run build
cd "$PROJECT_ROOT"

# Sync code
echo "📤 Syncing code..."
rsync -avz --delete \
    --exclude 'venv/' \
    --exclude 'node_modules/' \
    --exclude 'monitoring/dashboard/chat-frontend/node_modules/' \
    --exclude 'monitoring/dashboard/chat-frontend/build/' \
    --exclude 'data/' \
    --exclude 'logs/' \
    --exclude '*.pyc' \
    --exclude '__pycache__/' \
    --exclude '.git/' \
    --exclude '.env' \
    --exclude '.env.deploy' \
    --exclude 'scripts/deploy/.state/' \
    -e "ssh -i $SSH_KEY_PATH -o StrictHostKeyChecking=no" \
    "$PROJECT_ROOT/" \
    "$REMOTE_USER@$DROPLET_IP:$INSTALL_PATH/"

# Deploy frontend
echo "📤 Deploying frontend..."
rsync -avz --delete \
    -e "ssh -i $SSH_KEY_PATH -o StrictHostKeyChecking=no" \
    "$PROJECT_ROOT/monitoring/dashboard/chat-frontend/build/" \
    "$REMOTE_USER@$DROPLET_IP:$INSTALL_PATH/static/chat/"

# Update Python dependencies
echo "📦 Updating dependencies..."
ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no "$REMOTE_USER@$DROPLET_IP" << 'REMOTE'
    cd /opt/amiga
    source venv/bin/activate
    pip install --upgrade pip > /dev/null
    pip install -r requirements.txt > /dev/null
REMOTE

# Restart service
echo "🔄 Restarting service..."
ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no "$REMOTE_USER@$DROPLET_IP" \
    "sudo systemctl restart amiga"

# Wait for health check
echo "🔍 Waiting for service..."
sleep 5

MAX_WAIT=30
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no "$REMOTE_USER@$DROPLET_IP" \
        "curl -s http://localhost:3000/health" > /dev/null 2>&1; then
        echo "✅ Service is healthy"
        break
    fi

    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "❌ Service failed health check"
        echo "📋 Check logs:"
        echo "   ssh -i $SSH_KEY_PATH $REMOTE_USER@$DROPLET_IP"
        echo "   tail -50 /opt/amiga/logs/monitoring.log"
        exit 1
    fi

    sleep 2
    WAITED=$((WAITED + 2))
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨ Update Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   URL: https://$DOMAIN_NAME"
echo ""
echo "💡 Clear browser cache: Cmd+Shift+R (Mac) or Ctrl+Shift+R (Linux/Windows)"
