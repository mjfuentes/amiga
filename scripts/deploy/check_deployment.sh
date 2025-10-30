#!/bin/bash
# Check deployment status and health

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 AMIGA Deployment Status"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if deployed
if [ ! -f "$PROJECT_ROOT/.env.deploy" ]; then
    echo -e "${RED}❌ Not configured${NC}"
    echo "   Run: cp .env.deploy.example .env.deploy"
    exit 1
fi

source "$PROJECT_ROOT/.env.deploy"

if [ ! -f "$SCRIPT_DIR/.state/droplet_ip" ]; then
    echo -e "${YELLOW}⚠️  Not deployed yet${NC}"
    echo "   Run: bash scripts/deploy/deploy_production.sh"
    exit 0
fi

# Load state
DROPLET_IP=$(cat "$SCRIPT_DIR/.state/droplet_ip")
SSH_KEY_PATH=$(cat "$SCRIPT_DIR/.state/ssh_key_path")
REMOTE_USER="${REMOTE_USER:-amiga}"

echo "📍 Deployment Information:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   Domain:  $DOMAIN_NAME"
echo "   IP:      $DROPLET_IP"
echo "   User:    $REMOTE_USER"
echo ""

# Check if droplet exists
if ! doctl compute droplet list --format Name --no-header | grep -q "^${DROPLET_NAME:-amiga-production}$"; then
    echo -e "${RED}❌ Droplet not found${NC}"
    echo "   The droplet may have been deleted"
    exit 1
fi

echo "🌐 Network Status:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check DNS
RESOLVED_IP=$(dig +short "$DOMAIN_NAME" @8.8.8.8 | tail -1)
if [ "$RESOLVED_IP" = "$DROPLET_IP" ]; then
    echo -e "   DNS:     ${GREEN}✅ Resolved${NC} ($RESOLVED_IP)"
else
    echo -e "   DNS:     ${YELLOW}⚠️  Mismatch${NC} (expected: $DROPLET_IP, got: $RESOLVED_IP)"
fi

# Check HTTP
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://$DOMAIN_NAME/health" 2>/dev/null || echo "000")
if [ "$HTTP_STATUS" = "200" ]; then
    echo -e "   HTTP:    ${GREEN}✅ Online${NC} (200 OK)"
elif [ "$HTTP_STATUS" = "301" ] || [ "$HTTP_STATUS" = "302" ]; then
    echo -e "   HTTP:    ${GREEN}✅ Redirecting${NC} ($HTTP_STATUS)"
else
    echo -e "   HTTP:    ${RED}❌ Offline${NC} ($HTTP_STATUS)"
fi

# Check HTTPS
HTTPS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://$DOMAIN_NAME/health" 2>/dev/null || echo "000")
if [ "$HTTPS_STATUS" = "200" ]; then
    echo -e "   HTTPS:   ${GREEN}✅ Secure${NC} (200 OK)"
else
    echo -e "   HTTPS:   ${YELLOW}⚠️  Not available${NC} ($HTTPS_STATUS)"
fi

# Check SSH
if ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
    "$REMOTE_USER@$DROPLET_IP" "exit" 2>/dev/null; then
    echo -e "   SSH:     ${GREEN}✅ Connected${NC}"
else
    echo -e "   SSH:     ${RED}❌ Failed${NC}"
fi

echo ""

# Check service status
echo "⚙️  Service Status:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

SERVICE_STATUS=$(ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no \
    "$REMOTE_USER@$DROPLET_IP" "systemctl is-active amiga" 2>/dev/null || echo "unknown")

if [ "$SERVICE_STATUS" = "active" ]; then
    echo -e "   Service: ${GREEN}✅ Running${NC}"
elif [ "$SERVICE_STATUS" = "failed" ]; then
    echo -e "   Service: ${RED}❌ Failed${NC}"
else
    echo -e "   Service: ${YELLOW}⚠️  $SERVICE_STATUS${NC}"
fi

# Get service uptime
UPTIME=$(ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no \
    "$REMOTE_USER@$DROPLET_IP" \
    "systemctl show amiga -p ActiveEnterTimestamp --value" 2>/dev/null || echo "unknown")

if [ "$UPTIME" != "unknown" ] && [ -n "$UPTIME" ]; then
    echo "   Started: $UPTIME"
