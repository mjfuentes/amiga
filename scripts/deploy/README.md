# AMIGA Production Deployment Guide

Fully automated deployment scripts for deploying AMIGA to DigitalOcean with zero manual configuration.

## Prerequisites

### 1. DigitalOcean Account
- Sign up: https://www.digitalocean.com
- Get API token: https://cloud.digitalocean.com/account/api/tokens
  - Name: "AMIGA Deployment"
  - Scopes: Read + Write

### 2. Domain Name (Optional but Recommended)
- Register domain or use subdomain
- Will configure DNS automatically if domain is in DigitalOcean

### 3. Local Tools
Run the prerequisites installer:
```bash
bash scripts/deploy/00_prerequisites.sh
```

This installs:
- `doctl` (DigitalOcean CLI)
- `jq` (JSON processor)
- Other required tools

## Quick Start (One Command)

```bash
# 1. Copy configuration template
cp .env.deploy.example .env.deploy

# 2. Edit configuration
nano .env.deploy
# Fill in:
# - DIGITALOCEAN_TOKEN
# - DOMAIN_NAME
# - ANTHROPIC_API_KEY

# 3. Authenticate doctl
doctl auth init --access-token YOUR_DIGITALOCEAN_TOKEN

# 4. Run deployment
bash scripts/deploy/deploy_production.sh
```

