# WiPi Deployment Guide

## Prerequisites

1. **Controller** running (already done if you followed the main README)
2. **SSH access** to Raspberry Pis with your public key
3. **Raspberry Pis** running Raspberry Pi OS

## Quick Single Pi Deployment

Deploy to a single Pi:

```bash
cd /opt/stacks/wipi/scripts

# Set your controller URL (use your controller's IP)
export CONTROLLER_URL="http://172.16.254.204:8000"

# Deploy to a Pi
./deploy-to-pi.sh 172.16.254.147 wipi-01
```

The script will:
1. ✅ Test SSH connection
2. ✅ Set hostname
3. ✅ Enable Wi-Fi interface
4. ✅ Disable unnecessary services
5. ✅ Install system dependencies
6. ✅ Install Python packages
7. ✅ Configure the agent
8. ✅ Start the systemd service
9. ✅ Test the agent API

## Batch Deployment to Multiple Pis

### 1. Create a Pi list file

```bash
cd /opt/stacks/wipi/scripts
cp pi-list.txt.example pi-list.txt
```

Edit `pi-list.txt`:
```
172.16.254.147 wipi-01
172.16.254.148 wipi-02
172.16.254.149 wipi-03
```

### 2. Deploy to all Pis

```bash
export CONTROLLER_URL="http://172.16.254.204:8000"
./deploy-to-multiple-pis.sh pi-list.txt
```

This will deploy to all Pis in parallel and show a summary.

## Environment Variables

- `CONTROLLER_URL` - Controller API URL (default: http://172.16.254.204:8000)
- `PI_USER` - SSH user (default: admin)

## What Gets Installed

### System Packages
- python3, python3-pip, python3-venv
- wireless-tools, wpasupplicant, iw
- net-tools, isc-dhcp-client
- curl, jq

### Python Packages (in virtualenv)
- fastapi, uvicorn
- aiohttp
- psutil
- pyyaml

### Service Configuration
- Service: `/etc/systemd/system/wipi-agent.service`
- Config: `/etc/wipi/agent_config.yaml`
- Installation: `/opt/wipi-agent/`
- Runtime: `/var/run/wipi/`

## Verification

After deployment, verify the agent:

```bash
# Check service status
ssh admin@172.16.254.147 'sudo systemctl status wipi-agent'

# View logs
ssh admin@172.16.254.147 'sudo journalctl -u wipi-agent -f'

# Test API
curl http://172.16.254.147:8080/health
curl http://172.16.254.147:8080/status | jq
```

Check if Pi registered with controller:

```bash
curl http://localhost:8000/api/pis | jq
```

## Troubleshooting

### SSH Connection Failed

```bash
# Test SSH manually
ssh admin@172.16.254.147 echo "test"

# If password is required, add your SSH key:
ssh-copy-id admin@172.16.254.147
```

### Wi-Fi Interface Not Found

The Pi might not have a Wi-Fi adapter. Check with:

```bash
ssh admin@172.16.254.147 'ip link show'
ssh admin@172.16.254.147 'iw dev'
```

### Service Won't Start

Check logs:

```bash
ssh admin@172.16.254.147 'sudo journalctl -u wipi-agent -n 50'
```

Common issues:
- Python dependencies failed to install
- Port 8080 already in use
- Permission issues (service needs root)

### Agent Not Registering with Controller

Check network connectivity:

```bash
ssh admin@172.16.254.147 "curl -v http://172.16.254.204:8000/health"
```

Check agent configuration:

```bash
ssh admin@172.16.254.147 'cat /etc/wipi/agent_config.yaml'
```

## Re-deployment

To update an existing agent:

```bash
# The script automatically backs up the old installation
./deploy-to-pi.sh 172.16.254.147 wipi-01

# Old installation saved to: /opt/wipi-agent.backup.<timestamp>
```

## Uninstall

To remove the agent from a Pi:

```bash
ssh admin@172.16.254.147 'sudo bash -s' <<'EOF'
systemctl stop wipi-agent
systemctl disable wipi-agent
rm /etc/systemd/system/wipi-agent.service
rm -rf /opt/wipi-agent
rm -rf /etc/wipi
rm -rf /var/run/wipi
systemctl daemon-reload
EOF
```

## Manual Installation

If you prefer manual installation, see `agent/install.sh` for the steps.

## Next Steps

After successful deployment:

1. **Verify Pis are registered**: `curl http://localhost:8000/api/pis | jq`
2. **Edit a scenario**: Modify `controller/scenarios/simple_test.yaml` with your network SSID/password
3. **Apply scenario**: `curl -X POST http://localhost:8000/api/scenarios/simple-test-001/apply | jq`
4. **Monitor**: `curl http://localhost:8000/api/status | jq`

See the main README.md for full documentation.
