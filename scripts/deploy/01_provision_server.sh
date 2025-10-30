#!/bin/bash
# Phase 1: Provision DigitalOcean droplet
# Creates server, configures DNS, sets up SSH access

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Load configuration
if [ ! -f "$PROJECT_ROOT/.env.deploy" ]; then
    echo "❌ .env.deploy not found"
    echo "   Copy .env.deploy.example to .env.deploy and configure"
    exit 1
fi

source "$PROJECT_ROOT/.env.deploy"

# Validate required variables
if [ -z "$DIGITALOCEAN_TOKEN" ] || [ "$DIGITALOCEAN_TOKEN" = "your_digitalocean_token_here" ]; then
    echo "❌ DIGITALOCEAN_TOKEN not configured in .env.deploy"
    exit 1
fi

if [ -z "$DOMAIN_NAME" ] || [ "$DOMAIN_NAME" = "amiga.yourdomain.com" ]; then
    echo "❌ DOMAIN_NAME not configured in .env.deploy"
    exit 1
fi

# Set defaults
DROPLET_NAME="${DROPLET_NAME:-amiga-production}"
DROPLET_REGION="${DROPLET_REGION:-nyc3}"
DROPLET_SIZE="${DROPLET_SIZE:-s-2vcpu-2gb}"
DROPLET_IMAGE="${DROPLET_IMAGE:-ubuntu-22-04-x64}"
SSH_KEY_NAME="${SSH_KEY_NAME:-amiga-deploy-key}"
SSH_KEY_PATH="${SSH_KEY_PATH:-$HOME/.ssh/amiga_deploy_ed25519}"

# Authenticate doctl
export DIGITALOCEAN_ACCESS_TOKEN="$DIGITALOCEAN_TOKEN"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 Phase 1: Server Provisioning"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   Domain:  $DOMAIN_NAME"
echo "   Name:    $DROPLET_NAME"
echo "   Region:  $DROPLET_REGION"
echo "   Size:    $DROPLET_SIZE"
echo ""

# Step 1: Create SSH key if doesn't exist
if [ ! -f "$SSH_KEY_PATH" ]; then
    echo "🔑 Creating SSH key..."
    ssh-keygen -t ed25519 -f "$SSH_KEY_PATH" -N "" -C "amiga-deploy"
    echo "✅ SSH key created: $SSH_KEY_PATH"
else
    echo "✅ SSH key exists: $SSH_KEY_PATH"
fi

# Step 2: Upload SSH key to DigitalOcean if not already uploaded
SSH_KEY_FINGERPRINT=$(ssh-keygen -lf "$SSH_KEY_PATH.pub" | awk '{print $2}')
if doctl compute ssh-key list --format Fingerprint --no-header | grep -q "$SSH_KEY_FINGERPRINT"; then
    echo "✅ SSH key already uploaded to DigitalOcean"
    SSH_KEY_ID=$(doctl compute ssh-key list --format ID,Fingerprint --no-header | grep "$SSH_KEY_FINGERPRINT" | awk '{print $1}')
else
    echo "📤 Uploading SSH key to DigitalOcean..."
    SSH_KEY_ID=$(doctl compute ssh-key import "$SSH_KEY_NAME" \
        --public-key-file "$SSH_KEY_PATH.pub" \
        --format ID --no-header)
    echo "✅ SSH key uploaded (ID: $SSH_KEY_ID)"
fi

# Step 3: Check if droplet already exists
if doctl compute droplet list --format Name --no-header | grep -q "^${DROPLET_NAME}$"; then
    echo "⚠️  Droplet '$DROPLET_NAME' already exists"
    DROPLET_IP=$(doctl compute droplet list --format Name,PublicIPv4 --no-header | grep "^${DROPLET_NAME}" | awk '{print $2}')
    echo "   IP: $DROPLET_IP"

    read -p "Delete and recreate? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🗑️  Deleting existing droplet..."
        doctl compute droplet delete "$DROPLET_NAME" --force
        sleep 5
    else
        echo "✅ Using existing droplet: $DROPLET_IP"
        # Save to state file
        mkdir -p "$PROJECT_ROOT/scripts/deploy/.state"
        echo "$DROPLET_IP" > "$PROJECT_ROOT/scripts/deploy/.state/droplet_ip"
        echo "✅ Droplet IP saved to .state/droplet_ip"
        exit 0
    fi
