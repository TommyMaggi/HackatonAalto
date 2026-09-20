#!/bin/bash
set -e
cd "$(dirname "$0")"

if [ -z "$DEMO_ACCESS_TOKEN" ]; then
    echo "ERROR: DEMO_ACCESS_TOKEN is not set."
    exit 1
fi

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
SNAP_DIR="artifacts/snapshots/$TIMESTAMP"
mkdir -p "$SNAP_DIR"

echo "Taking snapshot of artifacts to $SNAP_DIR..."
cp artifacts/*.json "$SNAP_DIR/" 2>/dev/null || true
cp artifacts/decision_log.jsonl "$SNAP_DIR/" 2>/dev/null || true
if [ -f eval/validation_report.json ]; then
    cp eval/validation_report.json "$SNAP_DIR/" 2>/dev/null || true
fi

echo "Starting demo_server.py on localhost:8002..."
.venv/bin/python3 demo_server.py 8002 > server_demo.log 2>&1 &
echo $! > .demo_server.pid

echo "Starting cloudflared quick tunnel..."
cloudflared tunnel --url http://127.0.0.1:8002 > cloudflared_demo.log 2>&1 &
echo $! > .cloudflared.pid

echo "Waiting for tunnel URL..."
sleep 5
URL=$(grep -o 'https://[-a-zA-Z0-9]*\.trycloudflare.com' cloudflared_demo.log | head -n 1)
if [ -z "$URL" ]; then sleep 3; URL=$(grep -o 'https://[-a-zA-Z0-9]*\.trycloudflare.com' cloudflared_demo.log | head -n 1); fi

if [ -n "$URL" ]; then
    echo "========================================================"
    echo "DEMO IS LIVE!"
    echo "URL for judges:"
    echo "$URL/?t=$DEMO_ACCESS_TOKEN"
    echo "========================================================"
else
    echo "WARNING: Could not extract URL from cloudflared_demo.log."
fi
