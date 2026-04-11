#!/usr/bin/env python3
"""
Synapse Network — canonical 3-line developer demo.

Shows that AgentWallet.connect() → search → invoke works in 3 lines.
Runs against an in-process mock gateway; no external dependencies needed.

    pip install synapse-client
    python three_line_demo.py
"""
import json, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from uuid import uuid4

# ── Inline mock gateway (zero external dependency) ────────────────────────────
def _start_mock(port=18780):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _json(self, s, b):
            p = json.dumps(b).encode()
            self.send_response(s); self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(p))); self.end_headers(); self.wfile.write(p)
        def do_POST(self):
            if "/discovery" in self.path:
                self._json(200, {"results": [{"serviceId": "svc_eth_price", "serviceName": "ETH Price Feed",
                    "pricing": {"amount": "0.01", "currency": "USDC"}, "status": "online",
                    "health": {"overallStatus": "healthy"}, "summary": "Live ETH/USD price",
                    "tags": ["crypto"], "invoke": {}, "quoteTemplate": {"serviceId": "svc_eth_price", "responseMode": "sync",
                    "inputPreview": {"contentType":"application/json","payloadSchema":{},"sample":{}}}}],
                    "count": 1, "page": 1, "pageSize": 10, "totalCount": 1, "hasMore": False, "requestId": uuid4().hex})
            elif "/invoke" in self.path:
                int(self.headers.get("Content-Length",0)) and self.rfile.read(int(self.headers["Content-Length"]))
                self._json(200, {"invocationId": uuid4().hex, "serviceId": "svc_eth_price",
                    "status": "SUCCEEDED", "chargedUsdc": 0.01,
                    "result": {"body": {"price_usd": 3241.55, "pair": "ETH/USD", "source": "Synapse Mock"}},
                    "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            else:
                self._json(404, {})
    srv = HTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{port}"

# ── Start mock & set env so AgentWallet.connect() picks it up ─────────────────
import os
gw = _start_mock()
os.environ.setdefault("SYNAPSE_API_KEY", "demo_key")

# ═════════════════════════════════════════════════════════════════════════════
# THE 3 LINES — copy these into any agent
# ═════════════════════════════════════════════════════════════════════════════
from synapse_client import AgentWallet                                    # Line 1
wallet = AgentWallet.connect(budget=5.0, gateway_url=gw)                  # Line 2
svc    = wallet.search_services(query="ETH price feed").services[0]       # Line 3a — discover
result = wallet.invoke(svc.service_id, payload={}, cost_usdc=float(svc.price_usdc))  # Line 3b — invoke + pay
# ═════════════════════════════════════════════════════════════════════════════

print(f"\n✅  {result.status}  |  charged: ${result.charged_usdc} USDC  |  remaining: ${wallet.remaining_usdc} USDC")
print(f"    response: {json.dumps(result.result.get('body', result.result), ensure_ascii=False)}")
