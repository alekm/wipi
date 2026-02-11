#!/bin/bash
# Generate SHA-256 hash for WiPi admin password
# Usage: ./scripts/generate-password-hash.sh [password]

if [ -z "$1" ]; then
  echo "Usage: $0 <password>"
  echo "Example: $0 'MySecurePassword123!'"
  exit 1
fi

HASH=$(echo -n "$1" | sha256sum | cut -d' ' -f1)

echo ""
echo "Password: $1"
echo "SHA-256 Hash: $HASH"
echo ""
echo "Add this to your .env file:"
echo "WIPI_ADMIN_PASSWORD_HASH=$HASH"
echo ""