fi

# Check system resources
echo ""
echo "💻 System Resources:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no \
    "$REMOTE_USER@$DROPLET_IP" << 'REMOTE_CHECK'
    # CPU load
    LOAD=$(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | tr -d ',')
    echo "   CPU:     $LOAD (1m avg)"

    # Memory
    MEM=$(free -h | awk '/^Mem:/ {printf "%s / %s (%.0f%%)", $3, $2, ($3/$2)*100}')
    echo "   Memory:  $MEM"

    # Disk
    DISK=$(df -h /opt/amiga | awk 'NR==2 {printf "%s / %s (%s)", $3, $2, $5}')
    echo "   Disk:    $DISK"
REMOTE_CHECK

# Check recent errors
echo ""
echo "📋 Recent Activity:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

ERROR_COUNT=$(ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no \
    "$REMOTE_USER@$DROPLET_IP" \
    "grep -c ERROR /opt/amiga/logs/monitoring.log 2>/dev/null || echo 0" || echo 0)

if [ "$ERROR_COUNT" -gt 0 ]; then
    echo -e "   Errors:  ${YELLOW}$ERROR_COUNT found${NC}"
    echo ""
    echo "   Last 5 errors:"
    ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no \
        "$REMOTE_USER@$DROPLET_IP" \
        "grep ERROR /opt/amiga/logs/monitoring.log | tail -5" 2>/dev/null || true
else
    echo -e "   Errors:  ${GREEN}None${NC}"
fi

# Check SSL certificate
if [ "$HTTPS_STATUS" = "200" ]; then
    echo ""
    echo "🔒 SSL Certificate:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    CERT_INFO=$(ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no \
        "$REMOTE_USER@$DROPLET_IP" \
        "sudo certbot certificates 2>/dev/null | grep -A5 '$DOMAIN_NAME'" || echo "")

    if [ -n "$CERT_INFO" ]; then
        EXPIRY=$(echo "$CERT_INFO" | grep "Expiry Date:" | cut -d: -f2- | xargs)
        echo "   Expires: $EXPIRY"

        # Check if expires soon (30 days)
        EXPIRY_EPOCH=$(date -d "$EXPIRY" +%s 2>/dev/null || date -j -f "%b %d %H:%M:%S %Y %Z" "$EXPIRY" +%s 2>/dev/null || echo 0)
        NOW_EPOCH=$(date +%s)
        DAYS_LEFT=$(( ($EXPIRY_EPOCH - $NOW_EPOCH) / 86400 ))

        if [ "$DAYS_LEFT" -lt 30 ]; then
            echo -e "   Status:  ${YELLOW}⚠️  Expires in $DAYS_LEFT days${NC}"
        else
            echo -e "   Status:  ${GREEN}✅ Valid ($DAYS_LEFT days left)${NC}"
        fi
    fi
fi

# Check backups
echo ""
echo "💾 Backups:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

BACKUP_COUNT=$(ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no \
    "$REMOTE_USER@$DROPLET_IP" \
    "ls -1 /opt/amiga/backups/*.db.gz 2>/dev/null | wc -l" || echo 0)

if [ "$BACKUP_COUNT" -gt 0 ]; then
    LATEST_BACKUP=$(ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no \
        "$REMOTE_USER@$DROPLET_IP" \
        "ls -t /opt/amiga/backups/*.db.gz 2>/dev/null | head -1 | xargs basename" || echo "none")

    echo "   Total:   $BACKUP_COUNT backups"
    echo "   Latest:  $LATEST_BACKUP"
else
    echo -e "   ${YELLOW}⚠️  No backups found${NC}"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📝 Quick Commands:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   Visit:      https://$DOMAIN_NAME"
echo "   SSH:        ssh -i $SSH_KEY_PATH $REMOTE_USER@$DROPLET_IP"
echo "   Logs:       ssh -i $SSH_KEY_PATH $REMOTE_USER@$DROPLET_IP 'tail -f /opt/amiga/logs/monitoring.log'"
echo "   Restart:    ssh -i $SSH_KEY_PATH $REMOTE_USER@$DROPLET_IP 'sudo systemctl restart amiga'"
echo "   Update:     bash scripts/deploy/update_deployment.sh"
echo ""
