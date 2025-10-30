# AMIGA Production Deployment

**Single-command deployment to DigitalOcean via terminal.**

## Quick Deploy

```bash
# 1. Setup (one-time)
bash scripts/deploy/00_prerequisites.sh
doctl auth init --access-token YOUR_TOKEN

# 2. Configure
cp .env.deploy.example .env.deploy
nano .env.deploy  # Required: DIGITALOCEAN_TOKEN, DOMAIN_NAME, ANTHROPIC_API_KEY

# 3. Deploy (10 minutes)
bash scripts/deploy/deploy_production.sh

# 4. Access
curl https://your-domain.com/health
```

## Configuration (.env.deploy)

**Required:**
```bash
DIGITALOCEAN_TOKEN=dop_v1_xxx        # Get: https://cloud.digitalocean.com/account/api/tokens
DOMAIN_NAME=amiga.yourdomain.com     # Your domain
ANTHROPIC_API_KEY=sk-ant-xxx         # Claude API key
```

**Optional (defaults work):**
```bash
DROPLET_SIZE=s-2vcpu-2gb            # $12/month
DROPLET_REGION=nyc3                 # NYC datacenter
REMOTE_USER=amiga
```

## Scripts

- `deploy_production.sh` - Full deployment (provision → setup → deploy)
- `update_deployment.sh` - Update code on existing deployment
- `check_deployment.sh` - Check deployment status/health

## Manual Phase Execution

```bash
bash scripts/deploy/01_provision_server.sh    # Create droplet + DNS
bash scripts/deploy/02_setup_server.sh        # Install dependencies + security
bash scripts/deploy/03_deploy_app.sh          # Deploy app + SSL
```

## Post-Deploy

```bash
# Create first user
curl -X POST https://your-domain.com/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","email":"admin@example.com","password":"your-password"}'

# SSH access
ssh -i ~/.ssh/amiga_deploy_ed25519 amiga@$(cat scripts/deploy/.state/droplet_ip)

# Service management
sudo systemctl status amiga
sudo systemctl restart amiga
tail -f /opt/amiga/logs/monitoring.log
```

## Teardown

```bash
doctl compute droplet delete amiga-production --force
rm -rf scripts/deploy/.state/
```

## What Gets Deployed

**Infrastructure:** DigitalOcean droplet (2GB RAM, 2 vCPU, $12/mo)
**Stack:** Python 3.12, Node.js 20, Nginx, SQLite
**Security:** UFW firewall, Fail2ban, Let's Encrypt SSL, JWT auth
**Operations:** Systemd service, automated backups (daily), log rotation

**Deployment time:** ~10 minutes
**Cost:** $12/month + API usage
