# WiPi Platform Compatibility Guide

## Overview

WiPi consists of two components with different platform requirements:

- **Controller**: Platform-agnostic (Docker-based)
- **Agent**: Linux-specific (requires wireless interfaces)

## Controller Compatibility

### ✅ Works on Any Platform with Docker

**Supported Platforms:**
- x86_64 (Intel/AMD)
- ARM64 (Raspberry Pi, Apple Silicon, AWS Graviton)
- ARM32 (older Raspberry Pis)

**Requirements:**
- Docker Engine 20.10+
- Docker Compose 2.0+
- 512MB+ RAM
- 1GB+ disk space

**Tested Operating Systems:**
- Ubuntu 20.04+
- Debian 11+
- Raspberry Pi OS (Bullseye+)
- macOS (Docker Desktop)
- Windows (Docker Desktop with WSL2)

**Deployment:**
```bash
# Works everywhere:
docker compose up -d
```

---

## Agent Compatibility

### ✅ Works on Linux Systems with Wireless

**Requirements:**
- **Linux kernel** with wireless support
- **Wireless network interface** (wlan0, wlx*, etc.)
- **Python 3.11+**
- **systemd** (for service management)
- **Wireless tools**: `wpa_supplicant`, `iw`, `dhclient`

### Supported Distributions

| Distribution | Status | Notes |
|-------------|--------|-------|
| **Raspberry Pi OS** | ✅ Fully Supported | Primary target platform |
| **Ubuntu 20.04+** | ✅ Fully Supported | Server or Desktop |
| **Debian 11+** | ✅ Fully Supported | Bullseye or newer |
| **Linux Mint** | ✅ Should Work | Based on Ubuntu |
| **Pop!_OS** | ✅ Should Work | Based on Ubuntu |
| **Kali Linux** | ✅ Should Work | Debian-based |
| **Arch Linux** | ⚠️ Manual Setup | No deployment script |
| **Fedora/RHEL** | ⚠️ Manual Setup | Different package manager |
| **Alpine Linux** | ❌ Not Supported | No systemd |
| **macOS** | ❌ Not Supported | No native wireless tools |
| **Windows** | ❌ Not Supported | No wpa_supplicant |

### Hardware Requirements

**Minimum (Development):**
- 1 CPU core
- 512MB RAM
- 1GB disk space
- 1 wireless network interface

**Recommended (Production):**
- 2+ CPU cores
- 2GB+ RAM (more with many interfaces)
- 8GB+ disk space
- 1-2 wireless network interfaces

**Tested Hardware:**
- Raspberry Pi 4B (2GB, 4GB, 8GB)
- Raspberry Pi 5 (4GB, 8GB)
- Generic x86 laptops with Intel wireless
- Intel NUC with wireless adapter
- USB Wi-Fi adapters (various chipsets)

---

## Deployment Scripts

### `deploy-to-pi.sh` - Raspberry Pi Specific

**Use for:**
- Raspberry Pi OS (32-bit or 64-bit)
- Raspberry Pi hardware

**Features:**
- Sets Wi-Fi country code with `raspi-config`
- Installs firmware packages for common Pi adapters
- Disables unnecessary Pi services (bluetooth, etc.)

**Usage:**
```bash
./scripts/deploy-to-pi.sh 172.16.254.147 wipi-01
```

### `deploy-to-debian.sh` - Generic Debian/Ubuntu

**Use for:**
- Ubuntu 20.04+
- Debian 11+
- Any Debian-based distro with wireless

**Features:**
- Auto-detects wireless interface (wlan0, wlx*, etc.)
- Skips Pi-specific configuration
- Works on x86, ARM, any architecture

**Usage:**
```bash
./scripts/deploy-to-debian.sh 192.168.1.100 wipi-debian-01
```

**Environment Variables:**
```bash
# Custom SSH user
DEPLOY_USER=ubuntu ./scripts/deploy-to-debian.sh 192.168.1.100 wipi-01

# Custom controller URL
CONTROLLER_URL=http://192.168.1.50:8000 ./scripts/deploy-to-debian.sh 192.168.1.100 wipi-01
```

---

## Key Differences Between Scripts

| Feature | deploy-to-pi.sh | deploy-to-debian.sh |
|---------|-----------------|---------------------|
| **Target OS** | Raspberry Pi OS | Ubuntu/Debian |
| **SSH User** | `admin` (Pi default) | Current user |
| **Wi-Fi Config** | Uses `raspi-config` | Generic rfkill |
| **Firmware** | Installs Pi-specific | Assumes present |
| **Service Cleanup** | Disables Pi services | Minimal cleanup |
| **Interface Detection** | Assumes `wlan0` | Auto-detects |

---

## Manual Installation (Other Platforms)

For distributions without a deployment script:

### 1. Install Dependencies

**Debian/Ubuntu:**
```bash
sudo apt install python3 python3-pip python3-venv \
  wpasupplicant iw net-tools isc-dhcp-client curl jq
```

**Arch Linux:**
```bash
sudo pacman -S python python-pip wpa_supplicant iw net-tools dhclient curl jq
```

**Fedora/RHEL:**
```bash
sudo dnf install python3 python3-pip wpa_supplicant iw net-tools dhclient curl jq
```

### 2. Create Installation Directory

```bash
sudo mkdir -p /opt/wipi-agent
sudo cp -r agent shared /opt/wipi-agent/
```

### 3. Create Python Environment

