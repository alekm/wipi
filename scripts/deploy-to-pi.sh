#!/bin/bash
# WiPi Automated Pi Deployment Script
# Usage: ./deploy-to-pi.sh <pi-ip> [pi-hostname]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PI_USER="${PI_USER:-admin}"
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
    echo -e "${RED}Error: Pi IP address required${NC}"
    echo "Usage: $0 <pi-ip> [pi-hostname]"
    echo ""
    echo "Example: $0 172.16.254.147 wipi-01"
    echo ""
    echo "Environment variables (or set in .env via wipi-init):"
    echo "  PI_USER         - SSH user (default: admin)"
    echo "  CONTROLLER_URL  - Controller URL"
    echo "  AGENT_API_KEY   - Agent API key (must match controller)"
    exit 1
fi

PI_IP="$1"
PI_HOSTNAME="${2:-wipi-$(echo $PI_IP | cut -d. -f4)}"

echo -e "${GREEN}=== WiPi Automated Deployment ===${NC}"
echo "Target Pi: $PI_USER@$PI_IP"
echo "Hostname: $PI_HOSTNAME"
echo "Controller: $CONTROLLER_URL"
echo "Agent API Key: ${AGENT_API_KEY:0:16}... (${#AGENT_API_KEY} chars)"
echo ""

# Test SSH connection
echo -e "${YELLOW}Testing SSH connection...${NC}"
if ! ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new -o BatchMode=yes "$PI_USER@$PI_IP" "echo 'SSH connection successful'" 2>/dev/null; then
    echo -e "${RED}Error: Cannot connect to $PI_USER@$PI_IP${NC}"
    echo "Make sure:"
    echo "  1. Your SSH key is added to the Pi"
    echo "  2. The Pi is reachable on the network"
    echo "  3. SSH is enabled on the Pi"
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

# Upload to Pi
echo -e "${YELLOW}Uploading files to Pi...${NC}"
scp -o StrictHostKeyChecking=accept-new -q wipi-agent.tar.gz "$PI_USER@$PI_IP:/tmp/"
echo -e "${GREEN}✓ Files uploaded${NC}"
echo ""

# Execute remote deployment script
echo -e "${YELLOW}Executing remote deployment...${NC}"
ssh -o StrictHostKeyChecking=accept-new -T "$PI_USER@$PI_IP" "sudo bash -s" <<EOF
set -e

echo "=== Starting Pi Configuration ==="

# Set hostname if different
CURRENT_HOSTNAME=\$(hostname)
if [ "\$CURRENT_HOSTNAME" != "$PI_HOSTNAME" ]; then
    echo "Setting hostname to $PI_HOSTNAME..."
    hostnamectl set-hostname $PI_HOSTNAME
    echo "127.0.1.1    $PI_HOSTNAME" >> /etc/hosts
    echo "✓ Hostname set to $PI_HOSTNAME"
fi

# Enable Wi-Fi interface
echo "Enabling Wi-Fi interface..."
if ! ip link show wlan0 &> /dev/null; then
    echo "⚠ Warning: wlan0 interface not found"
else
    # Set Wi-Fi country code if not set (required for rfkill)
    if [ ! -f /etc/wpa_supplicant/wpa_supplicant.conf ] || ! grep -q "country=" /etc/wpa_supplicant/wpa_supplicant.conf; then
        echo "  Setting Wi-Fi country code to US..."
        raspi-config nonint do_wifi_country US 2>/dev/null || true
        # Or set it manually
        if [ ! -f /etc/wpa_supplicant/wpa_supplicant.conf ]; then
            mkdir -p /etc/wpa_supplicant
            cat > /etc/wpa_supplicant/wpa_supplicant.conf <<WPACONF
country=US
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
WPACONF
        fi
    fi

    # Unblock Wi-Fi if blocked
    if command -v rfkill &> /dev/null; then
        echo "  Unblocking Wi-Fi with rfkill..."
        rfkill unblock wifi 2>/dev/null || true
        rfkill unblock wlan 2>/dev/null || true
    fi

    # Wait a moment for interface to come up
    sleep 1

    # Bring interface up
    ip link set wlan0 up 2>/dev/null || true

    # Check if wlan0 is up
    if ip link show wlan0 | grep -q "state UP\|state UNKNOWN\|state DOWN"; then
        echo "✓ Wi-Fi interface enabled"
        # Show current state
        ip link show wlan0 | grep "state" || true
    else
        echo "⚠ Warning: Could not bring up wlan0 interface"
        echo "  You may need to manually set the Wi-Fi country code:"
        echo "  sudo raspi-config nonint do_wifi_country <YOUR_COUNTRY_CODE>"
    fi
fi

