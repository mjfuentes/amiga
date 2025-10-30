# AMIGA Remote Deployment - Quick Start

**Deploy AMIGA to production with a single command.**

## TL;DR

```bash
# 1. Setup (one-time)
bash scripts/deploy/00_prerequisites.sh

# 2. Configure
cp .env.deploy.example .env.deploy
nano .env.deploy  # Add tokens

# 3. Authenticate
doctl auth init --access-token YOUR_DO_TOKEN

# 4. Deploy
bash scripts/deploy/deploy_production.sh

# 🎉 Done! Access at https://your-domain.com
```

## What Gets Deployed

**Infrastructure:**
- ✅ DigitalOcean droplet (2GB RAM, 2 vCPU, $12/month)
- ✅ Ubuntu 22.04 LTS
- ✅ Public IP + DNS configuration
- ✅ SSL certificate (Let's Encrypt)

**Software Stack:**
- ✅ Python 3.12 + virtual environment
- ✅ Node.js 20 + Claude Code CLI
- ✅ Nginx reverse proxy
- ✅ React chat frontend (built + deployed)
- ✅ Flask + SocketIO server
- ✅ SQLite database

**Security:**
- ✅ UFW firewall (SSH, HTTP, HTTPS only)
- ✅ Fail2ban (brute force protection)
- ✅ SSL/TLS 1.2+ with strong ciphers
- ✅ Rate limiting (API + WebSocket)
- ✅ Security headers (HSTS, XSS, etc.)
- ✅ JWT authentication + bcrypt passwords

**Operations:**
- ✅ Systemd service (auto-restart)
- ✅ Log rotation (30 days)
- ✅ Automated backups (daily at 2 AM)
- ✅ Health check endpoint

## Prerequisites

### Required
- ✅ DigitalOcean account + API token
- ✅ Anthropic API key
- ✅ Domain name (or use IP address)

### Get DigitalOcean Token
1. Go to: https://cloud.digitalocean.com/account/api/tokens
2. Click "Generate New Token"
3. Name: "AMIGA Deployment"
4. Scopes: **Read + Write**
5. Copy token (starts with `dop_v1_...`)

### Get Anthropic API Key
1. Go to: https://console.anthropic.com/settings/keys
2. Create API key
3. Copy key (starts with `sk-ant-...`)

## Step-by-Step Deployment

### 1. Install Prerequisites
```bash
cd /Users/matifuentes/Workspace/amiga
bash scripts/deploy/00_prerequisites.sh
```

This installs:
- `doctl` (DigitalOcean CLI)
- `jq` (JSON processor)

### 2. Configure Deployment
```bash
# Copy template
cp .env.deploy.example .env.deploy

# Edit configuration
nano .env.deploy
```

**Minimum required configuration:**
```bash
# DigitalOcean API token (required)
DIGITALOCEAN_TOKEN=dop_v1_your_token_here

# Domain for your instance (required)
DOMAIN_NAME=amiga.yourdomain.com

# Anthropic API key (required)
ANTHROPIC_API_KEY=sk-ant-your_key_here
```

**Optional configuration** (defaults work fine):
```bash
DROPLET_NAME=amiga-production
DROPLET_REGION=nyc3              # New York datacenter
DROPLET_SIZE=s-2vcpu-2gb         # $12/month
REMOTE_USER=amiga
INSTALL_PATH=/opt/amiga
```

### 3. Authenticate CLI
```bash
doctl auth init --access-token YOUR_DIGITALOCEAN_TOKEN
```

### 4. Deploy
```bash
bash scripts/deploy/deploy_production.sh
```

**What happens:**
1. ✅ Creates droplet (~30 seconds)
2. ✅ Configures DNS (~1 minute)
3. ✅ Installs dependencies (~3 minutes)
4. ✅ Deploys application (~2 minutes)
5. ✅ Obtains SSL certificate (~2 minutes)

**Total time: ~10 minutes**

### 5. Create First User
```bash
# Replace with your domain
curl -X POST https://your-domain.com/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "admin",
    "email": "admin@example.com",
    "password": "your-secure-password"
  }'
```

### 6. Access Your Instance
Open: **https://your-domain.com**

## Post-Deployment

### SSH Access
```bash
# Stored in deployment state
ssh -i ~/.ssh/amiga_deploy_ed25519 amiga@YOUR_DROPLET_IP
```

### Service Management
```bash
# SSH to server first
ssh -i ~/.ssh/amiga_deploy_ed25519 amiga@YOUR_DROPLET_IP

# Check status
sudo systemctl status amiga

# View logs (real-time)
tail -f /opt/amiga/logs/monitoring.log

# Restart service
sudo systemctl restart amiga
```

### Update Deployment

After making code changes locally:
```bash
bash scripts/deploy/update_deployment.sh
```

This will:
1. Build frontend
2. Sync code
3. Update dependencies
4. Restart service
5. Verify health

**Time: ~2 minutes**

## Troubleshooting

### Deployment Failed?
Check which phase failed:
```bash
cat scripts/deploy/.state/completed_phases
```

Resume from failed phase:
```bash
bash scripts/deploy/01_provision_server.sh   # Phase 1
bash scripts/deploy/02_setup_server.sh       # Phase 2
bash scripts/deploy/03_deploy_app.sh         # Phase 3
```

### Can't Access Website?
```bash
# 1. Check service is running
ssh -i ~/.ssh/amiga_deploy_ed25519 amiga@YOUR_DROPLET_IP \
  "sudo systemctl status amiga"

# 2. Check nginx is running
ssh -i ~/.ssh/amiga_deploy_ed25519 amiga@YOUR_DROPLET_IP \
  "sudo systemctl status nginx"

# 3. Check firewall
ssh -i ~/.ssh/amiga_deploy_ed25519 amiga@YOUR_DROPLET_IP \
  "sudo ufw status"

# 4. Check DNS
dig +short your-domain.com
```

### SSL Certificate Issues?
```bash
# Wait 5-10 minutes for DNS propagation
# Then run manually:
ssh -i ~/.ssh/amiga_deploy_ed25519 amiga@YOUR_DROPLET_IP
sudo certbot --nginx -d your-domain.com
```

### Service Won't Start?
```bash
# Check logs
ssh -i ~/.ssh/amiga_deploy_ed25519 amiga@YOUR_DROPLET_IP \
  "tail -100 /opt/amiga/logs/monitoring.log"

# Common issues:
# - Missing .env file
# - Invalid API key
# - Port 3000 already in use
```

## Manual Configuration (If DNS Not in DigitalOcean)

If your domain is managed elsewhere:

1. **Get droplet IP:**
   ```bash
   cat scripts/deploy/.state/droplet_ip
   ```

2. **Add DNS record** in your DNS provider:
   - Type: `A`
   - Name: `amiga` (or `@` for root)
   - Value: `YOUR_DROPLET_IP`
   - TTL: `3600`

3. **Wait 5-10 minutes** for DNS propagation

4. **Obtain SSL manually:**
   ```bash
   ssh -i ~/.ssh/amiga_deploy_ed25519 amiga@YOUR_DROPLET_IP
   sudo certbot --nginx -d your-domain.com
   ```

## Cost Breakdown

**Infrastructure:**
- Droplet (s-2vcpu-2gb): **$12/month**
- Bandwidth: **Included** (2TB/month)
- Backups: **Free** (stored on droplet)
- SSL: **Free** (Let's Encrypt)

**API Usage:**
- Separate from infrastructure
- Set limits in `.env`: `DAILY_COST_LIMIT=100`

**Total: ~$12/month + API usage**

## Available Server Sizes

Edit `.env.deploy` → `DROPLET_SIZE`:

| Size | vCPU | RAM | Storage | Transfer | Cost/month |
|------|------|-----|---------|----------|------------|
| `s-1vcpu-1gb` | 1 | 1GB | 25GB | 1TB | $6 |
| `s-2vcpu-2gb` | 2 | 2GB | 50GB | 2TB | **$12** ⭐ |
| `s-2vcpu-4gb` | 2 | 4GB | 80GB | 3TB | $18 |
| `s-4vcpu-8gb` | 4 | 8GB | 160GB | 4TB | $36 |

## Available Regions

Edit `.env.deploy` → `DROPLET_REGION`:

| Region | Code | Location |
|--------|------|----------|
| **New York** | `nyc1`, `nyc3` | USA East |
| San Francisco | `sfo3` | USA West |
| Toronto | `tor1` | Canada |
| London | `lon1` | UK |
| Frankfurt | `fra1` | Germany |
| Amsterdam | `ams3` | Netherlands |
| Singapore | `sgp1` | Asia-Pacific |
| Bangalore | `blr1` | India |

## Backup & Recovery

### Automated Backups
- **Schedule**: Daily at 2 AM (server time)
- **Location**: `/opt/amiga/backups/`
- **Retention**: 30 days
- **Format**: Compressed SQLite backup

### Manual Backup
```bash
# SSH to server
ssh -i ~/.ssh/amiga_deploy_ed25519 amiga@YOUR_DROPLET_IP

# Trigger backup
/opt/amiga/scripts/backup_amiga.sh

# Download backup
exit
scp -i ~/.ssh/amiga_deploy_ed25519 \
  amiga@YOUR_DROPLET_IP:/opt/amiga/backups/*.db.gz \
  ./local-backup.db.gz
```

### Restore from Backup
```bash
# SSH to server
ssh -i ~/.ssh/amiga_deploy_ed25519 amiga@YOUR_DROPLET_IP

# Stop service
sudo systemctl stop amiga

# Restore (replace DATE)
gunzip -c /opt/amiga/backups/db_YYYYMMDD_HHMMSS.db.gz > \
  /opt/amiga/data/agentlab.db

# Start service
sudo systemctl start amiga
```

## Cleanup/Teardown

### Destroy Deployment
```bash
# Get droplet name from .env.deploy or use:
DROPLET_NAME=amiga-production

# Delete droplet
doctl compute droplet delete $DROPLET_NAME --force

# Optional: Delete SSH key
doctl compute ssh-key delete amiga-deploy-key --force

# Clean local state
rm -rf scripts/deploy/.state/
```

**This will permanently delete your server and all data!**

## Advanced Topics

See full documentation: `scripts/deploy/README.md`

Topics covered:
- Multiple environments (staging/production)
- Custom SSH keys
- Custom nginx configuration
- Monitoring and alerting
- Performance tuning
- Security hardening

## Support

**Deployment Issues:**
- Check: `scripts/deploy/.state/` for state files
- Logs: `tail -f logs/monitoring.log` (local)
- Server logs: `/opt/amiga/logs/monitoring.log` (remote)

**Application Issues:**
- Health check: `https://your-domain.com/health`
- Service status: `sudo systemctl status amiga`
- Restart: `sudo systemctl restart amiga`

---

**Full Documentation**: `scripts/deploy/README.md`

**Quick Commands:**
```bash
# Deploy
bash scripts/deploy/deploy_production.sh

# Update
bash scripts/deploy/update_deployment.sh

# SSH
ssh -i ~/.ssh/amiga_deploy_ed25519 amiga@$(cat scripts/deploy/.state/droplet_ip)

# Destroy
doctl compute droplet delete amiga-production --force
```
