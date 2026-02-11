# WiPi Quick Start Guide

Get WiPi up and running in 15 minutes.

## Prerequisites

- 1+ Raspberry Pi (3B+ or 4) with Raspberry Pi OS installed
- Linux/Mac/Windows machine for the controller (or another Pi)
- Raspberry Pis connected to the same network as the controller
- Wi-Fi network to test against

## Step 1: Start the Controller

On your controller machine:

```bash
cd /opt/stacks/wipi

# Create data directory
mkdir -p data

# Start controller with Docker Compose
docker-compose up -d

# Verify controller is running
curl http://localhost:8000/health
# Should return: {"status":"healthy"}

# View logs
docker-compose logs -f controller
```

Controller is now running at `http://localhost:8000`

API documentation: `http://localhost:8000/docs`

## Step 2: Install Agent on Raspberry Pi

On each Raspberry Pi:

```bash
# Update system
sudo apt update

# Copy WiPi files to Pi (from your dev machine)
# Option 1: Use scp
scp -r /opt/stacks/wipi pi@raspberrypi:/tmp/

# Option 2: Clone from git
git clone <your-repo> /tmp/wipi

# On the Pi, set controller URL (use controller's IP address)
export CONTROLLER_URL="http://192.168.1.10:8000"

# Set agent ID (optional, defaults to hostname)
export AGENT_ID="pi-001"

# Install agent
cd /tmp/wipi/agent
sudo ./install.sh

# Installation will:
# - Install system dependencies
# - Create Python virtual environment
# - Install Python packages
# - Create /etc/wipi/agent_config.yaml
# - Install and start systemd service

# Verify agent is running
systemctl status wipi-agent

# Check agent API
curl http://localhost:8080/health
# Should return: {"status":"healthy","agent_id":"pi-001"}
```

## Step 3: Verify Pi Registration

Back on the controller:

```bash
# List registered Pis
curl http://localhost:8000/api/pis | jq

# You should see your Pi listed with status "online"
```

Example output:
```json
[
  {
    "pi_id": "pi-001",
    "agent_id": "pi-001",
    "hostname": "raspberrypi",
    "ip_address": "192.168.1.100",
    "status": "online",
    "last_seen": "2024-01-15T10:30:00Z"
  }
]
```

## Step 4: Edit a Scenario

Edit an example scenario to match your network:

```bash
cd /opt/stacks/wipi/controller/scenarios

# Edit simple_test.yaml
nano simple_test.yaml
```

Update the scenario:
1. Change `pi_id` to match your Pi's ID (e.g., "pi-001")
2. Change `ssid` to your test network's SSID
3. Change `password` to your Wi-Fi password

```yaml
id: "simple-test-001"
name: "Simple Test"
description: "2 clients for testing"

pis:
  - pi_id: "pi-001"  # <- Change this to your Pi ID
    interfaces:
      - name: "wlan0_1"
        ssid: "YourNetworkSSID"  # <- Change this
        password: "YourPassword"   # <- Change this
        traffic:
          type: "http_browser"
          config:
            urls: ["http://httpbin.org/html"]
            interval: 30
```

## Step 5: Apply the Scenario

```bash
# List available scenarios
curl http://localhost:8000/api/scenarios | jq

# Apply the simple test scenario
curl -X POST http://localhost:8000/api/scenarios/simple-test-001/apply | jq

# Response will show the scenario status
```

## Step 6: Monitor Status

Watch the scenario in action:

```bash
# Get scenario status
curl http://localhost:8000/api/scenarios/simple-test-001/status | jq

# Get detailed Pi status
curl http://localhost:8000/api/pis/pi-001/status | jq

# Get overall fleet status
curl http://localhost:8000/api/status | jq

# Watch agent logs on the Pi
ssh pi@raspberrypi
journalctl -u wipi-agent -f
```

You should see:
- Interfaces being created (wlan0_1, wlan0_2)
- WPA supplicant connecting to your network
- DHCP obtaining IP addresses
- Traffic generators starting
- HTTP requests being made

## Step 7: Verify on Access Point

Log into your Wi-Fi access point and verify:
- You see 2 new clients connected
- They have different MAC addresses
- They're generating traffic

## Step 8: Stop the Scenario

```bash
# Stop the scenario (destroys interfaces, stops traffic)
curl -X POST http://localhost:8000/api/scenarios/simple-test-001/stop | jq

# Verify interfaces are gone
curl http://localhost:8000/api/pis/pi-001/status | jq
# Should show no interfaces
```

## Next Steps

### Scale Up

Install the agent on more Raspberry Pis:

```bash
# On each additional Pi
export CONTROLLER_URL="http://192.168.1.10:8000"
export AGENT_ID="pi-002"  # Unique ID for each Pi
sudo ./install.sh
```

### Test Different Scenarios

Try the other example scenarios:

```bash
# Basic load test - 10 clients with HTTP traffic
curl -X POST http://localhost:8000/api/scenarios/basic-load-test-001/apply | jq

# Heavy traffic - Video streaming and bulk transfers
curl -X POST http://localhost:8000/api/scenarios/heavy-traffic-001/apply | jq
```

### Create Custom Scenarios

1. Copy an example scenario
2. Modify the interfaces, SSIDs, and traffic patterns
3. Apply your custom scenario

```bash
cd /opt/stacks/wipi/controller/scenarios
cp simple_test.yaml my_scenario.yaml
nano my_scenario.yaml
# Edit as needed

# Restart controller to load new scenario
docker-compose restart controller

# Apply your scenario
curl -X POST http://localhost:8000/api/scenarios/my-scenario-001/apply | jq
```

## Troubleshooting

### Pi Not Registering

```bash
# On Pi, check agent is running
systemctl status wipi-agent

# Check logs
journalctl -u wipi-agent -n 50

# Verify controller is reachable
ping 192.168.1.10
curl http://192.168.1.10:8000/health

# Check configuration
cat /etc/wipi/agent_config.yaml
```

### Interfaces Not Connecting

```bash
# On Pi, check wpa_supplicant
wpa_cli -i wlan0_1 status

# Check for interface
iw dev

# Manually test connection
wpa_cli -i wlan0_1 scan
wpa_cli -i wlan0_1 scan_results

# Check SSID and password in scenario
```

### Permission Errors

The agent needs root privileges to create interfaces:

```bash
# Verify service is running as root
systemctl status wipi-agent | grep "Main PID"
ps aux | grep <PID>  # Should show root
```

## Mock Mode Testing

Test without real hardware:

```bash
# Start controller normally
docker-compose up -d

# Start agent in mock mode (no root needed)
cd /opt/stacks/wipi/agent
export MOCK_MODE=true
export AGENT_ID="mock-pi-001"
export CONTROLLER_URL="http://localhost:8000"
python -m uvicorn src.main:app --host 0.0.0.0 --port 8080

# Agent will simulate all operations
```

## Getting Help

- Check the main README.md for detailed documentation
- View API docs at http://localhost:8000/docs
- Check logs: `docker-compose logs controller` and `journalctl -u wipi-agent`
- Open an issue on GitHub

## Success Checklist

- [ ] Controller running and accessible
- [ ] At least one Pi agent installed and online
- [ ] Pi appears in `GET /api/pis` endpoint
- [ ] Scenario edited with correct SSID/password
- [ ] Scenario applies successfully
- [ ] Interfaces visible in Pi status
- [ ] Interfaces connected to Wi-Fi (state: "connected")
- [ ] Traffic generators active
- [ ] Clients visible on access point

You're now ready to use WiPi for Wi-Fi load testing!
