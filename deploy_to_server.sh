#!/bin/bash
# deploy_to_server.sh
# Deploys the Renoise AI Server from your local machine to the Proxmox server.

SERVER_IP="192.168.200.121"
SERVER_USER="root"
REMOTE_DIR="/root/"
LOCAL_DIR="./ai_server"
CONTAINER_NAME="renoise-server-1"

echo "=========================================="
echo "🚀 Deploying Renoise AI Server to Proxmox"
echo "=========================================="

# 1. Ensure sshpass is installed locally to handle the password automatically
if ! command -v sshpass &> /dev/null; then
    echo "Error: 'sshpass' is not installed."
    echo "Please install it first: sudo apt-get install sshpass (Linux) or brew install hudochenkov/sshpass/sshpass (Mac)"
    exit 1
fi

echo "Moving files to $SERVER_IP..."
# Copy the ai_server directory to /root/ on Proxmox
sshpass -p 'ColetteRae!2' scp -o StrictHostKeyChecking=no -r "$LOCAL_DIR" "$SERVER_USER@$SERVER_IP:$REMOTE_DIR"

if [ $? -ne 0 ]; then
    echo "❌ Deployment Failed: Could not copy files to server."
    exit 1
fi

echo "Restarting the Renoise AI systemd service on Proxmox..."
# Restart the service so it picks up the new Python code
sshpass -p 'ColetteRae!2' ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" "systemctl restart renoise-ai.service"

if [ $? -eq 0 ]; then
    echo "✅ Deployment Successful! Server is restarting."
else
    echo "⚠️ Files deployed, but could not restart 'renoise-ai.service'."
    echo "Check if the service is properly configured on the server."
fi
