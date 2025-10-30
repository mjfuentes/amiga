#!/bin/bash
# Phase 0: Install deployment prerequisites
# Run locally to prepare for automated deployment

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📦 Installing Deployment Prerequisites"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Detect OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "🍎 macOS detected"

    # Install Homebrew if not present
    if ! command -v brew &> /dev/null; then
        echo "📦 Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi

    # Install doctl (DigitalOcean CLI)
    if ! command -v doctl &> /dev/null; then
        echo "📦 Installing doctl..."
        brew install doctl
    fi

elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "🐧 Linux detected"

    # Install doctl
    if ! command -v doctl &> /dev/null; then
        echo "📦 Installing doctl..."
        cd ~
        wget https://github.com/digitalocean/doctl/releases/download/v1.104.0/doctl-1.104.0-linux-amd64.tar.gz
        tar xf doctl-1.104.0-linux-amd64.tar.gz
        sudo mv doctl /usr/local/bin
        rm doctl-1.104.0-linux-amd64.tar.gz
    fi
fi

# Verify installations
echo ""
echo "✅ Checking installed tools..."
doctl version
jq --version 2>/dev/null || (echo "⚠️  jq not found, installing..." && brew install jq)

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔑 DigitalOcean API Token Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📝 Steps to get your DigitalOcean API token:"
echo "   1. Go to: https://cloud.digitalocean.com/account/api/tokens"
echo "   2. Click 'Generate New Token'"
echo "   3. Name: 'AMIGA Deployment'"
echo "   4. Scopes: Read + Write"
echo "   5. Copy the token (starts with 'dop_v1_...')"
echo ""
echo "💾 Save to .env.deploy:"
echo "   DIGITALOCEAN_TOKEN=your_token_here"
echo "   DOMAIN_NAME=amiga.yourdomain.com"
echo ""
echo "🔐 Initialize doctl:"
echo "   doctl auth init --access-token YOUR_TOKEN"
echo ""
echo "✅ Prerequisites installed!"
