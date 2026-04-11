#!/usr/bin/env python3
"""
Synapse Network — 3-Line Quickstart Demo
=========================================
Demonstrates the full consumer flow:
  1. Create a SynapseClient (AgentWallet equivalent)
  2. Discover a service via MCP search
  3. Invoke + auto-deduct USDC

Run against a live gateway:
    SYNAPSE_API_KEY=<key> python quickstart_demo.py

Run against the bundled mock gateway (no real gateway needed):
    python quickstart_demo.py --mock

Requirements:
    pip install synapse-client   # actual package name
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from uuid import uuid4

from synapse_client import SynapseClient
from synapse_client.exceptions import BudgetExceededError, DiscoveryError, InvokeError


# ---------------------------------------------------------------------------
# Mock gateway — enables zero-dependency local demo
# ---------------------------------------------------------------------------

MOCK_SERVICE_ID = "svc_demo_market_sentiment"
MOCK_SERVICE_PRICE = 0.05
MOCK_INVOCATION_ID = uuid4().hex


class _MockGatewayHandler(BaseHTTPRequestHandler):
    """Minimal in-process HTTP server that mimics the Synapse gateway."""

    def log_message(self, format, *args):  # silence default access log
        pass

    def _send_json(self, status: int, body: dict):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if self.path == "/api/v1/agent/discovery/search":
            self._send_json(200, {
                "requestId": uuid4().hex,
                "page": 1,
                "pageSize": 10,
                "totalCount": 1,
                "hasMore": False,
                "count": 1,
                "results": [
                    {
                        "serviceId": MOCK_SERVICE_ID,
                        "serviceName": "Market Sentiment API",
                        "summary": "Real-time equity sentiment scoring powered by LLM analysis.",
                        "pricing": {"amount": str(MOCK_SERVICE_PRICE), "currency": "USDC"},
                        "tags": ["market", "sentiment", "finance"],
                        "status": "online",
                        "health": {"overallStatus": "healthy", "healthyTargets": 1, "totalTargets": 1},
                        "invoke": {"method": "POST", "request": {}, "response": {}},
                        "quoteTemplate": {
                            "serviceId": MOCK_SERVICE_ID,
                            "inputPreview": {"contentType": "application/json", "payloadSchema": {"body": {}}, "sample": {"body": {}}},
                            "responseMode": "sync",
                        },
                    }
                ],
            })
        elif self.path == "/api/v1/agent/invoke":
            content_len = int(self.headers.get("Content-Length", 0))
            self.rfile.read(content_len)  # consume body
            self._send_json(200, {
                "invocationId": MOCK_INVOCATION_ID,
                "serviceId": MOCK_SERVICE_ID,
                "status": "SUCCEEDED",
                "costUsdc": str(MOCK_SERVICE_PRICE),
                "result": {
                    "body": {
                        "ticker": "AAPL",
                        "sentiment_score": 0.82,
                        "label": "BULLISH",
                        "source": "Synapse Mock Gateway",
                    }
                },
                "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
        else:
            self._send_json(404, {"detail": "not found"})


def _start_mock_gateway(port: int = 18765) -> tuple[HTTPServer, str]:
    server = HTTPServer(("127.0.0.1", port), _MockGatewayHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, f"http://127.0.0.1:{port}"


# ---------------------------------------------------------------------------
# Demo runner — the actual 3-line pattern
# ---------------------------------------------------------------------------

def run_demo(gateway_url: str, api_key: str, budget_usdc: float = 5.00):
    print("\n" + "=" * 60)
    print("  Synapse Network — Agent Quickstart Demo")
    print("=" * 60)

    # ── Line 1: Create the agent client (AgentWallet equivalent) ──────────
    print(f"\n[1/3] Connecting to gateway: {gateway_url}")
    client = SynapseClient(api_key=api_key, gateway_url=gateway_url)
    print(f"      ✅  SynapseClient ready  |  budget ceiling: ${budget_usdc:.2f} USDC")

    # ── Line 2: Discover a service (MCP-native service search) ────────────
    print("\n[2/3] Discovering services via MCP search query …")
    discovery = client.search_services(query="market sentiment AAPL")
    if not discovery.services:
        raise DiscoveryError("No services returned — check gateway connectivity.")
    service = discovery.services[0]
    print(f"      ✅  Found: '{service.serviceName}'")
    print(f"          serviceId : {service.serviceId}")
    print(f"          price     : ${service.price_usdc} USDC/call")
    print(f"          status    : {service.status}")

    # ── Line 3: Invoke the service — USDC auto-deducted on SUCCEEDED ──────
    print("\n[3/3] Invoking service & deducting USDC …")
    result = client.invoke(
        service.serviceId,
        payload={"ticker": "AAPL", "query": "sentiment today"},
        cost_usdc=float(service.price_usdc),
    )
    print(f"      ✅  Invocation SUCCEEDED")
    print(f"          invocationId : {result.invocation_id}")
    print(f"          cost paid    : ${result.costUsdc} USDC")
    print(f"          status       : {result.status}")
    if result.result:
        body = result.result.get("body") or result.result
        print(f"          response     : {json.dumps(body, ensure_ascii=False)}")

    remaining = round(budget_usdc - float(result.costUsdc), 6)
    print(f"\n      💰  Remaining budget (simulated): ${remaining:.2f} USDC")
    print("\n" + "=" * 60)
    print("  Task Complete. Machine-to-Machine payments — unlocked.")
    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Synapse Network 3-line quickstart demo")
    parser.add_argument("--mock", action="store_true", help="Use in-process mock gateway (no real gateway needed)")
    parser.add_argument("--gateway-url", default=os.getenv("SYNAPSE_GATEWAY", "http://127.0.0.1:8000"))
    parser.add_argument("--api-key", default=os.getenv("SYNAPSE_API_KEY", ""))
    parser.add_argument("--budget", type=float, default=5.00, help="Simulated USDC budget ceiling")
    args = parser.parse_args()

    if args.mock:
        print("🔧  Starting in-process mock gateway …")
        _, gateway_url = _start_mock_gateway()
        api_key = "demo_mock_key"
    else:
        gateway_url = args.gateway_url
        api_key = args.api_key
        if not api_key:
            print("❌  Error: --api-key or SYNAPSE_API_KEY env var is required for live mode.")
            print("    Tip: run with --mock for a zero-dependency local demo.\n")
            raise SystemExit(1)

    try:
        run_demo(gateway_url=gateway_url, api_key=api_key, budget_usdc=args.budget)
    except BudgetExceededError as e:
        print(f"\n⛔  Budget exceeded: {e}")
        raise SystemExit(1)
    except (DiscoveryError, InvokeError) as e:
        print(f"\n❌  Demo failed: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
