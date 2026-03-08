#!/bin/bash

echo "Starting Renoise AI V2 decoupled architecture..."

cd "/home/juanquy/dev/Renoise AI Plugin/ai_server"
PYTHON_BIN="/home/juanquy/miniconda3/envs/ai_env/bin/python"

# Start the ML Worker in the background
export AUDIOCRAFT_NO_XFORMERS=1
$PYTHON_BIN -u worker.py &
WORKER_PID=$!

echo "Worker started with PID $WORKER_PID"

# Start the lightweight Flask API via Gunicorn (production server)
$PYTHON_BIN -m gunicorn -b 0.0.0.0:5000 --workers 4 --timeout 300 --access-logfile - app:app

# When Flask exits, kill the worker
kill $WORKER_PID