```bash
cd /opt/wipi-agent
sudo python3 -m venv venv
sudo ./venv/bin/pip install -r agent/requirements.txt
```

### 4. Create Configuration

```bash
sudo mkdir -p /etc/wipi
sudo tee /etc/wipi/agent_config.yaml <<EOF
agent_id: "wipi-manual-01"
controller_url: "http://172.16.254.4:8000"
api_port: 8080
max_interfaces: 8
default_base_interface: "wlan0"
dhcp_client: "dhclient"
mock_mode: false
EOF
```

### 5. Create Systemd Service

```bash
sudo tee /etc/systemd/system/wipi-agent.service <<EOF
[Unit]
Description=WiPi Agent
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/wipi-agent
Environment="PYTHONPATH=/opt/wipi-agent"
ExecStart=/opt/wipi-agent/venv/bin/python -m uvicorn agent.src.main:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```

### 6. Start Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable wipi-agent
sudo systemctl start wipi-agent
```

---

## Wireless Interface Compatibility

### Supported Interfaces

**Built-in Wireless:**
- ✅ Raspberry Pi built-in Wi-Fi (BCM43xx)
- ✅ Intel Wireless (iwlwifi)
- ✅ Broadcom (brcmfmac)
- ✅ Atheros (ath9k, ath10k)
- ✅ Realtek (rtl8xxxu)
- ✅ MediaTek (mt76)

**USB Adapters:**
- ✅ Realtek RTL8812AU
- ✅ Realtek RTL8821AU
- ✅ MediaTek MT7612U
- ✅ Atheros AR9271
- ✅ Ralink RT5370

**Virtual Interface Support:**
- Hardware must support creating managed (station) virtual interfaces
- Check with: `iw phy phy0 info | grep -A 5 "interface combinations"`

### Troubleshooting Wireless

**No wireless interface found:**
```bash
# List all network interfaces
ip link show

# List wireless interfaces
iw dev

# Check for blocked interfaces
rfkill list
sudo rfkill unblock all
```

**Interface but no virtual interface support:**
```bash
# Check capabilities
iw phy phy0 info | grep -A 10 "interface combinations"

# Look for "total <= X, #{ managed } <= Y"
# Y is the max number of station interfaces
```

---

## Performance Considerations

### By Platform

**Raspberry Pi 5 (8GB):**
- **Capacity**: 8-16 interfaces per Pi
- **CPU**: Quad-core 2.4GHz (sufficient)
- **Performance**: Excellent
- **Recommendation**: Best choice

**Raspberry Pi 4B (4GB/8GB):**
- **Capacity**: 1-4 interfaces per Pi (VIF issues on some models)
- **CPU**: Quad-core 1.5GHz (adequate)
- **Performance**: Good for base interface
- **Recommendation**: Use with USB adapters

**Ubuntu x86 Laptop:**
- **Capacity**: 2-4 interfaces (depends on wireless chip)
- **CPU**: Varies (usually sufficient)
- **Performance**: Excellent for development
- **Recommendation**: Good for testing

**Ubuntu Server with USB Adapters:**
- **Capacity**: 2-4 per adapter
- **CPU**: Varies
- **Performance**: Depends on USB controller
- **Recommendation**: Works well

---

## Cloud/VM Compatibility

### ❌ Not Supported

**Why VMs Don't Work:**
- VMs don't have direct access to wireless hardware
- Wi-Fi adapters can't be passed through to VMs easily
- Cloud instances (AWS, GCP, Azure) have no wireless interfaces

**Exceptions:**
- USB Wi-Fi adapters can sometimes be passed to VMs (complex setup)
- Physical servers with wireless cards work fine

**Recommendation:**
- Use physical hardware (Raspberry Pi, old laptops, mini PCs)
- Or USB Wi-Fi adapters on physical servers

---

## Containerization

### Controller: ✅ Fully Containerized

- Runs in Docker
- Platform-independent
- Easy to deploy

### Agent: ❌ Cannot Be Containerized

**Why Agents Don't Run in Docker:**
- Requires direct access to wireless hardware
- Needs to create network namespaces
- Must run wpa_supplicant per interface
- Requires root privileges for network manipulation

**Current Architecture:**
- Agent runs as systemd service (native)
- Direct hardware access
- Better performance and reliability

---

## Testing Compatibility

### Quick Compatibility Check

Run this on your target system:

```bash
# Check wireless interface
iw dev

# Check Python version (need 3.11+)
python3 --version

# Check required tools
which wpa_supplicant iw dhclient systemctl

# Check virtual interface support
sudo iw dev wlan0 interface add wlan0_test type station
sudo iw dev wlan0_test del
# If this succeeds, VIF is supported
```

If all checks pass, the system is compatible!

---

## Summary

**Controller:**
- ✅ Works everywhere Docker runs
- No platform restrictions

**Agent:**
- ✅ **Best on**: Raspberry Pi 5, Ubuntu with wireless
- ✅ **Works on**: Any Linux with wireless interfaces
- ⚠️ **Manual setup**: Arch, Fedora, non-Debian distros
- ❌ **Won't work**: macOS, Windows, VMs without wireless

**Recommendation for Production:**
- Controller: Run on any Docker host (x86 server, Pi, cloud)
- Agents: Raspberry Pi 5 (8GB) with USB adapters for maximum capacity
- Alternative: Ubuntu mini PCs with good wireless cards

---

**Last Updated:** 2026-02-11
