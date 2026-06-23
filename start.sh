#!/bin/bash
# Color definitions
GREEN="\033[92m"
BLUE="\033[94m"
YELLOW="\033[93m"
RED="\033[91m"
BOLD="\033[1m"
RESET="\033[0m"

echo -e "${BLUE}=========================================${RESET}"
echo -e "${BLUE}   Starting BamBot Agent Services...   ${RESET}"
echo -e "${BLUE}=========================================${RESET}"
echo -e "${RED}${BOLD}🚨 SECURITY WARNING: NEVER expose BamBot to the public internet!${RESET}"
echo -e "Run only inside local network or secure VPN (Tailscale/WireGuard)."
echo -e "${BLUE}=========================================${RESET}"

# Kill any existing uvicorn processes on 8000 and 8001
echo "Cleaning up any stale servers on ports 8000/8001..."
pkill -f "uvicorn.*8000" || true
pkill -f "uvicorn.*8001" || true

# Start Mock Printer Server
echo -e "Starting ${YELLOW}Mock BamBuddy API Server${RESET} on port 8001..."
uv run uvicorn tests.mock_bambuddy:app --host 0.0.0.0 --port 8001 > mock_bambuddy.log 2>&1 &
MOCK_PID=$!

# Wait for mock to boot
sleep 1.5

# Start FastAPI Portal
echo -e "Starting ${YELLOW}FastAPI Agent Web Portal${RESET} on port 8000..."
uv run uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8000 > fast_api_app.log 2>&1 &
PORTAL_PID=$!

echo -e "${GREEN}✔ Both services successfully running in the background!${RESET}"
echo -e "- Mock Printer API:  ${BLUE}http://localhost:8001${RESET}"
echo -e "- Web Dashboard UI:  ${BLUE}http://localhost:8000${RESET}"
echo ""
echo "Logs are written to 'mock_bambuddy.log' and 'fast_api_app.log'."
echo -e "To stop both servers, run: ${YELLOW}kill $MOCK_PID $PORTAL_PID${RESET}"
echo -e "${BLUE}=========================================${RESET}"