# Disable unnecessary services to free resources
echo "Disabling unnecessary services..."
services_to_disable=(
    "bluetooth.service"
    "hciuart.service"
    "triggerhappy.service"
    "avahi-daemon.service"
)

for service in "\${services_to_disable[@]}"; do
    if systemctl is-enabled "\$service" &>/dev/null; then
        systemctl disable "\$service" 2>/dev/null || true
        systemctl stop "\$service" 2>/dev/null || true
        echo "  - Disabled \$service"
    fi
done

# Note: Not disabling X/display manager as it might be needed
# User can manually disable with: systemctl set-default multi-user.target

echo "✓ Services configured"

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
    firmware-misc-nonfree \
    firmware-iwlwifi \
    || { echo "Error installing dependencies"; exit 1; }

echo "✓ System dependencies installed"

# Mask system wpa_supplicant to prevent conflicts with agent
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
echo "Installing to \$INSTALL_DIR..."

# Backup old installation if exists
if [ -d "\$INSTALL_DIR" ]; then
    echo "  Backing up previous installation..."
    systemctl stop wipi-agent 2>/dev/null || true
    mv "\$INSTALL_DIR" "\$INSTALL_DIR.backup.\$(date +%s)"
fi

# Create installation directory
mkdir -p "\$INSTALL_DIR"
mv agent "\$INSTALL_DIR/"
mv shared "\$INSTALL_DIR/"

# Create Python virtual environment
echo "Creating Python virtual environment..."
cd "\$INSTALL_DIR"
python3 -m venv venv

# Install Python dependencies
echo "Installing Python dependencies..."
"\$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"\$INSTALL_DIR/venv/bin/pip" install --quiet -r agent/requirements.txt

echo "✓ Python environment configured"

# Create configuration directory
mkdir -p /etc/wipi

# Create agent configuration
echo "Creating agent configuration..."
cat > /etc/wipi/agent_config.yaml <<CONFIG_EOF
agent_id: "$PI_HOSTNAME"
controller_url: "$CONTROLLER_URL"
agent_api_key: "$AGENT_API_KEY"
api_port: 8080
max_interfaces: 8
default_base_interface: "wlan0"
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
WorkingDirectory=\$INSTALL_DIR
Environment="PYTHONPATH=\$INSTALL_DIR"
Environment="AGENT_ID=$PI_HOSTNAME"
Environment="CONTROLLER_URL=$CONTROLLER_URL"
Environment="AGENT_API_KEY=$AGENT_API_KEY"
Environment="API_PORT=8080"
Environment="BASE_INTERFACE=wlan0"
Environment="DHCP_CLIENT=dhclient"
Environment="MOCK_MODE=false"
ExecStart=\$INSTALL_DIR/venv/bin/python -m uvicorn agent.src.main:app --host 0.0.0.0 --port 8080
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
echo "Agent ID: $PI_HOSTNAME"
echo "API URL: http://\$(hostname -I | awk '{print \$1}'):8080"
echo "Controller: $CONTROLLER_URL"
EOF

echo -e "${GREEN}✓ Remote deployment completed${NC}"
echo ""

# Wait a moment for service to fully start
sleep 2

# Test agent API
echo -e "${YELLOW}Testing agent API...${NC}"
if ssh -o StrictHostKeyChecking=accept-new "$PI_USER@$PI_IP" "curl -s --max-time 5 http://localhost:8080/health" | grep -q "healthy"; then
    echo -e "${GREEN}✓ Agent API is responding${NC}"

    # Get agent status
    AGENT_STATUS=$(ssh -o StrictHostKeyChecking=accept-new "$PI_USER@$PI_IP" "curl -s http://localhost:8080/")
    echo ""
    echo "Agent Status:"
    echo "$AGENT_STATUS" | jq . 2>/dev/null || echo "$AGENT_STATUS"
else
    echo -e "${YELLOW}⚠ Agent API not responding yet (may still be starting)${NC}"
    echo "Check status with: ssh $PI_USER@$PI_IP 'sudo systemctl status wipi-agent'"
fi

echo ""
echo -e "${GREEN}=== Deployment Summary ===${NC}"
echo "Pi: $PI_HOSTNAME ($PI_IP)"
echo "Agent API: http://$PI_IP:8080"
echo "Controller: $CONTROLLER_URL"
echo ""
echo "Useful commands:"
echo "  View logs:    ssh $PI_USER@$PI_IP 'sudo journalctl -u wipi-agent -f'"
echo "  Check status: ssh $PI_USER@$PI_IP 'sudo systemctl status wipi-agent'"
echo "  Restart:      ssh $PI_USER@$PI_IP 'sudo systemctl restart wipi-agent'"
echo "  Get status:   curl http://$PI_IP:8080/status | jq"
echo ""
echo -e "${GREEN}✓ Deployment successful!${NC}"
