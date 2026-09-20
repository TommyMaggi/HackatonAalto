#!/bin/bash
cd "$(dirname "$0")"

if [ -f .demo_server.pid ]; then
    PID=$(cat .demo_server.pid)
    kill $PID 2>/dev/null && echo "Stopped demo_server.py ($PID)" || echo "demo_server.py already stopped"
    rm .demo_server.pid
fi

if [ -f .cloudflared.pid ]; then
    PID=$(cat .cloudflared.pid)
    kill $PID 2>/dev/null && echo "Stopped cloudflared ($PID)" || echo "cloudflared already stopped"
    rm .cloudflared.pid
fi
