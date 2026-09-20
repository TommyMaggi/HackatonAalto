#!/usr/bin/env python3
import hmac
import json
import os
import sys
import time
from collections import defaultdict
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs

# Import the existing server handler
from ui.server import Handler, ROOT

TOKEN = os.environ.get("DEMO_ACCESS_TOKEN")
if not TOKEN:
    sys.exit("ERROR: DEMO_ACCESS_TOKEN is not set in the environment.")

RATE_LIMIT_READS = 120  # per min per IP
RATE_LIMIT_MODEL_IP = 6 # per min per IP
RATE_LIMIT_MODEL_GLOBAL = 60 # per hour across all clients

# Simple in-memory trackers
reads_tracker = defaultdict(list)
model_ip_tracker = defaultdict(list)
model_global_tracker = []

def clean_tracker(tracker, max_age):
    now = time.time()
    for k in list(tracker.keys()):
        tracker[k] = [t for t in tracker[k] if now - t < max_age]
        if not tracker[k]:
            del tracker[k]

def check_rate_limit():
    now = time.time()
    clean_tracker(reads_tracker, 60)
    clean_tracker(model_ip_tracker, 60)
    global model_global_tracker
    model_global_tracker = [t for t in model_global_tracker if now - t < 3600]

MODEL_ENDPOINTS = {
    "/api/hypothesis",
    "/api/chat",
    "/api/context_append",
    "/api/physical",
    "/api/shift_review",
    "/api/ask"
}

class DemoHandler(Handler):
    def _is_authorized(self):
        # Check query string
        if "?" in self.path:
            qs = parse_qs(self.path.split("?")[1])
            if "t" in qs:
                cand = qs["t"][0]
                if hmac.compare_digest(cand.encode(), TOKEN.encode()):
                    return True
        # Check header
        auth_header = self.headers.get("X-Demo-Token")
        if auth_header and hmac.compare_digest(auth_header.encode(), TOKEN.encode()):
            return True
        return False

    def _apply_rate_limits(self, is_model_call):
        ip = self.client_address[0]
        now = time.time()
        
        if is_model_call:
            if len([t for t in model_global_tracker if now - t < 3600]) >= RATE_LIMIT_MODEL_GLOBAL:
                return False, "Global AI model rate limit reached for the demo (60/hr). Please wait or check back later."
            if len([t for t in model_ip_tracker[ip] if now - t < 60]) >= RATE_LIMIT_MODEL_IP:
                return False, "Your IP has reached the AI model rate limit (6/min). Please wait a moment."
            model_global_tracker.append(now)
            model_ip_tracker[ip].append(now)
            return True, ""
        else:
            if len([t for t in reads_tracker[ip] if now - t < 60]) >= RATE_LIMIT_READS:
                return False, "Rate limit reached. Please wait a minute."
            reads_tracker[ip].append(now)
            return True, ""

    def dispatch_request(self, original_method):
        check_rate_limit()
        
        if not self._is_authorized():
            self.send_response(401)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>401 Unauthorized</h1><p>This is a private demo. Valid token required.</p>")
            return

        route = self.path.split("?")[0]
        
        if route.startswith("/data/features/"):
            self.send_response(403)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Access to raw sensor features is forbidden in this demo.")
            return

        if self.command == "POST" and route == "/api/model":
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "Model switching is disabled in demo mode. The switch is demonstrated live by the presenter."}')
            return

        is_model_call = self.command == "POST" and route in MODEL_ENDPOINTS
        allowed, msg = self._apply_rate_limits(is_model_call)
        
        if not allowed:
            self.send_response(429)
            if route.startswith("/api/"):
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": msg}).encode())
            else:
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(f"<h1>429 Too Many Requests</h1><p>{msg}</p>".encode())
            return
            
        if self.command == "GET" and (route == "/" or route.endswith(".html")):
            filepath = ROOT / route.lstrip("/")
            if filepath.is_dir():
                filepath = filepath / "index.html"
                
            if filepath.exists() and filepath.suffix == ".html":
                try:
                    content = filepath.read_text(encoding="utf-8")
                except Exception:
                    original_method()
                    return
                
                injection = """
                <script>
                    (function() {
                        const urlParams = new URLSearchParams(window.location.search);
                        const t = urlParams.get('t');
                        if (t) {
                            sessionStorage.setItem('demo_token', t);
                            window.history.replaceState({}, document.title, window.location.pathname);
                        }
                        const token = sessionStorage.getItem('demo_token');
                        
                        const origFetch = window.fetch;
                        window.fetch = async function() {
                            let [resource, config] = arguments;
                            if (!config) config = {};
                            if (!config.headers) config.headers = {};
                            if (token) {
                                config.headers['X-Demo-Token'] = token;
                            }
                            const res = await origFetch(resource, config);
                            if (res.status === 429) {
                                try {
                                    const err = await res.clone().json();
                                    showBanner("Rate Limit: " + err.error, true);
                                } catch (e) {
                                    showBanner("Rate Limit reached.", true);
                                }
                            }
                            return res;
                        };

                        const origOpen = window.XMLHttpRequest ? XMLHttpRequest.prototype.open : null;
                        if (origOpen) {
                            XMLHttpRequest.prototype.open = function() {
                                this.addEventListener('readystatechange', function() {
                                    if (this.readyState === 4 && this.status === 429) {
                                        let msg = "Rate limit reached.";
                                        try {
                                            msg = "Rate Limit: " + JSON.parse(this.responseText).error;
                                        } catch(e) {}
                                        showBanner(msg, true);
                                    }
                                });
                                return origOpen.apply(this, arguments);
                            };
                            
                            const origSend = XMLHttpRequest.prototype.send;
                            XMLHttpRequest.prototype.send = function() {
                                if (token) {
                                    this.setRequestHeader('X-Demo-Token', token);
                                }
                                return origSend.apply(this, arguments);
                            };
                        }

                        function showBanner(msg, isError) {
                            let banner = document.getElementById('demo-banner-overlay');
                            if (!banner) {
                                banner = document.createElement('div');
                                banner.id = 'demo-banner-overlay';
                                Object.assign(banner.style, {
                                    position: 'fixed',
                                    top: '0',
                                    left: '0',
                                    width: '100%',
                                    padding: '10px',
                                    textAlign: 'center',
                                    zIndex: '9999',
                                    fontFamily: 'sans-serif',
                                    fontWeight: 'bold',
                                    boxShadow: '0 2px 4px rgba(0,0,0,0.2)'
                                });
                                document.body.insertBefore(banner, document.body.firstChild);
                                document.body.style.paddingTop = "40px";
                            }
                            banner.style.backgroundColor = isError ? '#ffebee' : '#fff3e0';
                            banner.style.color = isError ? '#c62828' : '#e65100';
                            banner.innerHTML = msg;
                        }
                        
                        document.addEventListener("DOMContentLoaded", function() {
                            showBanner("Private demo. Your actions are recorded in the decision log, which is append-only by design &mdash; that is the audit trail this system is built around.", false);
                        });
                    })();
                </script>
                """
                content = content.replace("</head>", injection + "</head>")
                body = content.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

        original_method()

    def do_GET(self):
        self.dispatch_request(super().do_GET)

    def do_POST(self):
        self.dispatch_request(super().do_POST)

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
    server = ThreadingHTTPServer(("127.0.0.1", port), DemoHandler)
    print(f"Starting Demo Server on http://127.0.0.1:{port}")
    server.serve_forever()
