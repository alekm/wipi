#!/bin/bash
# WiPi Agent Installation Script for Raspberry Pi

set -e

echo "=== WiPi Agent Installation ==="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This script must be run as root"
    exit 1
fi

# Configuration
INSTALL_DIR="/opt/wipi-agent"
CONTROLLER_URL="${CONTROLLER_URL:-http://192.168.1.10:8000}"
AGENT_ID="${AGENT_ID:-$(hostname)}"

echo "Install directory: $INSTALL_DIR"
echo "Controller URL: $CONTROLLER_URL"
echo "Agent ID: $AGENT_ID"

# Install system dependencies
echo "Installing system dependencies..."
apt-get update
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    wireless-tools \
    wpasupplicant \
    iw \
    dhcpcd5 \
    net-tools

# Create installation directory
echo "Creating installation directory..."
mkdir -p "$INSTALL_DIR"

# Copy agent files
echo "Copying agent files..."
cp -r agent "$INSTALL_DIR/"
cp -r shared "$INSTALL_DIR/"

# Create Python virtual environment
echo "Creating Python virtual environment..."
cd "$INSTALL_DIR"
python3 -m venv venv

# Install Python dependencies
echo "Installing Python dependencies..."
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r agent/requirements.txt

# Create configuration directory
echo "Creating configuration directory..."
mkdir -p /etc/wipi

# Create agent configuration file
echo "Creating agent configuration..."
cat > /etc/wipi/agent_config.yaml <<EOF
agent_id: "$AGENT_ID"
controller_url: "$CONTROLLER_URL"
api_port: 8080
max_interfaces: 8
default_base_interface: "wlan0"
dhcp_client: "dhclient"
mock_mode: false
EOF

# Create runtime directory
mkdir -p /var/run/wipi

# Install systemd service
echo "Installing systemd service..."
cp "$INSTALL_DIR/agent/wipi-agent.service" /etc/systemd/system/
systemctl daemon-reload

# Enable and start service
echo "Enabling and starting WiPi Agent service..."
systemctl enable wipi-agent
systemctl start wipi-agent

# Check status
echo ""
echo "=== Installation Complete ==="
echo ""
systemctl status wipi-agent --no-pager
echo ""
echo "WiPi Agent installed successfully!"
echo ""
echo "Useful commands:"
echo "  - View logs: journalctl -u wipi-agent -f"
echo "  - Restart:   systemctl restart wipi-agent"
echo "  - Stop:      systemctl stop wipi-agent"
echo "  - Status:    systemctl status wipi-agent"
echo ""
echo "Configuration file: /etc/wipi/agent_config.yaml"
echo "Agent API: http://$(hostname -I | awk '{print $1}'):8080"
