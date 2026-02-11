# WiPi System Status

## ✅ Successfully Deployed Components

### Controller (Running on util - 172.16.254.4)
- **Status**: ✅ Running
- **URL**: http://172.16.254.4:8000 or http://util:8000
- **Container**: wipi-controller (Docker)
- **Database**: SQLite at `/app/data/wipi.db`
- **API Docs**: http://util:8000/docs

### Pi Agent (wipi-01 - 172.16.254.147)
- **Status**: ✅ Running
- **API**: http://172.16.254.147:8080
- **Service**: wipi-agent.service (systemd)
- **Registration**: ✅ Registered with controller
- **System**: Raspberry Pi OS (Python 3.13)
  - CPU: 0% idle
  - Memory: 6.7% used
  - Temp: 50.7°C
  - Uptime: 48 minutes

### Loaded Scenarios
1. ✅ **basic-load-test-001**: 10 clients with mixed HTTP traffic (2 Pis required)
2. ✅ **heavy-traffic-001**: High-bandwidth video streaming and bulk transfers
3. ✅ **simple-test-001**: 2 clients for basic connectivity testing

## 📋 What's Working

1. **Automated Deployment**
   - SSH-based deployment script: `./scripts/deploy-to-pi.sh`
   - Batch deployment: `./scripts/deploy-to-multiple-pis.sh`
   - Auto-configures Pi (hostname, Wi-Fi, services)
   - Installs Python 3.13 compatible dependencies
   - Creates systemd service for auto-start

2. **Controller API**
   - Pi registration and management
   - Scenario CRUD operations
   - Fleet monitoring (polling every 10s)
   - Status aggregation

3. **Pi Agent API**
   - Configuration storage (`POST /configure`)
   - Configuration application (`POST /apply`)
   - Status reporting (`GET /status`)
   - Health checks (`GET /health`)

## ⚠️ Known Issues

### Wi-Fi Configuration
- **Issue**: Wi-Fi blocked by rfkill until country code is set
- **Status**: ✅ Fixed in deployment script (sets country=US)
- **Manual Fix**: `sudo raspi-config nonint do_wifi_country US`

### Pi Auto-Registration
- **Issue**: Pi agent doesn't auto-register with controller on startup
- **Status**: Manual registration working
- **Workaround**: Use controller API to register:
  ```bash
  curl -X POST http://util:8000/api/pis/register \
    -H "Content-Type: application/json" \
    -d '{"agent_id":"wipi-01","hostname":"wipi-01","ip_address":"172.16.254.147"...}'
  ```
- **TODO**: Add auto-registration to agent startup

## 🚀 Next Steps

### Ready to Test
1. **Edit Scenario** - Update `controller/scenarios/simple_test.yaml`:
   - Change `ssid` to your test network
   - Change `password` to your Wi-Fi password
   - Save changes and restart controller to reload

2. **Apply Scenario**:
   ```bash
   curl -X POST http://util:8000/api/scenarios/simple-test-001/apply | jq
   ```

3. **Monitor Execution**:
   ```bash
   # Get scenario status
   curl http://util:8000/api/scenarios/simple-test-001/status | jq
   
   # Get Pi status
   curl http://172.16.254.147:8080/status | jq
   
   # Watch agent logs
   ssh admin@172.16.254.147 'sudo journalctl -u wipi-agent -f'
   ```

### Scale Up
1. **Deploy to More Pis**:
   - Create `scripts/pi-list.txt` with your Pi IPs
   - Run: `./scripts/deploy-to-multiple-pis.sh pi-list.txt`

2. **Create Custom Scenarios**:
   - Copy an example scenario
   - Modify interface count, SSIDs, traffic patterns
   - Apply to your fleet

## 🔧 Useful Commands

### Controller Management
```bash
# View controller logs
docker compose logs -f controller

# Restart controller
docker compose restart controller

# List registered Pis
curl http://util:8000/api/pis | jq

# List scenarios
curl http://util:8000/api/scenarios | jq

# Get overall status
curl http://util:8000/api/status | jq
```

### Pi Agent Management
```bash
# View agent logs
ssh admin@172.16.254.147 'sudo journalctl -u wipi-agent -f'

# Restart agent
ssh admin@172.16.254.147 'sudo systemctl restart wipi-agent'

# Check agent status
curl http://172.16.254.147:8080/status | jq

# Check Wi-Fi interface
ssh admin@172.16.254.147 'iw dev'
ssh admin@172.16.254.147 'ip link show wlan0'
```

### Deployment
```bash
# Deploy to single Pi
export CONTROLLER_URL="http://172.16.254.4:8000"
./scripts/deploy-to-pi.sh <pi-ip> <hostname>

# Deploy to multiple Pis
./scripts/deploy-to-multiple-pis.sh pi-list.txt

# Re-deploy (updates existing installation)
./scripts/deploy-to-pi.sh 172.16.254.147 wipi-01
```

## 📚 Documentation
- **Main README**: `/opt/stacks/wipi/README.md`
- **Quick Start**: `/opt/stacks/wipi/QUICKSTART.md`
- **Deployment Guide**: `/opt/stacks/wipi/DEPLOYMENT.md`
- **API Docs**: http://util:8000/docs

## System Architecture
```
Controller (util:8000)
  ↓ HTTP/JSON API
wipi-01 (172.16.254.147:8080)
  → wlan0 (physical interface)
    → wlan0_1, wlan0_2, ... (virtual interfaces)
      → wpa_supplicant per interface
      → DHCP client per interface
      → Traffic generator per interface
```

## Success Metrics
- ✅ Controller deployed and running
- ✅ 1 Pi agent deployed and registered
- ✅ Automated deployment working
- ✅ 3 example scenarios loaded
- ⏳ Waiting for test scenario execution

## Ready for Production Testing!
The system is now ready to:
1. Create virtual Wi-Fi interfaces
2. Connect to test networks
3. Generate realistic client traffic
4. Monitor and report status

Just edit a scenario with your test network credentials and apply it!
