# WiPi - Wi-Fi Client Farm System

**Raspberry Pi-based Wi-Fi load testing system with intelligent resident simulation**

WiPi creates realistic Wi-Fi network load by simulating hundreds of apartment residents connecting to access points, generating traffic, and rotating through different usage patterns. Perfect for testing MDU (Multi-Dwelling Unit) Wi-Fi infrastructure, device fingerprinting accuracy, and network performance under realistic conditions.

---

## ✨ Features

### Intelligent Resident Simulation
- 🏘️ **Apartment-Based Model** - Simulate real apartment buildings with DPSK passphrases
- 🔄 **Automatic Rotation** - Residents "move in" and "move out" on configurable schedules
- 🕐 **Time-Aware Traffic** - Different usage patterns for morning, day, and evening
- 📊 **Realistic Load** - Browser sessions, video streaming, file transfers matched to time of day

### Distributed Architecture
- 🥧 **Raspberry Pi Fleet** - Deploy across multiple Pis for scale
- 📡 **Virtual Interfaces** - Multiple Wi-Fi clients per Pi (hardware-dependent)
- 🎯 **Pull-Based Config** - Agents autonomously fetch and apply configurations
- 💪 **Self-Healing** - Automatic recovery from connection failures

### Management & Monitoring
- 🖥️ **Web Dashboard** - React-based UI for complete system control
- 📈 **Real-Time Status** - Monitor all interfaces, traffic, and Pi health
- 🔍 **Ruckus One Integration** - Track device fingerprinting accuracy
- 📝 **Audit Logging** - Complete trail of all administrative actions

### Security & Access Control
- 🔐 **Admin Authentication** - Session-based login with httpOnly cookies
- 🎭 **Demo Mode** - Read-only access for demonstrations
- 🔑 **Agent API Keys** - Secure agent-to-controller communication
- 🛡️ **Security Headers** - CSP, X-Frame-Options, and more

---

## 🚀 Quick Start

### Prerequisites

- **Controller Host:** Any Linux machine with Docker and Docker Compose
- **Agent Hosts:** Raspberry Pi 5 (or Pi 4B with limitations - see Hardware Compatibility)
- **Network:** Controller and agents must be on the same network or routable
- **Wi-Fi Infrastructure:** Access points with DPSK or PSK authentication

### 1. Clone and Start Controller

```bash
git clone https://github.com/yourusername/wipi.git
cd wipi

# Start controller and UI
docker compose up -d

# Check status
docker compose ps
docker compose logs -f controller
```

**Access the UI:** http://localhost:8080  
**API Documentation:** http://localhost:8000/docs

### 2. Deploy Agents to Raspberry Pis

```bash
# Single Pi deployment
./scripts/deploy-to-pi.sh 192.168.1.100 wipi-01

# Multiple Pis (create pi-list.txt first)
./scripts/deploy-to-multiple-pis.sh pi-list.txt

# Custom controller URL
CONTROLLER_URL=http://192.168.1.50:8000 ./scripts/deploy-to-pi.sh 192.168.1.100 wipi-01
```

**Pi List Format** (`pi-list.txt`):
```
192.168.1.100 wipi-01
192.168.1.101 wipi-02
192.168.1.102 wipi-03
```

### 3. Import DPSK Passphrases

1. Export DPSK CSV from your Wi-Fi controller (e.g., Ruckus MDU 360)
2. Navigate to **Resident Simulation** tab in UI
3. Click **Import PSK CSV**
4. Upload file and provide ID, Name, and SSID

### 4. Start Resident Simulation

1. In **Resident Simulation** tab, configure:
   - **Enable Simulation:** ON
   - **PSK Set:** Select your imported set
   - **Target Active Apartments:** Number of simultaneous connections
   - **Rotation Interval:** Hours between rotations
   - **Max Interfaces per Pi:** Limit per device

2. Click **Update Simulation**

The system will automatically distribute apartments across Pis, create virtual interfaces, connect to APs, and generate realistic traffic patterns.

---

## 🔐 Authentication

### Admin Access

**Default Password:** `Ruckus123!`

**Login to UI:**
1. Navigate to http://localhost:8080 (starts in Demo mode)
2. Click toggle switch in header
3. Enter password when prompted
4. Session lasts 24 hours

**Change Password:**
```bash
# Generate new hash
echo -n "YourNewPassword" | sha256sum

# Set environment variable
export WIPI_ADMIN_PASSWORD_HASH="your_hash_here"
docker compose up -d
```

### Agent API Key

