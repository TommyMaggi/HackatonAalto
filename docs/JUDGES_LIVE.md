# Judges Live Demo Instructions

This document explains how to run, stop, and restore the live demo environment for the hackathon judges.

## Start the Demo
To start the demo securely with a public URL:
1. Ensure the `DEMO_ACCESS_TOKEN` environment variable is set (this is the shared token for the judges).
2. Run `./serve_demo.sh`.
3. The script will automatically:
   - Verify the token.
   - Take a snapshot of the current state of `artifacts/` and `eval/`.
   - Start the local Python server behind a wrapper enforcing security constraints.
   - Start a Cloudflare quick tunnel.
   - Print a live, publicly accessible URL appended with the `?t=<token>`.

Share this URL with the judges.

## Stop the Demo
When the judging period is over, or if you need to quickly kill the server:
- Run `./stop_demo.sh`.
This safely stops both the tunnel and the Python backend.

## Restore from Snapshot
Judges may use the UI to override or mutate decisions, which affects the decision log and other artifacts.
- To revert the artifacts back to their state before the demo started, run `./restore_demo.sh`.

## Security & Limitations
During the live demo, the following protections are active:
- **Token Required:** Any request lacking the correct token is denied (401).
- **Rate Limits:** Aggressive rate limiting is enabled. 120 reads/min, 6 model calls/min/IP, 60 model calls/hour globally. If these limits are hit, the UI will display a banner.
- **No Raw Data:** The raw `data/features/**` files are entirely inaccessible.
- **No Direct Ollama Access:** Ollama runs safely bounded to `localhost:11434`. The tunnel only exposes the application server (`localhost:8001`).
- **No Model Switching:** The `POST /api/model` endpoint is disabled to prevent judges from arbitrarily mutating `config/llm.yaml`. (If a switch to Gemini is necessary, do it locally and restart).

## Gemini Fallback
If Ollama struggles under the load, you must switch the system to use Gemini:
1. Ensure `GEMINI_API_KEY` is in your environment.
2. Edit `config/llm.yaml` and switch the active provider to Gemini.
3. Restart the server (`./stop_demo.sh` then `./serve_demo.sh`).

## Custom DNS Records
If you eventually wish to bind this to `vucumpra.com`, add a `CNAME` record in your DNS provider pointing to the cloudflared endpoint UUID (for quick tunnels this isn't possible directly, but if you create a named tunnel via Cloudflare Zero Trust, you would add a `CNAME` record to `<tunnel-uuid>.cfargotunnel.com`).
