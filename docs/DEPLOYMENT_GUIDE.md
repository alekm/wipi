# WiPi Deployment & Portability Guide

This guide covers deploying WiPi to different environments, including running the controller on a Raspberry Pi.

## Table of Contents
- [Current Deployment (x86 Server)](#current-deployment-x86-server)
- [Moving to Raspberry Pi Controller](#moving-to-raspberry-pi-controller)
- [Dual-Role Pi (Controller + Agent)](#dual-role-pi-controller--agent)
- [Backup & Restore](#backup--restore)
- [Migration Checklist](#migration-checklist)

---

## Current Deployment (x86 Server)

**Current Setup:**
- Controller & UI: Running on `util` server (x86_64)
- Database: SQLite at `/opt/stacks/wipi/data/wipi.db`
- Agents: Running on Raspberry Pis (ARM64)

**Architecture:**
```
┌──────────────────────────────────┐
│  util (x86 server)               │
│  ┌────────────┐  ┌────────────┐ │
│  │ Controller │  │     UI     │ │
│  │  :8000     │  │   :8080    │ │
│  └────────────┘  └────────────┘ │
│         │                        │
│    ┌────┴────┐                   │
│    │ SQLite  │                   │
│    │   DB    │                   │
│    └─────────┘                   │
└─────────────┬────────────────────┘
              │
      ┌───────┴────────┬─────────────┬─────────────┐
      │                │             │             │
┌─────▼────┐  ┌────────▼───┐  ┌─────▼────┐  ┌─────▼────┐
│ wipi-01  │  │  wipi-02   │  │ wipi-03  │  │ wipi-04  │
│  Agent   │  │   Agent    │  │  Agent   │  │  Agent   │
│  :8080   │  │   :8080    │  │  :8080   │  │  :8080   │
└──────────┘  └────────────┘  └──────────┘  └──────────┘
```

---

## Moving to Raspberry Pi Controller

### Why Run Controller on Raspberry Pi?

**Advantages:**
- ✅ Self-contained system (no separate server needed)
- ✅ Lower power consumption
- ✅ Portable (take entire lab in a bag)
- ✅ Cheaper than dedicated server
- ✅ Can be co-located with test environment

**Considerations:**
- ⚠️ Pi 5 recommended (8GB RAM model for production)
- ⚠️ Performance: Controller handles orchestration, not heavy compute
- ⚠️ Storage: Use USB SSD for database (not SD card)
- ⚠️ Network: Wired Ethernet recommended (more reliable than Wi-Fi)

### Hardware Requirements

**Minimum (Development/Testing):**
- Raspberry Pi 4B 4GB
- 32GB SD card (Class 10 or better)
- Wired Ethernet connection

**Recommended (Production):**
- Raspberry Pi 5 8GB
- USB 3.0 SSD (128GB+) for database
- 32GB SD card (boot only)
- Wired Gigabit Ethernet
- Cooling (heatsink or fan)

### Installation Steps

#### 1. Prepare Raspberry Pi

```bash
# Flash Raspberry Pi OS Lite (64-bit) to SD card
# Enable SSH during flash (Raspberry Pi Imager)

# SSH into Pi
ssh admin@<pi-ip>

# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Reboot to apply group membership
sudo reboot
```

#### 2. Mount USB SSD (Optional but Recommended)

```bash
# Plug in USB SSD
# Find device name
lsblk

# Example output:
# sda      8:0    0 238.5G  0 disk
# └─sda1   8:1    0 238.5G  0 part

# Format as ext4
sudo mkfs.ext4 /dev/sda1

# Create mount point
sudo mkdir -p /mnt/wipi-data

# Get UUID
sudo blkid /dev/sda1
# Example: UUID="abc123..."

# Add to /etc/fstab for auto-mount
echo "UUID=abc123... /mnt/wipi-data ext4 defaults 0 2" | sudo tee -a /etc/fstab

# Mount
sudo mount -a

# Verify
df -h | grep wipi-data

# Set ownership
sudo chown -R $USER:$USER /mnt/wipi-data
```

#### 3. Deploy WiPi to Pi

**Option A: Fresh Deployment**

```bash
# Create project directory
mkdir -p /mnt/wipi-data/wipi
cd /mnt/wipi-data/wipi

# Clone/copy WiPi code
# (If using git)
git clone <wipi-repo-url> .

# (Or copy from USB/network)
scp -r /opt/stacks/wipi/* admin@<pi-ip>:/mnt/wipi-data/wipi/

# Create data directory
mkdir -p data

# Set password (optional)
echo "WIPI_ADMIN_PASSWORD_HASH=8f4179b458b4e4622c32089b025ff4e4b531137642dfdf5143b5f29af3c32e84" > .env

# Build and start
docker compose up -d

# Check logs
docker compose logs -f
```

**Option B: Migrate Existing Deployment (with data)**

See [Backup & Restore](#backup--restore) section below.

#### 4. Configure Agent Pi Endpoints

After controller is running on Pi, update agents to point to new controller URL:

```bash
# On each agent Pi, update config:
sudo nano /etc/wipi/agent_config.yaml

# Change:
controller_url: "http://172.16.254.X:8000"  # New Pi controller IP

# Restart agent
sudo systemctl restart wipi-agent
```

---

## Dual-Role Pi (Controller + Agent)

Run both controller and agent on the same Raspberry Pi.

### Architecture

```
┌──────────────────────────────────────────────┐
│  Raspberry Pi (Dual Role)                    │
│                                              │
│  ┌────────────┐  ┌────────────┐            │
│  │ Controller │  │     UI     │            │
│  │  :8000     │  │   :8080    │  (Docker)  │
│  └─────┬──────┘  └────────────┘            │
│        │                                     │
│   ┌────┴────┐                               │
│   │ SQLite  │                               │
│   │   DB    │                               │
│   └─────────┘                               │
│        ▲                                     │
│        │ HTTP (localhost)                   │
│        │                                     │
│  ┌─────┴──────┐                             │
│  │   Agent    │  (systemd service)          │
│  │   :8081    │  ← Different port!          │
│  │            │                              │
│  │  wlan0 ──────► Creates virtual           │
│  │  wlan1 ──────► Wi-Fi interfaces          │
│  └────────────┘                             │
└──────────────────────────────────────────────┘
```

**Key Considerations:**
- ⚠️ Agent uses different port (`:8081` instead of `:8080` to avoid conflict with UI)
- ⚠️ Controller URL is `http://localhost:8000`
- ⚠️ Resource usage: Pi 5 8GB recommended (Docker + Agent + multiple interfaces)
- ⚠️ Agent can't use `eth0` for internet (traffic routing conflict)

### Setup Instructions

#### 1. Install Controller (as above)

```bash
# Deploy controller with Docker Compose
cd /mnt/wipi-data/wipi
docker compose up -d

# Verify controller is running
curl http://localhost:8000/health
```

#### 2. Install Agent on Same Pi

```bash
# Download deployment script
curl -O https://raw.githubusercontent.com/your-repo/wipi/main/scripts/deploy-to-pi.sh

# Make executable
chmod +x deploy-to-pi.sh

# Run installer with custom port and localhost controller
PI_USER=$USER \
CONTROLLER_URL=http://localhost:8000 \
AGENT_PORT=8081 \
./deploy-to-pi.sh localhost wipi-controller-01
```

**Script modifications needed** (update `deploy-to-pi.sh`):

```bash
# Add AGENT_PORT variable (default 8080)
AGENT_PORT=${AGENT_PORT:-8080}

# Update agent config template:
cat > /etc/wipi/agent_config.yaml <<EOF
agent_id: "$HOSTNAME"
controller_url: "$CONTROLLER_URL"
api_port: $AGENT_PORT  # ← Use variable instead of hardcoded 8080
...
EOF

# Update systemd service:
ExecStart=/usr/local/bin/uvicorn agent.src.main:app --host 0.0.0.0 --port $AGENT_PORT
```

#### 3. Verify Dual-Role Operation

```bash
# Check controller
curl http://localhost:8000/health

# Check UI
curl http://localhost:8080/

# Check agent
curl http://localhost:8081/status

# Check agent registration in controller
curl http://localhost:8000/api/pis | jq
# Should show wipi-controller-01 in list

# Check logs
docker compose logs -f controller
journalctl -u wipi-agent -f
```

#### 4. Resource Monitoring

```bash
# Monitor CPU/memory usage
htop

# Docker stats
docker stats

# Agent process stats
ps aux | grep uvicorn
```

**Expected Resource Usage (Pi 5 8GB):**
- Controller: ~200-400MB RAM, ~5-10% CPU (idle)
- UI: ~50MB RAM (nginx)
- Agent: ~100-200MB RAM, ~5-15% CPU (idle)
- Per interface: ~10-50MB RAM, varies by traffic type
- **Total (8 interfaces):** ~1-2GB RAM, 20-40% CPU under load

---

## Backup & Restore

### What to Backup

**Essential:**
- ✅ `data/wipi.db` - SQLite database (Pi registrations, scenarios, PSK sets, Ruckus One config)
- ✅ `.env` - Environment variables (password hash)

**Optional:**
- 🔵 `controller/scenarios/` - Stored scenario files (also in database)
- 🔵 Docker volumes (usually recreatable)

**NOT needed:**
- ❌ Docker images (rebuild from source)
- ❌ `node_modules/`, `__pycache__/` (recreatable)

### Backup Procedure

**Method 1: Manual Backup**

```bash
# Stop controller to ensure DB consistency
docker compose stop controller

# Create backup directory
mkdir -p ~/wipi-backups/$(date +%Y%m%d-%H%M%S)
BACKUP_DIR=~/wipi-backups/$(date +%Y%m%d-%H%M%S)

# Backup database
cp data/wipi.db $BACKUP_DIR/

# Backup environment
cp .env $BACKUP_DIR/

# Backup scenarios (if not in DB)
cp -r controller/scenarios $BACKUP_DIR/

# Create archive
tar -czf ~/wipi-backup-$(date +%Y%m%d-%H%M%S).tar.gz -C $BACKUP_DIR .

# Restart controller
docker compose start controller

# Verify backup
tar -tzf ~/wipi-backup-*.tar.gz
```

**Method 2: Automated Backup Script**

```bash
# Create backup script
cat > /usr/local/bin/backup-wipi.sh <<'EOF'
#!/bin/bash
set -e

BACKUP_ROOT="/mnt/wipi-data/backups"
WIPI_DIR="/mnt/wipi-data/wipi"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="$BACKUP_ROOT/$TIMESTAMP"

mkdir -p "$BACKUP_DIR"

# Stop controller
cd "$WIPI_DIR"
docker compose stop controller

# Backup files
cp data/wipi.db "$BACKUP_DIR/"
cp .env "$BACKUP_DIR/" 2>/dev/null || true
cp -r controller/scenarios "$BACKUP_DIR/" 2>/dev/null || true

# Create archive
tar -czf "$BACKUP_ROOT/wipi-backup-$TIMESTAMP.tar.gz" -C "$BACKUP_DIR" .

# Restart controller
docker compose start controller

# Keep only last 7 backups
cd "$BACKUP_ROOT"
ls -t wipi-backup-*.tar.gz | tail -n +8 | xargs rm -f

echo "Backup complete: $BACKUP_ROOT/wipi-backup-$TIMESTAMP.tar.gz"
EOF

# Make executable
sudo chmod +x /usr/local/bin/backup-wipi.sh

# Add to cron (daily at 2 AM)
echo "0 2 * * * /usr/local/bin/backup-wipi.sh" | crontab -
```

### Restore Procedure

**Scenario: Moving from util server to Raspberry Pi**

```bash
# 1. On OLD server (util), create backup
cd /opt/stacks/wipi
docker compose stop controller
tar -czf ~/wipi-backup.tar.gz data/wipi.db .env controller/scenarios

# 2. Copy backup to NEW Pi
scp ~/wipi-backup.tar.gz admin@<new-pi-ip>:~/

# 3. On NEW Pi, extract backup
ssh admin@<new-pi-ip>
cd /mnt/wipi-data/wipi
tar -xzf ~/wipi-backup.tar.gz

# 4. Verify database
ls -lh data/wipi.db

# 5. Start controller
docker compose up -d

# 6. Verify data
curl http://localhost:8000/api/pis | jq
# Should show all previously registered Pis

# 7. Update agent controller URLs (on each agent Pi)
# See "Configure Agent Pi Endpoints" above
```

---

## Migration Checklist

### Pre-Migration

- [ ] Backup current database
- [ ] Document current configuration (IP addresses, ports, hostnames)
- [ ] Test backup restore on dev system
- [ ] Prepare new Pi (OS installed, Docker ready)
- [ ] Schedule maintenance window (agents will disconnect during migration)

### Migration

- [ ] Stop controller on old server
- [ ] Create final backup
- [ ] Copy backup to new Pi
- [ ] Extract backup on new Pi
- [ ] Start controller on new Pi
- [ ] Verify controller health (`/health` endpoint)
- [ ] Verify database (`/api/pis`, `/api/scenarios`)
- [ ] Test UI access
- [ ] Update DNS/load balancer (if applicable)

### Post-Migration

- [ ] Update agent controller URLs (on each agent Pi)
- [ ] Restart all agents (`sudo systemctl restart wipi-agent`)
- [ ] Verify agent registration (check controller `/api/pis`)
- [ ] Test scenario deployment
- [ ] Test Ruckus One integration (if enabled)
- [ ] Monitor logs for errors
- [ ] Decommission old server (after 24-48 hours of stable operation)

### Rollback Plan

If migration fails:

1. Stop new Pi controller
2. Restart old server controller
3. Agents will auto-reconnect to old controller
4. Investigate issues before retrying

---

## Network Configuration

### Static IP (Recommended for Controller Pi)

```bash
# Edit dhcpcd.conf
sudo nano /etc/dhcpcd.conf

# Add at end:
interface eth0
static ip_address=192.168.1.100/24
static routers=192.168.1.1
static domain_name_servers=192.168.1.1 8.8.8.8

# Restart networking
sudo systemctl restart dhcpcd
```

### DNS/Hostname Setup

```bash
# Set hostname
sudo hostnamectl set-hostname wipi-controller

# Update /etc/hosts
sudo nano /etc/hosts
# Add:
192.168.1.100  wipi-controller

# On agent Pis, update /etc/hosts
echo "192.168.1.100  wipi-controller" | sudo tee -a /etc/hosts

# Use hostname in agent config
controller_url: "http://wipi-controller:8000"
```

### Firewall Rules (Pi Controller)

```bash
# Allow SSH, controller, UI
sudo ufw allow 22/tcp
sudo ufw allow 8000/tcp
sudo ufw allow 8080/tcp
sudo ufw allow 8081/tcp  # If running agent on same Pi

# Enable firewall
sudo ufw enable

# Check status
sudo ufw status
```

---

## Performance Tuning (Raspberry Pi)

### Docker Resource Limits

```yaml
# docker-compose.yml
services:
  controller:
    ...
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '2.0'
        reservations:
          memory: 512M
          cpus: '0.5'

  ui:
    ...
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: '0.5'
```

### Database Optimization

```bash
# Enable WAL mode for better concurrency
sqlite3 data/wipi.db "PRAGMA journal_mode=WAL;"

# Optimize database
sqlite3 data/wipi.db "VACUUM; ANALYZE;"

# Add to cron (monthly)
echo "0 3 1 * * sqlite3 /mnt/wipi-data/wipi/data/wipi.db 'VACUUM; ANALYZE;'" | crontab -
```

### Storage Performance

```bash
# Verify USB SSD is using USB 3.0
lsusb -t
# Look for "5000M" (USB 3.0) not "480M" (USB 2.0)

# Benchmark disk
sudo hdparm -t /dev/sda1
# Should see 100+ MB/sec for SSD

# Enable TRIM (for SSD longevity)
sudo fstrim -v /mnt/wipi-data
# Add to cron weekly
echo "0 4 * * 0 /usr/bin/fstrim -v /mnt/wipi-data" | sudo crontab -
```

### CPU Governor (Performance Mode)

```bash
# Check current governor
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor

# Set to performance mode
echo "performance" | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Make permanent
sudo apt install cpufrequtils
echo 'GOVERNOR="performance"' | sudo tee /etc/default/cpufrequtils
sudo systemctl restart cpufrequtils
```

---

## Troubleshooting

### Controller Won't Start

```bash
# Check Docker logs
docker compose logs controller

# Common issues:
# - Port 8000 already in use
sudo netstat -tulpn | grep 8000

# - Database locked
sudo fuser /mnt/wipi-data/wipi/data/wipi.db
# Kill process if needed

# - Out of memory
free -h
docker stats
```

### Agents Can't Connect

```bash
# Test connectivity from agent Pi
curl http://<controller-ip>:8000/health

# Check controller URL in agent config
cat /etc/wipi/agent_config.yaml | grep controller_url

# Check firewall on controller Pi
sudo ufw status

# Check controller logs
docker compose logs controller | grep -i "agent\|registration"
```

### Database Corruption

```bash
# Check database integrity
sqlite3 data/wipi.db "PRAGMA integrity_check;"

# If corrupted, restore from backup
docker compose stop controller
mv data/wipi.db data/wipi.db.corrupt
cp /path/to/backup/wipi.db data/wipi.db
docker compose start controller
```

---

## Monitoring

### System Health Dashboard (Optional)

```bash
# Install Prometheus + Grafana (optional)
# Add monitoring stack to docker-compose.yml

# Or use simple monitoring script
cat > /usr/local/bin/wipi-status.sh <<'EOF'
#!/bin/bash
echo "=== WiPi Status ==="
echo "Controller: $(curl -s http://localhost:8000/health | jq -r .status)"
echo "Registered Pis: $(curl -s http://localhost:8000/api/pis | jq '. | length')"
echo "Docker: $(docker compose ps --format json | jq -r '.State' | grep -c running) running"
echo "Memory: $(free -h | grep Mem | awk '{print $3 "/" $2}')"
echo "CPU: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}')%"
echo "Disk: $(df -h /mnt/wipi-data | tail -1 | awk '{print $3 "/" $2 " (" $5 ")"}')"
EOF

chmod +x /usr/local/bin/wipi-status.sh
```

---

## References

- [Raspberry Pi Documentation](https://www.raspberrypi.com/documentation/)
- [Docker on Raspberry Pi](https://docs.docker.com/engine/install/debian/)
- [SQLite Performance Tuning](https://www.sqlite.org/pragma.html)

**Last Updated:** 2026-02-11
