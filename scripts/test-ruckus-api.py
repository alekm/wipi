#!/usr/bin/env python3
"""
Test script to query Ruckus One API for clients
"""
import requests
import json
import sys

# Credentials
TENANT_ID = "b21843c8a259439397faa3ef3d663eba"
CLIENT_ID = "05b5e993a03009750c6a736491d45a60"
CLIENT_SECRET = "1f9ec955bd2990636185872c74111a68"

def get_bearer_token(tenant_id, client_id, client_secret):
    """Get OAuth2 bearer token from Ruckus One"""
    auth_url = f"https://api.ruckus.cloud/oauth2/token/{tenant_id}"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "audience": "https://api.ruckus.cloud"
    }

    print(f"Requesting token from: {auth_url}")
    response = requests.post(auth_url, headers=headers, data=data)

    print(f"Auth response status: {response.status_code}")
    print(f"Auth response headers: {dict(response.headers)}")
    print(f"Auth response body: {response.text}")

    if response.status_code != 200:
        print(f"Failed to get token: {response.status_code} - {response.text}")
        sys.exit(1)

    token_data = response.json()
    if "access_token" not in token_data:
        print(f"No access_token in response: {token_data}")
        sys.exit(1)

    return token_data["access_token"]

def get_clients(bearer_token):
    """Get list of clients from Ruckus One"""
    url = "https://api.ruckus.cloud/clients"
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json"
    }

    print(f"\nRequesting clients from: {url}")
    response = requests.get(url, headers=headers, params={"size": 50})

    print(f"Clients response status: {response.status_code}")

    if response.status_code != 200:
        print(f"Failed to get clients: {response.status_code} - {response.text}")
        sys.exit(1)

    return response.json()

if __name__ == "__main__":
    print("=== Ruckus One API Test ===\n")

    # Get token
    token = get_bearer_token(TENANT_ID, CLIENT_ID, CLIENT_SECRET)
    print(f"\n✓ Got token: {token[:20]}...")

    # Get clients
    clients = get_clients(token)
    print(f"\n✓ Got {len(clients)} clients")

    # Display clients with OS detection
    print("\n=== Clients ===")
    for client in clients:
        mac = client.get('mac', 'unknown')
        ip = client.get('ip', 'unknown')
        hostname = client.get('hostname', 'unknown')
        os_type = client.get('osType', 'unknown')
        ssid = client.get('ssid', 'unknown')

        print(f"{mac:20} {ip:15} {hostname:20} OS: {os_type:15} SSID: {ssid}")
