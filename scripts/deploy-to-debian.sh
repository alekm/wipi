#!/bin/bash
# WiPi Deployment for Generic Debian/Ubuntu Systems
# Usage: ./deploy-to-debian.sh <host-ip> [hostname]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
DEPLOY_USER="${DEPLOY_USER:-${USER}}"
CONTROLLER_URL="${CONTROLLER_URL:-http://172.16.254.4:8000}"
AGENT_API_KEY="${AGENT_API_KEY:-387d5f76c069bc167dc3ba74b1adb2b25233e9874e369dfa436894c3906bad0e}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Load .env from project root if present (created by wipi-init)
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    # shellcheck source=/dev/null
    . "$PROJECT_ROOT/.env"
    set +a
fi

# Parse arguments
if [ $# -lt 1 ]; then
    echo -e "${RED}Error: Host IP address required${NC}"
    echo "Usage: $0 <host-ip> [hostname]"
    echo ""
    echo "Example: $0 192.168.1.100 wipi-debian-01"
    echo ""
    echo "Environment variables (or set in .env via wipi-init):"
    echo "  DEPLOY_USER     - SSH user (default: current user)"
    echo "  CONTROLLER_URL  - Controller URL"
    echo "  AGENT_API_KEY   - Agent API key (must match controller)"
    exit 1
fi

HOST_IP="$1"
HOSTNAME="${2:-wipi-$(echo $HOST_IP | cut -d. -f4)}"

echo -e "${GREEN}=== WiPi Deployment (Generic Debian/Ubuntu) ===${NC}"
echo "Target Host: $DEPLOY_USER@$HOST_IP"
echo "Hostname: $HOSTNAME"
echo "Controller: $CONTROLLER_URL"
echo "Agent API Key: ${AGENT_API_KEY:0:16}... (${#AGENT_API_KEY} chars)"
echo ""

# Test SSH connection
echo -e "${YELLOW}Testing SSH connection...${NC}"
if ! ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new -o BatchMode=yes "$DEPLOY_USER@$HOST_IP" "echo 'SSH connection successful'" 2>/dev/null; then
    echo -e "${RED}Error: Cannot connect to $DEPLOY_USER@$HOST_IP${NC}"
    echo "Make sure:"
    echo "  1. Your SSH key is added to the host"
    echo "  2. The host is reachable on the network"
    echo "  3. SSH is enabled on the host"
    exit 1
fi
echo -e "${GREEN}✓ SSH connection successful${NC}"
echo ""

# Create temporary staging directory
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

echo -e "${YELLOW}Preparing deployment package...${NC}"
# Copy agent files to temp directory
cp -r "$PROJECT_ROOT/agent" "$TEMP_DIR/"
cp -r "$PROJECT_ROOT/shared" "$TEMP_DIR/"

# Create deployment archive
cd "$TEMP_DIR"
tar czf wipi-agent.tar.gz agent shared
echo -e "${GREEN}✓ Deployment package created${NC}"
echo ""

# Upload to host
echo -e "${YELLOW}Uploading files to host...${NC}"
scp -o StrictHostKeyChecking=accept-new -q wipi-agent.tar.gz "$DEPLOY_USER@$HOST_IP:/tmp/"
echo -e "${GREEN}✓ Files uploaded${NC}"
echo ""

# Execute remote deployment script (pass vars so remote script can use them)
echo -e "${YELLOW}Executing remote deployment...${NC}"
ssh -o StrictHostKeyChecking=accept-new -T "$DEPLOY_USER@$HOST_IP" \
    "HOSTNAME='$HOSTNAME' CONTROLLER_URL='$CONTROLLER_URL' AGENT_API_KEY='$AGENT_API_KEY' sudo -E bash -s" <<'EOF'
set -e

echo "=== Starting System Configuration ==="

# Set hostname if different
CURRENT_HOSTNAME=$(hostname)
if [ "$CURRENT_HOSTNAME" != "$HOSTNAME" ]; then
    echo "Setting hostname to $HOSTNAME..."
    hostnamectl set-hostname $HOSTNAME
    # Add to /etc/hosts if not already there
    if ! grep -q "127.0.1.1.*$HOSTNAME" /etc/hosts; then
        echo "127.0.1.1    $HOSTNAME" >> /etc/hosts
    fi
    echo "✓ Hostname set to $HOSTNAME"
fi

# Detect wireless interface
WLAN_INTERFACE=""
for iface in /sys/class/net/*; do
    iface_name=$(basename "$iface")
    if [[ "$iface_name" == wlan* ]] || [[ "$iface_name" == wlx* ]]; then
        WLAN_INTERFACE="$iface_name"
        echo "Found wireless interface: $WLAN_INTERFACE"
        break
    fi
done

if [ -z "$WLAN_INTERFACE" ]; then
    echo "⚠ Warning: No wireless interface found"
    echo "  Expected wlan0, wlx*, etc."
    echo "  System will install but may not function correctly"
    WLAN_INTERFACE="wlan0"  # Fallback
else
    # Ensure wireless interface is up
    echo "Enabling wireless interface $WLAN_INTERFACE..."

    # Unblock Wi-Fi if rfkill is available
    if command -v rfkill &> /dev/null; then
        echo "  Unblocking Wi-Fi with rfkill..."
        rfkill unblock wifi 2>/dev/null || true
        rfkill unblock wlan 2>/dev/null || true
    fi

    # Bring interface up
    ip link set "$WLAN_INTERFACE" up 2>/dev/null || true

    # Check status
    if ip link show "$WLAN_INTERFACE" | grep -q "state UP\|state UNKNOWN\|state DOWN"; then
        echo "✓ Wireless interface enabled"
    else
        echo "⚠ Warning: Could not bring up wireless interface"
    fi
fi

# Update package list
echo "Updating package list..."
apt-get update -qq

# Install system dependencies
echo "Installing system dependencies..."
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    python3 \
    python3-pip \
    python3-venv \
    wpasupplicant \
    iw \
    net-tools \
    isc-dhcp-client \
    curl \
    jq \
    || { echo "Error installing dependencies"; exit 1; }

echo "✓ System dependencies installed"

# Mask system wpa_supplicant to prevent conflicts
echo "Disabling system wpa_supplicant..."
if systemctl is-enabled wpa_supplicant &>/dev/null || systemctl is-active wpa_supplicant &>/dev/null; then
    systemctl stop wpa_supplicant 2>/dev/null || true
    systemctl mask wpa_supplicant 2>/dev/null || true
    echo "✓ System wpa_supplicant disabled"
fi

# Extract agent files
echo "Extracting WiPi agent..."
cd /tmp
tar xzf wipi-agent.tar.gz
rm wipi-agent.tar.gz

# Install to /opt/wipi-agent
INSTALL_DIR="/opt/wipi-agent"
echo "Installing to $INSTALL_DIR..."

# Backup old installation if exists
if [ -d "$INSTALL_DIR" ]; then
    echo "  Backing up previous installation..."
    systemctl stop wipi-agent 2>/dev/null || true
    mv "$INSTALL_DIR" "$INSTALL_DIR.backup.$(date +%s)"
fi

# Create installation directory
mkdir -p "$INSTALL_DIR"
mv agent "$INSTALL_DIR/"
mv shared "$INSTALL_DIR/"

# Create Python virtual environment
echo "Creating Python virtual environment..."
cd "$INSTALL_DIR"
python3 -m venv venv

# Install Python dependencies
echo "Installing Python dependencies..."
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -r agent/requirements.txt

echo "✓ Python environment configured"

# Create configuration directory
mkdir -p /etc/wipi

# Create agent configuration
echo "Creating agent configuration..."
cat > /etc/wipi/agent_config.yaml <<CONFIG_EOF
agent_id: "$HOSTNAME"
controller_url: "$CONTROLLER_URL"
agent_api_key: "$AGENT_API_KEY"
api_port: 8080
max_interfaces: 8
default_base_interface: "$WLAN_INTERFACE"
dhcp_client: "dhclient"
mock_mode: false
CONFIG_EOF

echo "✓ Configuration created"

# Create runtime directory
mkdir -p /var/run/wipi

# Install systemd service
echo "Installing systemd service..."
cat > /etc/systemd/system/wipi-agent.service <<SERVICE_EOF
[Unit]
Description=WiPi Agent - Wi-Fi Client Farm Agent
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment="PYTHONPATH=$INSTALL_DIR"
Environment="AGENT_ID=$HOSTNAME"
Environment="CONTROLLER_URL=$CONTROLLER_URL"
Environment="AGENT_API_KEY=$AGENT_API_KEY"
Environment="API_PORT=8080"
Environment="BASE_INTERFACE=$WLAN_INTERFACE"
Environment="DHCP_CLIENT=dhclient"
Environment="MOCK_MODE=false"
ExecStart=$INSTALL_DIR/venv/bin/python -m uvicorn agent.src.main:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE_EOF

# Reload systemd and enable service
systemctl daemon-reload
systemctl enable wipi-agent

# Start the service
echo "Starting WiPi agent service..."
systemctl start wipi-agent

# Wait for service to start
sleep 3

# Check service status
if systemctl is-active --quiet wipi-agent; then
    echo "✓ WiPi agent service started successfully"
else
    echo "⚠ Warning: Service may not have started properly"
    systemctl status wipi-agent --no-pager || true
fi

echo ""
echo "=== Deployment Complete ==="
echo "Agent ID: $HOSTNAME"
echo "Wireless Interface: $WLAN_INTERFACE"
echo "API URL: http://$(hostname -I | awk '{print $1}'):8080"
echo "Controller: $CONTROLLER_URL"
EOF

echo -e "${GREEN}✓ Remote deployment completed${NC}"
echo ""

# Wait for service to fully start
sleep 2

# Test agent API
echo -e "${YELLOW}Testing agent API...${NC}"
if ssh -o StrictHostKeyChecking=accept-new "$DEPLOY_USER@$HOST_IP" "curl -s --max-time 5 http://localhost:8080/health" | grep -q "healthy"; then
    echo -e "${GREEN}✓ Agent API is responding${NC}"

    # Get agent status
    AGENT_STATUS=$(ssh -o StrictHostKeyChecking=accept-new "$DEPLOY_USER@$HOST_IP" "curl -s http://localhost:8080/")
    echo ""
    echo "Agent Status:"
    echo "$AGENT_STATUS" | jq . 2>/dev/null || echo "$AGENT_STATUS"
else
    echo -e "${YELLOW}⚠ Agent API not responding yet (may still be starting)${NC}"
    echo "Check status with: ssh $DEPLOY_USER@$HOST_IP 'sudo systemctl status wipi-agent'"
fi

echo ""
echo -e "${GREEN}=== Deployment Summary ===${NC}"
echo "Host: $HOSTNAME ($HOST_IP)"
echo "Agent API: http://$HOST_IP:8080"
echo "Controller: $CONTROLLER_URL"
echo ""
echo "Useful commands:"
echo "  View logs:    ssh $DEPLOY_USER@$HOST_IP 'sudo journalctl -u wipi-agent -f'"
echo "  Check status: ssh $DEPLOY_USER@$HOST_IP 'sudo systemctl status wipi-agent'"
echo "  Restart:      ssh $DEPLOY_USER@$HOST_IP 'sudo systemctl restart wipi-agent'"
echo "  Get status:   curl http://$HOST_IP:8080/status | jq"
echo ""
echo -e "${GREEN}✓ Deployment successful!${NC}"