**Default Key:** `387d5f76c069bc167dc3ba74b1adb2b25233e9874e369dfa436894c3906bad0e`

**Generate New Key:**
```bash
openssl rand -hex 32

# Update controller
export AGENT_API_KEY="your_new_key_here"
docker compose up -d

# Update all agents: Edit /etc/wipi/agent_config.yaml
agent_api_key: "your_new_key_here"
sudo systemctl restart wipi-agent
```

---

## 📊 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Controller (Docker)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐    │
│  │   FastAPI    │  │   SQLite     │  │  Resident         │    │
│  │   Backend    │  │   Database   │  │  Simulator        │    │
│  └──────────────┘  └──────────────┘  └───────────────────┘    │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│  Pi Agent 1   │    │  Pi Agent 2   │    │  Pi Agent 3   │
│  ┌─────────┐  │    │  ┌─────────┐  │    │  ┌─────────┐  │
│  │ wlan0   │  │    │  │ wlan0   │  │    │  │ wlan0   │  │
│  │ wlan0_1 │  │    │  │ wlan0_1 │  │    │  │ wlan0_1 │  │
│  │ wlan1   │  │    │  │ wlan1   │  │    │  │ wlan1   │  │
│  └─────────┘  │    │  └─────────┘  │    │  └─────────┘  │
└───────────────┘    └───────────────┘    └───────────────┘
        │                    │                    │
        └────────────────────┴────────────────────┘
                             ▼
                    ┌─────────────────┐
                    │   Access Point  │
                    └─────────────────┘
```

---

## 🛠️ Hardware Compatibility

### Recommended: Raspberry Pi 5
✅ Full virtual interface support  
✅ 4-8 clients per Pi (built-in + USB Wi-Fi)  
✅ Traffic routing works correctly

### Limited: Raspberry Pi 4B
⚠️ Virtual interface routing issues  
⚠️ Use only base interface = 1 client per Pi  
⚠️ Or add USB Wi-Fi adapters for physical interfaces

### USB Wi-Fi Adapters
Compatible (tested):
- MediaTek MT7612U (2 interfaces)
- Ralink RT5572 (2 interfaces)
- Atheros AR9271 (2 interfaces)

---

## 📈 Monitoring

### Dashboard Metrics
- Total interfaces (connected, connecting, error)
- Pi status (online, offline, last seen)
- Traffic activity indicators
- Simulation status (active apartments, next rotation)

### Audit Logs
```bash
# View all audit events
docker compose logs controller | grep "wipi.audit"

# Example output:
# {"timestamp": "2026-02-11T21:35:12Z", "action": "create", 
#  "resource_type": "psk_set", "user": "admin", "success": true}
```

---

## 🚨 Troubleshooting

### Pi Not Registering
```bash
# On Pi
sudo systemctl status wipi-agent
journalctl -u wipi-agent -f

# Check connectivity
ping <controller-ip>
```

### Interface Not Connecting
```bash
# Check interface status
iw dev
iwconfig

# Check WPA
ps aux | grep wpa_supplicant
wpa_cli -i wlan0_1 status

# Check DHCP
ip addr show wlan0_1
```

### VIF Creation Fails
```bash
# Check VIF support
iw phy phy0 info | grep -A 10 "interface combinations"

# Reduce max_interfaces_per_pi in simulation config
# Or add USB Wi-Fi adapters
```

---

## 📚 Documentation

- **[Security Roadmap](docs/SECURITY_ROADMAP.md)** - Security hardening plan and implementation status
- **[Deployment Guide](docs/DEPLOYMENT_GUIDE.md)** - Complete Raspberry Pi deployment guide
- **[Platform Compatibility](docs/PLATFORM_COMPATIBILITY.md)** - Deployment on other Linux distributions
- **[API Documentation](http://localhost:8000/docs)** - Interactive OpenAPI documentation (when controller running)

---

## 🤝 Contributing

Contributions welcome!

```bash
# Fork and clone
git clone https://github.com/yourusername/wipi.git

# Create feature branch
git checkout -b feature/amazing-feature

# Make changes and commit
git commit -m 'Add amazing feature'

# Push and create PR
git push origin feature/amazing-feature
```

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details

---

## 🙏 Acknowledgments

- Built for testing **CommScope Ruckus** MDU 360 and Ruckus One
- Uses **DPSK** (Dynamic Pre-Shared Key) authentication
- Inspired by real-world MDU Wi-Fi deployment challenges

---

**Built with ❤️ for Wi-Fi testing and network engineering**
