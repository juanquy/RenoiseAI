#!/bin/bash

echo "🚀 Starting Renoise AI V2 (Blackwell Edition)..."

cd "/home/juanquy/dev/Renoise AI Plugin/ai_server"
PYTHON_BIN="/home/juanquy/miniconda3/envs/ai_env/bin/python"

# Kill any stray processes first
pkill -f worker.py
pkill -f gunicorn

# Start the ML Worker
export AUDIOCRAFT_NO_XFORMERS=1
nohup $PYTHON_BIN -u worker.py > worker.log 2>&1 &
echo "  - Neural Worker started."

# Start the Flask API
nohup $PYTHON_BIN -m gunicorn -b 0.0.0.0:5000 --workers 2 --timeout 600 --access-logfile server_access.log app:app > server_boot.log 2>&1 &
echo "  - Conductor Server started (Port 5000)."

echo "✅ AI Backend is now running in the background."
echo "Logs: worker.log and server_boot.log"
