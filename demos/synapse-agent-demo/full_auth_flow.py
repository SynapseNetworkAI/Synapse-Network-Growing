#!/usr/bin/env python3
"""
Synapse Network — Full Auth Flow Demo
======================================
Shows how a developer goes from a raw private key → credential token → first paid invoke.
This is the "getting started from scratch" path that the 3-line quickstart assumes is done.

Steps demonstrated:
  1.  SynapseAuth.from_private_key()  — wallet-based identity
  2.  auth.authenticate()             — challenge/verify handshake
  3.  auth.issue_credential()         — issue agent API key with optional budget cap
  4.  SynapseClient(api_key=token)    — consumer client
  5.  client.search_services()        — discover available paid APIs
  6.  client.invoke()                 — call + auto-deduct USDC

Run:
    # Requires eth-account (included in synapse-client[dev] or separate install):
    pip install "synapse-client[dev]"
    SYNAPSE_PRIVATE_KEY=0x<key> python full_auth_flow.py

    # Or use the Hardhat local network deployer key (dev environments only):
    python full_auth_flow.py --dev-key

Requirements:
    pip install "synapse-client[dev]"   # pulls in eth-account
"""

from __future__ import annotations

import argparse
import os

# ---------------------------------------------------------------------------
# Ensure eth-account is installed before proceeding
# ---------------------------------------------------------------------------
try:
    from eth_account import Account  # noqa: F401
except ImportError:
    print("❌  eth-account is required for wallet-based auth.")
    print("    Install with:  pip install 'synapse-client[dev]'")
    raise SystemExit(1)

from synapse_client import SynapseAuth, SynapseClient
from synapse_client.exceptions import (
    AuthenticationError,
    BudgetExceededError,
    DiscoveryError,
    InsufficientFundsError,
    InvokeError,
)

# Hardhat default deployer key — safe for local dev networks only.
# Never use this on mainnet or any funded wallet.
_HARDHAT_DEPLOYER_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synapse full auth flow demo")
    parser.add_argument(
        "--gateway-url",
        default=os.getenv("SYNAPSE_GATEWAY", "http://127.0.0.1:8000"),
    )
    parser.add_argument(
        "--private-key",
        default=os.getenv("SYNAPSE_PRIVATE_KEY", ""),
        help="Wallet private key (hex). Defaults to SYNAPSE_PRIVATE_KEY env var.",
    )
    parser.add_argument(
        "--dev-key",
        action="store_true",
        help="Use the Hardhat deployer key (local dev only — never mainnet).",
    )
    parser.add_argument(
        "--credit-limit",
        type=float,
        default=1.0,
        help="USDC credit limit for the issued credential (default: 1.0).",
    )
    parser.add_argument(
        "--query",
        default="sentiment",
        help="Service discovery query.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    private_key = _HARDHAT_DEPLOYER_KEY if args.dev_key else args.private_key
    if not private_key:
        print("❌  Provide --private-key or set SYNAPSE_PRIVATE_KEY, or use --dev-key for local dev.")
        raise SystemExit(1)

    gateway = args.gateway_url

    print("\n" + "=" * 62)
    print("  Synapse Network — Full Auth Flow")
    print("=" * 62)

    # ── Step 1: Create wallet identity ────────────────────────────────────
    print("\n[1/6] Creating wallet identity from private key …")
    try:
        auth = SynapseAuth.from_private_key(private_key, gateway_url=gateway)
    except ImportError as e:
        print(f"❌  {e}")
        raise SystemExit(1)
    print(f"      ✅  Wallet address : {auth.wallet_address}")

    # ── Step 2: Authenticate (challenge/verify) ───────────────────────────
    print("\n[2/6] Authenticating with gateway (challenge/verify) …")
    try:
        owner_token = auth.authenticate()
    except AuthenticationError as e:
        print(f"❌  Auth failed: {e}")
        print("    Ensure your wallet is registered on the gateway.")
        raise SystemExit(1)
    print(f"      ✅  Owner JWT token  : {owner_token[:24]}…")

    # ── Step 3: Issue an agent credential (= the API key) ─────────────────
    print(f"\n[3/6] Issuing agent credential (budget cap: ${args.credit_limit:.2f} USDC) …")
    try:
        cred = auth.issue_credential(
            name="full-auth-demo",
            creditLimit=args.credit_limit,
        )
    except AuthenticationError as e:
        print(f"❌  Credential issuance failed: {e}")
        raise SystemExit(1)
    api_key = cred.token
    print(f"      ✅  Credential token : {api_key[:24]}…")
    print(f"          credential_id  : {cred.credential.credential_id}")
    print()
    print("  ─── Exportable for reuse ────────────────────────────────")
    print(f"  export SYNAPSE_API_KEY={api_key}")
    print("  python quickstart_demo.py  (no re-auth needed)")
    print("  ─────────────────────────────────────────────────────────")

    # ── Step 4: Create consumer client ────────────────────────────────────
    print("\n[4/6] Creating SynapseClient with issued credential …")
    client = SynapseClient(api_key=api_key, gateway_url=gateway)
    print("      ✅  SynapseClient ready")

    # ── Step 5: Discover services ─────────────────────────────────────────
    print(f"\n[5/6] Discovering services (query: '{args.query}') …")
    try:
        discovery = client.search_services(query=args.query)
    except DiscoveryError as e:
        print(f"❌  Discovery failed: {e}")
        raise SystemExit(1)

    if not discovery.services:
        print("⚠️   No services found. Try a different query or check the gateway.")
        raise SystemExit(0)

    print(f"      ✅  {len(discovery.services)} service(s) found:")
    for svc in discovery.services:
        print(f"          • {svc.service_id:<40} ${float(svc.price_usdc):.6f} USDC")

    service = discovery.services[0]

    # ── Step 6: Invoke — USDC deducted on SUCCEEDED ───────────────────────
    cost = float(service.price_usdc)
    print(f"\n[6/6] Invoking '{service.service_id}' (cost: ${cost:.6f} USDC) …")
    try:
        result = client.invoke(
            service.service_id,
            payload={"symbol": "ETH"},
            cost_usdc=cost,
        )
    except InsufficientFundsError as e:
        print(f"⛔  Insufficient funds: {e}")
        print("    Deposit USDC via the gateway admin dashboard to proceed.")
        raise SystemExit(1)
    except BudgetExceededError as e:
        print(f"⛔  Budget exceeded: {e}")
        raise SystemExit(1)
    except InvokeError as e:
        print(f"❌  Invoke failed: {e}")
        raise SystemExit(1)

    print(f"      ✅  status        : {result.status}")
    print(f"          invocationId : {result.invocation_id}")
    print(f"          charged      : ${result.charged_usdc:.6f} USDC")
    if result.result:
        body = result.result.get("body") or result.result
        print(f"          response     : {body}")

    print("\n" + "=" * 62)
    print("  Auth flow complete. SYNAPSE_API_KEY is ready to reuse.")
    print("=" * 62 + "\n")


if __name__ == "__main__":
    main()
