#!/bin/bash
# Phase 2: Setup server environment
# Installs dependencies, creates user, configures firewall, sets up nginx

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Load configuration
source "$PROJECT_ROOT/.env.deploy"

# Load state
if [ ! -f "$SCRIPT_DIR/.state/droplet_ip" ]; then
    echo "❌ Droplet IP not found. Run 01_provision_server.sh first"
    exit 1
fi

DROPLET_IP=$(cat "$SCRIPT_DIR/.state/droplet_ip")
SSH_KEY_PATH=$(cat "$SCRIPT_DIR/.state/ssh_key_path")
REMOTE_USER="${REMOTE_USER:-amiga}"
INSTALL_PATH="${INSTALL_PATH:-/opt/amiga}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⚙️  Phase 2: Server Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   IP:   $DROPLET_IP"
echo "   User: $REMOTE_USER"
echo "   Path: $INSTALL_PATH"
echo ""

# Create setup script to run on remote server
cat > /tmp/amiga_setup.sh << 'SETUP_SCRIPT'
#!/bin/bash
set -e

REMOTE_USER="$1"
INSTALL_PATH="$2"
DOMAIN_NAME="$3"

echo "🔄 Updating system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq

echo "📦 Installing system dependencies..."
apt-get install -y -qq \
    python3.12 python3.12-venv python3-pip \
    git jq curl wget \
    nginx certbot python3-certbot-nginx \
    build-essential libssl-dev libffi-dev python3-dev \
    ufw fail2ban \
    sqlite3 \
    htop iotop nethogs \
    > /dev/null

echo "📦 Installing Node.js 20..."
curl -fsSL https://deb.nodesource.com/setup_20.x | bash - > /dev/null
apt-get install -y -qq nodejs > /dev/null

echo "📦 Installing Claude Code CLI..."
npm install -g @anthropic-ai/claude-code > /dev/null 2>&1

echo "👤 Creating user: $REMOTE_USER..."
if ! id "$REMOTE_USER" &>/dev/null; then
    useradd -m -s /bin/bash "$REMOTE_USER"
    usermod -aG sudo "$REMOTE_USER"
    echo "$REMOTE_USER ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/$REMOTE_USER"
fi

echo "📁 Creating installation directory..."
mkdir -p "$INSTALL_PATH"
chown -R "$REMOTE_USER:$REMOTE_USER" "$INSTALL_PATH"

echo "🔥 Configuring firewall (UFW)..."
ufw --force reset > /dev/null
ufw default deny incoming > /dev/null
ufw default allow outgoing > /dev/null
ufw allow 22/tcp comment 'SSH' > /dev/null
ufw allow 80/tcp comment 'HTTP' > /dev/null
ufw allow 443/tcp comment 'HTTPS' > /dev/null
ufw --force enable > /dev/null

echo "🛡️  Configuring fail2ban..."
systemctl enable fail2ban > /dev/null 2>&1
systemctl start fail2ban > /dev/null 2>&1

echo "🌐 Configuring nginx..."
# Remove default site
rm -f /etc/nginx/sites-enabled/default

# Create nginx config
cat > /etc/nginx/sites-available/amiga << 'NGINX_CONFIG'
# HTTP → HTTPS redirect (will be configured by certbot)
server {
    listen 80;
    server_name DOMAIN_PLACEHOLDER;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS server (will be configured by certbot)
server {
    listen 443 ssl http2;
    server_name DOMAIN_PLACEHOLDER;

    # SSL certificates (placeholder - will be set by certbot)
    ssl_certificate /etc/ssl/certs/ssl-cert-snakeoil.pem;
    ssl_certificate_key /etc/ssl/private/ssl-cert-snakeoil.key;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Rate limiting zones
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=ws:10m rate=5r/s;

    # WebSocket upgrade map
    map $http_upgrade $connection_upgrade {
        default upgrade;
        '' close;
    }

    # Static files (chat frontend)
    location /static/chat/ {
        alias /opt/amiga/static/chat/;
        expires 1d;
        add_header Cache-Control "public, immutable";
        try_files $uri $uri/ =404;
    }

    # WebSocket endpoint
    location /socket.io/ {
        limit_req zone=ws burst=10 nodelay;
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_buffering off;
    }

    # Server-Sent Events (SSE)
    location /api/stream/ {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        chunked_transfer_encoding on;
    }

    # API endpoints
    location /api/ {
        limit_req zone=api burst=20 nodelay;
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }

    # Health check endpoint
    location /health {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        access_log off;
    }

    # Main application
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }

    # Error pages
    error_page 502 503 504 /50x.html;
    location = /50x.html {
        root /usr/share/nginx/html;
    }
}
NGINX_CONFIG

# Replace domain placeholder
sed -i "s/DOMAIN_PLACEHOLDER/$DOMAIN_NAME/g" /etc/nginx/sites-available/amiga

# Enable site
ln -sf /etc/nginx/sites-available/amiga /etc/nginx/sites-enabled/

# Test nginx config
nginx -t

# Reload nginx
systemctl reload nginx

echo "📝 Configuring log rotation..."
cat > /etc/logrotate.d/amiga << 'LOGROTATE_CONFIG'
/opt/amiga/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 0644 amiga amiga
    sharedscripts
    postrotate
        systemctl reload amiga > /dev/null 2>&1 || true
    endscript
}
LOGROTATE_CONFIG

echo "✅ Server setup complete"
SETUP_SCRIPT

# Copy setup script to server and execute
echo "📤 Uploading setup script..."
scp -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no \
    /tmp/amiga_setup.sh root@"$DROPLET_IP":/tmp/

echo "🔧 Running setup script on server..."
ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no root@"$DROPLET_IP" \
    "bash /tmp/amiga_setup.sh '$REMOTE_USER' '$INSTALL_PATH' '$DOMAIN_NAME'"

# Copy SSH key to new user
echo "🔑 Configuring SSH access for $REMOTE_USER..."
ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no root@"$DROPLET_IP" << EOF
    mkdir -p /home/$REMOTE_USER/.ssh
    cp /root/.ssh/authorized_keys /home/$REMOTE_USER/.ssh/
    chown -R $REMOTE_USER:$REMOTE_USER /home/$REMOTE_USER/.ssh
    chmod 700 /home/$REMOTE_USER/.ssh
    chmod 600 /home/$REMOTE_USER/.ssh/authorized_keys
EOF

# Test SSH access with new user
echo "🔍 Testing SSH access as $REMOTE_USER..."
if ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no \
    "$REMOTE_USER@$DROPLET_IP" "echo 'SSH OK'" > /dev/null 2>&1; then
    echo "✅ SSH access confirmed"
else
    echo "❌ SSH access failed for $REMOTE_USER"
    exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨ Phase 2 Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   Server configured and ready"
echo "   User: $REMOTE_USER"
echo "   SSH:  ssh -i $SSH_KEY_PATH $REMOTE_USER@$DROPLET_IP"
echo ""
echo "📝 Next: Run 03_deploy_app.sh"
