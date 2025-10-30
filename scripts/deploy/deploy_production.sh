#!/bin/bash
# Master deployment script for AMIGA
# Orchestrates full deployment: provision → setup → deploy

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

show_banner() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🚀 AMIGA Production Deployment"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
}

check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check for required tools
    local missing=0

    if ! command -v doctl &> /dev/null; then
        log_error "doctl not found"
        echo ""
        echo "Install doctl:"
        echo "  macOS:  brew install doctl"
        echo "  Linux:  wget https://github.com/digitalocean/doctl/releases/download/v1.104.0/doctl-1.104.0-linux-amd64.tar.gz"
        echo "          tar xf doctl-1.104.0-linux-amd64.tar.gz"
        echo "          sudo mv doctl /usr/local/bin"
        missing=1
    fi

    if ! command -v jq &> /dev/null; then
        log_error "jq not found"
        echo ""
        echo "Install jq:"
        echo "  macOS:  brew install jq"
        echo "  Linux:  sudo apt install jq"
        missing=1
    fi

    if ! command -v rsync &> /dev/null; then
        log_error "rsync not found"
        echo "  Install: brew install rsync (macOS) or sudo apt install rsync (Linux)"
        missing=1
    fi

    if [ $missing -eq 1 ]; then
        exit 1
    fi

    # Check for configuration file
    if [ ! -f "$PROJECT_ROOT/.env.deploy" ]; then
        log_error ".env.deploy not found"
        echo ""
        echo "Create .env.deploy from template:"
        echo "  cp .env.deploy.example .env.deploy"
        echo "  # Edit and configure your settings"
        exit 1
    fi

    # Load and validate configuration
    source "$PROJECT_ROOT/.env.deploy"

    if [ -z "$DIGITALOCEAN_TOKEN" ] || [ "$DIGITALOCEAN_TOKEN" = "your_digitalocean_token_here" ]; then
        log_error "DIGITALOCEAN_TOKEN not configured in .env.deploy"
        exit 1
    fi

    if [ -z "$DOMAIN_NAME" ] || [ "$DOMAIN_NAME" = "amiga.yourdomain.com" ]; then
        log_error "DOMAIN_NAME not configured in .env.deploy"
        exit 1
    fi

    if [ -z "$ANTHROPIC_API_KEY" ] || [ "$ANTHROPIC_API_KEY" = "your_anthropic_api_key_here" ]; then
        log_error "ANTHROPIC_API_KEY not configured in .env.deploy"
        exit 1
    fi

    # Check doctl authentication
    if ! doctl account get &> /dev/null; then
        log_error "doctl not authenticated"
        echo ""
        echo "Authenticate with:"
        echo "  doctl auth init --access-token \$DIGITALOCEAN_TOKEN"
        exit 1
    fi

    log_success "Prerequisites check passed"
    echo ""
}

show_deployment_plan() {
    source "$PROJECT_ROOT/.env.deploy"

    echo "📋 Deployment Configuration:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "   Domain:      $DOMAIN_NAME"
    echo "   Server:      ${DROPLET_NAME:-amiga-production}"
    echo "   Region:      ${DROPLET_REGION:-nyc3}"
    echo "   Size:        ${DROPLET_SIZE:-s-2vcpu-2gb}"
    echo "   User:        ${REMOTE_USER:-amiga}"
    echo "   Install Dir: ${INSTALL_PATH:-/opt/amiga}"
    echo ""

    # Estimate cost
    local monthly_cost="12"
    case "${DROPLET_SIZE:-s-2vcpu-2gb}" in
        s-1vcpu-1gb) monthly_cost="6" ;;
        s-2vcpu-2gb) monthly_cost="12" ;;
        s-2vcpu-4gb) monthly_cost="18" ;;
        s-4vcpu-8gb) monthly_cost="36" ;;
    esac

    echo "💰 Estimated Monthly Cost: \$${monthly_cost}/month"
    echo ""
}