fi

# Step 4: Create droplet
echo "🖥️  Creating droplet..."
DROPLET_ID=$(doctl compute droplet create "$DROPLET_NAME" \
    --image "$DROPLET_IMAGE" \
    --size "$DROPLET_SIZE" \
    --region "$DROPLET_REGION" \
    --ssh-keys "$SSH_KEY_ID" \
    --enable-monitoring \
    --tag-names "amiga,production" \
    --format ID --no-header \
    --wait)

echo "✅ Droplet created (ID: $DROPLET_ID)"

# Step 5: Get droplet IP
echo "🔍 Retrieving droplet IP..."
sleep 10  # Wait for IP assignment
DROPLET_IP=$(doctl compute droplet get "$DROPLET_ID" --format PublicIPv4 --no-header)

if [ -z "$DROPLET_IP" ]; then
    echo "❌ Failed to get droplet IP"
    exit 1
fi

echo "✅ Droplet IP: $DROPLET_IP"

# Step 6: Save state
mkdir -p "$PROJECT_ROOT/scripts/deploy/.state"
echo "$DROPLET_IP" > "$PROJECT_ROOT/scripts/deploy/.state/droplet_ip"
echo "$DROPLET_ID" > "$PROJECT_ROOT/scripts/deploy/.state/droplet_id"
echo "$SSH_KEY_PATH" > "$PROJECT_ROOT/scripts/deploy/.state/ssh_key_path"

# Step 7: Configure DNS
echo ""
echo "🌐 Configuring DNS..."

# Extract domain parts (e.g., amiga.example.com → example.com, amiga)
DOMAIN_BASE=$(echo "$DOMAIN_NAME" | awk -F. '{print $(NF-1)"."$NF}')
SUBDOMAIN=$(echo "$DOMAIN_NAME" | sed "s/\.$DOMAIN_BASE//")

# Check if domain is managed by DigitalOcean
if ! doctl compute domain list --format Domain --no-header | grep -q "^${DOMAIN_BASE}$"; then
    echo "⚠️  Domain '$DOMAIN_BASE' not found in DigitalOcean DNS"
    echo "   Add domain: doctl compute domain create $DOMAIN_BASE"
    echo ""
    echo "📝 Manual DNS configuration required:"
    echo "   Create A record:"
    echo "   Name:  $SUBDOMAIN"
    echo "   Type:  A"
    echo "   Value: $DROPLET_IP"
    echo "   TTL:   3600"
else
    # Create/update A record
    echo "📝 Creating A record: $DOMAIN_NAME → $DROPLET_IP"

    # Delete existing record if present
    EXISTING_RECORD=$(doctl compute domain records list "$DOMAIN_BASE" \
        --format ID,Name,Type --no-header | grep "$SUBDOMAIN.*A" | awk '{print $1}' || true)

    if [ -n "$EXISTING_RECORD" ]; then
        echo "   Deleting existing record..."
        doctl compute domain records delete "$DOMAIN_BASE" "$EXISTING_RECORD" --force
    fi

    # Create new record
    doctl compute domain records create "$DOMAIN_BASE" \
        --record-type A \
        --record-name "$SUBDOMAIN" \
        --record-data "$DROPLET_IP" \
        --record-ttl 3600 > /dev/null

    echo "✅ DNS record created"
fi

# Step 8: Wait for SSH to be available
echo ""
echo "🔍 Waiting for SSH to be available..."
MAX_WAIT=120
WAITED=0
while ! ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
    root@"$DROPLET_IP" "exit" 2>/dev/null; do
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "❌ SSH not available after ${MAX_WAIT}s"
        exit 1
    fi
    echo "   Waiting... (${WAITED}s)"
    sleep 5
    WAITED=$((WAITED + 5))
done

echo "✅ SSH is available"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨ Phase 1 Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   Droplet IP:  $DROPLET_IP"
echo "   Domain:      $DOMAIN_NAME"
echo "   SSH:         ssh -i $SSH_KEY_PATH root@$DROPLET_IP"
echo ""
echo "📝 Next: Run 02_setup_server.sh"