That's it! The script will:
1. ✅ Provision DigitalOcean droplet (2GB RAM, 2vCPU)
2. ✅ Configure DNS (if domain in DigitalOcean)
3. ✅ Install all dependencies (Python, Node, nginx, etc.)
4. ✅ Setup firewall and security
5. ✅ Deploy application code
6. ✅ Build and deploy frontend
7. ✅ Create systemd service
8. ✅ Obtain SSL certificate (Let's Encrypt)
9. ✅ Configure automated backups

**Estimated time**: 10-15 minutes

## Configuration File (.env.deploy)

```bash
# Required
DIGITALOCEAN_TOKEN=dop_v1_xxxxx...
DOMAIN_NAME=amiga.yourdomain.com
ANTHROPIC_API_KEY=sk-ant-...

# Optional (defaults shown)
DROPLET_NAME=amiga-production
DROPLET_REGION=nyc3              # NYC datacenter
DROPLET_SIZE=s-2vcpu-2gb         # $12/month
DROPLET_IMAGE=ubuntu-22-04-x64

REMOTE_USER=amiga
INSTALL_PATH=/opt/amiga

# Application settings
DAILY_COST_LIMIT=100
MONTHLY_COST_LIMIT=1000
SESSION_TIMEOUT_MINUTES=60
LOG_LEVEL=INFO
```

## Deployment Phases

### Phase 1: Server Provisioning (`01_provision_server.sh`)
- Creates DigitalOcean droplet
- Generates SSH key
- Configures DNS (A record)
- Waits for SSH availability

**Can run standalone:**
```bash
bash scripts/deploy/01_provision_server.sh
```

### Phase 2: Server Setup (`02_setup_server.sh`)
- Installs system dependencies
- Creates application user
- Configures firewall (UFW)
- Installs nginx reverse proxy
- Sets up fail2ban
- Configures log rotation

**Can run standalone:**
```bash
bash scripts/deploy/02_setup_server.sh
```

### Phase 3: Application Deployment (`03_deploy_app.sh`)
- Builds React frontend
- Syncs code to server
- Creates Python virtual environment
- Installs dependencies
- Creates systemd service
- Obtains SSL certificate
- Sets up automated backups

**Can run standalone:**
```bash
bash scripts/deploy/03_deploy_app.sh
```

## Post-Deployment

### Access Your Instance
```bash
# Web interface
https://your-domain.com

# SSH access
ssh -i ~/.ssh/amiga_deploy_ed25519 amiga@your-droplet-ip
```

### Create First User
```bash
curl -X POST https://your-domain.com/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "admin",
    "email": "admin@example.com",
    "password": "secure-password-here"
  }'
```

### Service Management
```bash
# SSH to server
ssh -i ~/.ssh/amiga_deploy_ed25519 amiga@your-droplet-ip

# Service status
sudo systemctl status amiga

# View logs (real-time)
tail -f /opt/amiga/logs/monitoring.log

# Restart service
sudo systemctl restart amiga

# Stop service
sudo systemctl stop amiga

# Start service
sudo systemctl start amiga
```

### Updating Deployment

After making code changes locally:

```bash
bash scripts/deploy/update_deployment.sh
```

This will:
1. Build frontend locally
2. Sync code to server
3. Update dependencies
4. Restart service
5. Verify health

## Server Specifications

### Default Configuration ($12/month)
- **CPU**: 2 vCPU
- **RAM**: 2GB
- **Storage**: 50GB SSD
- **Transfer**: 2TB
- **Region**: New York (nyc3)

### Available Sizes
```bash
# Edit .env.deploy DROPLET_SIZE=

s-1vcpu-1gb     # $6/month  - Minimal
s-2vcpu-2gb     # $12/month - Recommended
s-2vcpu-4gb     # $18/month - High traffic
s-4vcpu-8gb     # $36/month - Heavy load
```

### Available Regions
```bash
# Edit .env.deploy DROPLET_REGION=

nyc1, nyc3      # New York
sfo3            # San Francisco
tor1            # Toronto
lon1            # London
fra1            # Frankfurt
ams3            # Amsterdam
sgp1            # Singapore
blr1            # Bangalore
```

## Security Features

### Firewall (UFW)
```bash
# Enabled by default, allows:
- Port 22 (SSH)
- Port 80 (HTTP)
- Port 443 (HTTPS)
```

### SSL/TLS
- Let's Encrypt certificates (auto-renewal)
- TLS 1.2 + TLS 1.3 only
- Strong cipher suites
- HSTS enabled

### Security Headers
- X-Frame-Options: SAMEORIGIN
- X-Content-Type-Options: nosniff
- X-XSS-Protection: 1; mode=block
- Strict-Transport-Security

### Rate Limiting
- API: 10 requests/second
- WebSocket: 5 connections/second

### Fail2ban
- Protects against brute force attacks
- Automatic IP banning

### Application Security
- JWT authentication
- Bcrypt password hashing
- Systemd security hardening

## Backup & Recovery

### Automated Backups
- **Schedule**: Daily at 2 AM (server time)
- **Location**: `/opt/amiga/backups/`
- **Format**: SQLite backup (compressed)
- **Retention**: 30 days

### Manual Backup
```bash
# SSH to server
ssh -i ~/.ssh/amiga_deploy_ed25519 amiga@your-droplet-ip

# Run backup script
/opt/amiga/scripts/backup_amiga.sh

# Download backup locally
scp -i ~/.ssh/amiga_deploy_ed25519 \
  amiga@your-droplet-ip:/opt/amiga/backups/db_latest.db.gz \
  ./local-backup.db.gz
```

### Restore from Backup
```bash
# SSH to server
ssh -i ~/.ssh/amiga_deploy_ed25519 amiga@your-droplet-ip

# Stop service
sudo systemctl stop amiga

# Restore database
gunzip -c /opt/amiga/backups/db_YYYYMMDD_HHMMSS.db.gz > /opt/amiga/data/agentlab.db

# Start service
sudo systemctl start amiga
```

## Monitoring

### Service Health
```bash
# Health check endpoint
curl https://your-domain.com/health

# Expected response: 200 OK
```

### Logs
```bash
# Application logs
tail -f /opt/amiga/logs/monitoring.log

# Nginx access logs
sudo tail -f /var/log/nginx/access.log

# Nginx error logs
sudo tail -f /var/log/nginx/error.log

# System logs
sudo journalctl -u amiga -f
```

### Resource Usage
```bash
# CPU/Memory
htop

# Disk usage
df -h

# Network traffic
nethogs

# I/O usage
iotop
```

## Troubleshooting

### Service Won't Start
```bash
# Check status and logs
sudo systemctl status amiga
tail -50 /opt/amiga/logs/monitoring.log

# Check for port conflicts
sudo lsof -i :3000

# Verify Python environment
cd /opt/amiga
source venv/bin/activate
python --version  # Should be 3.12+
pip list
```

### SSL Certificate Issues
```bash
# Check certificate status
sudo certbot certificates

# Renew manually
sudo certbot renew

# Force renewal
sudo certbot renew --force-renewal
```

### DNS Not Propagating
```bash
# Check DNS
dig +short your-domain.com @8.8.8.8

# If incorrect, wait 5-10 minutes
# Or configure manually in DigitalOcean DNS
```

### Can't Connect via SSH
```bash
# Check SSH key permissions
chmod 600 ~/.ssh/amiga_deploy_ed25519

# Connect with verbose output
ssh -v -i ~/.ssh/amiga_deploy_ed25519 amiga@your-droplet-ip

# Try root user
ssh -i ~/.ssh/amiga_deploy_ed25519 root@your-droplet-ip
```

### High Memory Usage
```bash
# Check processes
ps aux --sort=-%mem | head -20

# Upgrade to larger droplet
doctl compute droplet-action resize DROPLET_ID --size s-2vcpu-4gb
```

## Cleanup/Teardown

### Destroy Deployment
```bash
# Delete droplet
doctl compute droplet delete amiga-production --force

# Delete SSH key
doctl compute ssh-key delete amiga-deploy-key --force

# Delete DNS record
doctl compute domain records delete your-domain.com RECORD_ID --force

# Clean local state
rm -rf scripts/deploy/.state/
```

## Cost Breakdown

### Infrastructure
- **Droplet**: $12/month (s-2vcpu-2gb)
- **Bandwidth**: Included (2TB)
- **Backups**: Free (stored on droplet)

### Optional
- **Domain**: ~$12/year
- **SSL**: Free (Let's Encrypt)
- **Monitoring**: Free (DigitalOcean built-in)

### Claude API Usage
- Separate from infrastructure
- Set limits in `.env` (DAILY_COST_LIMIT, MONTHLY_COST_LIMIT)

**Total**: ~$12-15/month + API usage

## Advanced Configuration

### Custom Domain (Not in DigitalOcean)
If your domain is not managed by DigitalOcean:

1. Get droplet IP from deployment:
   ```bash
   cat scripts/deploy/.state/droplet_ip
   ```

2. Add A record in your DNS provider:
   - **Name**: amiga (or @ for root)
   - **Type**: A
   - **Value**: [DROPLET_IP]
   - **TTL**: 3600

3. Run SSL setup manually:
   ```bash
   ssh -i ~/.ssh/amiga_deploy_ed25519 amiga@your-droplet-ip
   sudo certbot --nginx -d your-domain.com
   ```

### Multiple Environments
Deploy separate instances for staging/production:

```bash
# Staging
cp .env.deploy .env.deploy.staging
# Edit: DROPLET_NAME=amiga-staging, DOMAIN_NAME=staging.example.com

# Production
cp .env.deploy .env.deploy.production
# Edit: DROPLET_NAME=amiga-production, DOMAIN_NAME=amiga.example.com

# Deploy each
ENV_FILE=.env.deploy.staging bash scripts/deploy/deploy_production.sh
ENV_FILE=.env.deploy.production bash scripts/deploy/deploy_production.sh
```

### Custom SSH Key
```bash
# Generate your own
ssh-keygen -t ed25519 -f ~/.ssh/my_custom_key -C "custom-key"

# Update .env.deploy
SSH_KEY_PATH=~/.ssh/my_custom_key
```

## Support

### Logs for Debugging
When reporting issues, include:

```bash
# Deployment logs
cat scripts/deploy/.state/deployment_started
cat scripts/deploy/.state/deployment_completed

# Application logs
ssh -i ~/.ssh/amiga_deploy_ed25519 amiga@your-droplet-ip \
  "tail -100 /opt/amiga/logs/monitoring.log"

# Service status
ssh -i ~/.ssh/amiga_deploy_ed25519 amiga@your-droplet-ip \
  "sudo systemctl status amiga"
```

### Common Issues
- **Port 3000 in use**: Check for conflicting services
- **Out of memory**: Upgrade droplet size
- **SSL errors**: Wait for DNS propagation (5-10 min)
- **Build failures**: Check disk space (need 2GB free)

---

**Last Updated**: 2025-10-30
**Maintainer**: AMIGA Team