confirm_deployment() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    read -p "🚀 Proceed with deployment? (yes/no): " -r
    echo ""

    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        log_info "Deployment cancelled"
        exit 0
    fi
}

run_phase() {
    local phase=$1
    local script=$2
    local description=$3

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📍 Phase $phase: $description"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    if [ ! -f "$SCRIPT_DIR/$script" ]; then
        log_error "Script not found: $script"
        exit 1
    fi

    chmod +x "$SCRIPT_DIR/$script"

    if bash "$SCRIPT_DIR/$script"; then
        log_success "Phase $phase complete"
        echo "$phase" >> "$SCRIPT_DIR/.state/completed_phases"
    else
        log_error "Phase $phase failed"
        echo ""
        echo "📝 Resume deployment from Phase $phase:"
        echo "   bash scripts/deploy/$script"
        exit 1
    fi
}

show_completion_summary() {
    source "$PROJECT_ROOT/.env.deploy"

    local droplet_ip=""
    if [ -f "$SCRIPT_DIR/.state/droplet_ip" ]; then
        droplet_ip=$(cat "$SCRIPT_DIR/.state/droplet_ip")
    fi

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🎉 DEPLOYMENT COMPLETE!"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "🌐 Your AMIGA instance is live!"
    echo ""
    echo "📍 Access Points:"
    echo "   URL:   https://$DOMAIN_NAME"
    echo "   IP:    $droplet_ip"
    echo ""
    echo "🔐 SSH Access:"
    if [ -f "$SCRIPT_DIR/.state/ssh_key_path" ]; then
        local ssh_key=$(cat "$SCRIPT_DIR/.state/ssh_key_path")
        echo "   ssh -i $ssh_key ${REMOTE_USER:-amiga}@$droplet_ip"
    fi
    echo ""
    echo "📝 Next Steps:"
    echo "   1. Visit: https://$DOMAIN_NAME"
    echo "   2. Create first user:"
    echo "      curl -X POST https://$DOMAIN_NAME/api/auth/register \\"
    echo "           -H 'Content-Type: application/json' \\"
    echo "           -d '{\"username\":\"admin\",\"email\":\"admin@example.com\",\"password\":\"your-password\"}'"
    echo ""
    echo "   3. Login and start chatting!"
    echo ""
    echo "📊 Management Commands:"
    echo "   Status:       sudo systemctl status amiga"
    echo "   Logs:         tail -f /opt/amiga/logs/monitoring.log"
    echo "   Restart:      sudo systemctl restart amiga"
    echo "   Update code:  bash scripts/deploy/update_deployment.sh"
    echo ""
    echo "💾 Database & Backups:"
    echo "   Database:     /opt/amiga/data/agentlab.db"
    echo "   Backups:      /opt/amiga/backups/ (daily at 2 AM)"
    echo ""
    echo "🔒 Security:"
    echo "   Firewall:     ufw status"
    echo "   SSL Cert:     sudo certbot certificates"
    echo "   Fail2ban:     sudo fail2ban-client status"
    echo ""
}

# Main execution
main() {
    show_banner
    check_prerequisites
    show_deployment_plan
    confirm_deployment

    # Create state directory
    mkdir -p "$SCRIPT_DIR/.state"
    rm -f "$SCRIPT_DIR/.state/completed_phases"

    # Record deployment start
    date > "$SCRIPT_DIR/.state/deployment_started"

    # Run deployment phases
    run_phase 1 "01_provision_server.sh" "Server Provisioning"
    run_phase 2 "02_setup_server.sh" "Server Configuration"
    run_phase 3 "03_deploy_app.sh" "Application Deployment"

    # Record deployment completion
    date > "$SCRIPT_DIR/.state/deployment_completed"

    show_completion_summary
}

# Handle script interruption
trap 'log_warning "Deployment interrupted. Resume with: bash $0"' INT TERM

# Run main
main "$@"
