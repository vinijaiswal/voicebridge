#!/bin/bash
# Run from inside agent/ folder: ./debug_server.sh
# This starts the token server visibly so you can see the actual error

source .venv/bin/activate

echo "Starting token server with full logging..."
echo ""
uvicorn server:app --port 8080 --log-level debug
