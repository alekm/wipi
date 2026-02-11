#!/bin/bash
# Deploy WiPi agent to multiple Raspberry Pis in parallel
# Usage: ./deploy-to-multiple-pis.sh <pi-list-file>

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ $# -lt 1 ]; then
    echo -e "${RED}Error: Pi list file required${NC}"
    echo ""
    echo "Usage: $0 <pi-list-file>"
    echo ""
    echo "Pi list file format (one per line):"
    echo "  172.16.254.147 wipi-01"
    echo "  172.16.254.148 wipi-02"
    echo "  172.16.254.149 wipi-03"
    echo ""
    echo "Or just IP addresses (hostnames will be auto-generated):"
    echo "  172.16.254.147"
    echo "  172.16.254.148"
    echo ""
    exit 1
fi

PI_LIST_FILE="$1"

if [ ! -f "$PI_LIST_FILE" ]; then
    echo -e "${RED}Error: File not found: $PI_LIST_FILE${NC}"
    exit 1
fi

# Read Pi list
mapfile -t PI_LINES < <(grep -v '^#' "$PI_LIST_FILE" | grep -v '^[[:space:]]*$')

if [ ${#PI_LINES[@]} -eq 0 ]; then
    echo -e "${RED}Error: No Pis found in $PI_LIST_FILE${NC}"
    exit 1
fi

echo -e "${GREEN}=== WiPi Batch Deployment ===${NC}"
echo "Found ${#PI_LINES[@]} Pis to deploy"
echo ""

# Create log directory
LOG_DIR="/tmp/wipi-deploy-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$LOG_DIR"

echo "Logs will be saved to: $LOG_DIR"
echo ""

# Deploy to each Pi in parallel
PIDS=()
for line in "${PI_LINES[@]}"; do
    # Parse line (IP hostname or just IP)
    read -r pi_ip pi_hostname <<< "$line"

    if [ -z "$pi_hostname" ]; then
        pi_hostname="wipi-$(echo $pi_ip | cut -d. -f4)"
    fi

    echo -e "${YELLOW}Starting deployment to $pi_ip ($pi_hostname)...${NC}"

    # Deploy in background
    (
        "$SCRIPT_DIR/deploy-to-pi.sh" "$pi_ip" "$pi_hostname" > "$LOG_DIR/${pi_hostname}.log" 2>&1
        echo "$?" > "$LOG_DIR/${pi_hostname}.exit"
    ) &

    PIDS+=($!)
done

echo ""
echo "Waiting for all deployments to complete..."
echo ""

# Wait for all deployments
for pid in "${PIDS[@]}"; do
    wait "$pid"
done

# Generate summary
echo ""
echo -e "${GREEN}=== Deployment Summary ===${NC}"
echo ""

SUCCESS_COUNT=0
FAIL_COUNT=0

for line in "${PI_LINES[@]}"; do
    read -r pi_ip pi_hostname <<< "$line"
    if [ -z "$pi_hostname" ]; then
        pi_hostname="wipi-$(echo $pi_ip | cut -d. -f4)"
    fi

    exit_code=$(cat "$LOG_DIR/${pi_hostname}.exit" 2>/dev/null || echo "1")

    if [ "$exit_code" = "0" ]; then
        echo -e "${GREEN}✓${NC} $pi_hostname ($pi_ip) - Success"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        echo -e "${RED}✗${NC} $pi_hostname ($pi_ip) - Failed (see $LOG_DIR/${pi_hostname}.log)"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
done

echo ""
echo "Results: $SUCCESS_COUNT succeeded, $FAIL_COUNT failed"
echo "Logs: $LOG_DIR"
echo ""

if [ $FAIL_COUNT -gt 0 ]; then
    echo -e "${YELLOW}Some deployments failed. Check the logs for details.${NC}"
    exit 1
else
    echo -e "${GREEN}All deployments completed successfully!${NC}"

    # Test controller can reach all Pis
    echo ""
    echo -e "${YELLOW}Testing controller connectivity...${NC}"
    echo ""

    for line in "${PI_LINES[@]}"; do
        read -r pi_ip pi_hostname <<< "$line"
        if [ -z "$pi_hostname" ]; then
            pi_hostname="wipi-$(echo $pi_ip | cut -d. -f4)"
        fi

        if curl -s --max-time 3 "http://$pi_ip:8080/health" | grep -q "healthy"; then
            echo -e "${GREEN}✓${NC} $pi_hostname - API responding"
        else
            echo -e "${YELLOW}⚠${NC} $pi_hostname - API not responding (may still be starting)"
        fi
    done

    echo ""
    echo -e "${GREEN}Deployment complete!${NC}"
    echo "Check registered Pis: curl http://localhost:8000/api/pis | jq"
fi
