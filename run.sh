#!/bin/bash

# ==============================================================================
# Renoise AI Suite 3.0 (Mac Studio Neural Engine Edition)
# Server Administration Script
# ==============================================================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
AI_SERVER_DIR="$DIR/ai_server"
VENV_PYTHON="$AI_SERVER_DIR/venv_mac/bin/python3"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_usage() {
    echo -e "${BLUE}Renoise AI Suite Control Script${NC}"
    echo "Usage: ./run.sh [command]"
    echo ""
    echo "Commands:"
    echo "  start   - Starts the Flask API and the Text2midi Neural Worker"
    echo "  stop    - Stops all AI background processes"
    echo "  status  - Checks if the servers are currently running"
    echo "  logs    - Tails the active server logs"
}

start_server() {
    echo -e "${YELLOW}Stopping any existing instances...${NC}"
    stop_server > /dev/null 2>&1
    
    echo -e "${BLUE}Starting AI Suite backend on Mac Studio (MPS)...${NC}"
    cd "$AI_SERVER_DIR" || exit
    
    if [ ! -f "$VENV_PYTHON" ]; then
        echo -e "${RED}Error: Python virtual environment not found at $VENV_PYTHON${NC}"
        echo "Did you complete the Phase 2 setup?"
        exit 1
    fi
    
    # Start the Flask API Bridge
    nohup $VENV_PYTHON app.py > server_boot.log 2>&1 &
    API_PID=$!
    echo -e "${GREEN}✓ Flask API started (PID $API_PID)${NC} on port 5055."
    
    # Start the Text2midi MPS Worker
    export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
    nohup $VENV_PYTHON worker.py > worker.log 2>&1 &
    WORKER_PID=$!
    echo -e "${GREEN}✓ Neural Worker started (PID $WORKER_PID)${NC}."
    
    echo -e "\n${GREEN}Both services are now running in the background.${NC}"
    echo "You can monitor them with: ./run.sh logs"
}

stop_server() {
    echo -e "${YELLOW}Shutting down AI processes...${NC}"
    if pgrep -f "app.py" > /dev/null; then
        pkill -f "app.py"
        echo -e "${GREEN}✓ Stopped Flask API.${NC}"
    fi
    if pgrep -f "worker.py" > /dev/null; then
        pkill -f "worker.py"
        echo -e "${GREEN}✓ Stopped Neural Worker.${NC}"
    fi
}

check_status() {
    echo -e "${BLUE}System Status:${NC}"
    
    if pgrep -f "app.py" > /dev/null; then
        echo -e "Flask API Bridge:   ${GREEN}[RUNNING]${NC}"
    else
        echo -e "Flask API Bridge:   ${RED}[STOPPED]${NC}"
    fi
    
    if pgrep -f "worker.py" > /dev/null; then
        echo -e "Text2midi Worker:   ${GREEN}[RUNNING]${NC}"
    else
        echo -e "Text2midi Worker:   ${RED}[STOPPED]${NC}"
    fi
}

show_logs() {
    echo -e "${BLUE}Tailing logs... (Press Ctrl+C to exit)${NC}"
    tail -f "$AI_SERVER_DIR/server_boot.log" "$AI_SERVER_DIR/worker.log"
}

case "$1" in
    start)
        start_server
        ;;
    stop)
        stop_server
        ;;
    status)
        check_status
        ;;
    logs)
        show_logs
        ;;
    *)
        print_usage
        ;;
esac
