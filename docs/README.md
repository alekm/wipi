# WiPi Documentation

This directory contains comprehensive guides for deploying, securing, and operating WiPi.

## Documents

### [Security Roadmap](SECURITY_ROADMAP.md)
**Phased security hardening plan from current state to enterprise-grade security.**

**Quick Overview:**
- **Phase 1 (1-2 days):** Quick wins - API sanitization, security headers, audit logging
- **Phase 2 (3-5 days):** Backend authentication - Sessions, API keys, middleware
- **Phase 3 (5-10 days):** Enhanced security - RBAC, multi-user, secrets encryption
- **Phase 4 (10+ days):** Advanced security - HTTPS/TLS, OAuth2/SSO, 2FA

**Current Status:** ✅ Frontend password protection (SHA-256 hash)

**Recommended Next Step:** Implement Phase 1 (Quick Wins)

---

### [Deployment Guide](DEPLOYMENT_GUIDE.md)
**Complete guide to deploying WiPi on different hardware, including Raspberry Pi.**

**Topics Covered:**
- Current deployment architecture (x86 server)
- Moving controller to Raspberry Pi
- Dual-role Pi (controller + agent on same device)
- Backup and restore procedures
- Migration checklists
- Performance tuning for Pi
- Network configuration
- Troubleshooting

**Use Cases:**
- **"I want to run everything on Raspberry Pis"** → See "Moving to Raspberry Pi Controller"
- **"I need to back up my data"** → See "Backup & Restore"
- **"I want a portable demo system"** → See "Dual-Role Pi" setup
- **"Controller server crashed, need to restore"** → See "Restore Procedure"

---

### [Platform Compatibility](PLATFORM_COMPATIBILITY.md)
**What platforms can run WiPi controller and agents?**

**Quick Answers:**
- **Controller**: ✅ Works on any platform with Docker (x86, ARM, Mac, Windows)
- **Agent**: ✅ Works on Linux with wireless interfaces (Raspberry Pi, Ubuntu, Debian)

**Topics Covered:**
- Platform requirements and compatibility matrix
- Deployment scripts: `deploy-to-pi.sh` vs `deploy-to-debian.sh`
- Manual installation for other distros
- Wireless interface compatibility
- Performance by platform
- Cloud/VM considerations

**Use Cases:**
- **"Can I run agents on Ubuntu?"** → Yes! See "deploy-to-debian.sh"
- **"Will this work on my old laptop?"** → If it has Linux + wireless, yes
- **"Can I run this in AWS?"** → Controller yes, agents no (no wireless in cloud VMs)
- **"What about Arch/Fedora?"** → See "Manual Installation"

---

## Quick Start Guides

### For Security Hardening

**If you have 2 hours:**
```bash
# Implement API response sanitization
# See SECURITY_ROADMAP.md → Phase 1.1
```

**If you have 1 day:**
```bash
# Implement all Phase 1 (Quick Wins)
# - API sanitization
# - Security headers
# - Audit logging
```

**If you have 1 week:**
```bash
# Implement Phase 1 + Phase 2
# - Quick wins
# - Backend session authentication
# - Agent API keys
```

---

### For Deployment

**Moving to Raspberry Pi:**
```bash
# 1. Read DEPLOYMENT_GUIDE.md → "Moving to Raspberry Pi Controller"
# 2. Prepare Pi hardware (Pi 5 8GB + USB SSD recommended)
# 3. Follow installation steps
# 4. Backup old deployment
# 5. Restore to new Pi
# 6. Update agent endpoints
```

**Backup Current System:**
```bash
# See DEPLOYMENT_GUIDE.md → "Backup & Restore"
cd /opt/stacks/wipi
docker compose stop controller
tar -czf ~/wipi-backup-$(date +%Y%m%d).tar.gz data/wipi.db .env
docker compose start controller
```

**Restore to New System:**
```bash
# See DEPLOYMENT_GUIDE.md → "Restore Procedure"
scp wipi-backup.tar.gz admin@new-pi:~/
ssh admin@new-pi
tar -xzf wipi-backup.tar.gz
docker compose up -d
```

---

## Reference

### Current Security Implementation

**Password:** `Ruckus123!`
**Hash:** `8f4179b458b4e4622c32089b025ff4e4b531137642dfdf5143b5f29af3c32e84` (SHA-256)

**Generate new password hash:**
```bash
./scripts/generate-password-hash.sh "YourPassword"
```

**Default Mode:** Demo (read-only)

**Demo Mode Restrictions:**
- ❌ Cannot access Simulation tab
- ❌ Cannot configure Ruckus One
- ❌ Cannot delete Pis
- ✅ Can view all monitoring/status

**Admin Mode Access:**
- ✅ Full access to all features
- Requires password: `Ruckus123!`

### Hardware Requirements

**Current Deployment:**
- Controller: x86 server (util)
- Agents: Raspberry Pi 4B/5

**Recommended for Pi Controller:**
- Raspberry Pi 5 8GB RAM
- USB 3.0 SSD (128GB+)
- Wired Gigabit Ethernet
- Cooling (heatsink/fan)

**Dual-Role Pi (Controller + Agent):**
- Raspberry Pi 5 8GB RAM (minimum)
- USB SSD required (not SD card)
- Multiple Wi-Fi adapters (built-in + USB)
- Expect ~1-2GB RAM usage, 20-40% CPU under load

---

## Document Maintenance

**Last Updated:** 2026-02-11

**Update Triggers:**
- Security implementation changes → Update SECURITY_ROADMAP.md
- Deployment process changes → Update DEPLOYMENT_GUIDE.md
- New hardware tested → Update DEPLOYMENT_GUIDE.md hardware requirements
- New security vulnerabilities → Update SECURITY_ROADMAP.md

**Contributors:**
- Add your name here when updating docs

---

## External Resources

**Security:**
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [Mozilla Web Security](https://infosec.mozilla.org/guidelines/web_security)

**Raspberry Pi:**
- [Official Documentation](https://www.raspberrypi.com/documentation/)
- [Docker on Pi](https://docs.docker.com/engine/install/debian/)

**WiPi-Specific:**
- Main documentation: `/opt/stacks/wipi/CLAUDE.md`
- API documentation: `http://localhost:8000/docs` (when running)
