#!/usr/bin/env python3
"""Deploy a Knot contract to Studio Next (Studio Devnet, chain 61997) via the Python SDK.

The ``genlayer`` CLI cannot sign in this environment: it stores keys in an OS
keychain and reports "OS keychain is not available" on WSL, and it accepts no
private-key environment variable. ``genlayer-py`` signs in-process instead, so
this script reads ``GENLAYER_PRIVATE_KEY`` from the environment (never printing
it), builds the deploy transaction locally, and submits it.

Dry run by default. ``--execute`` submits the transaction.

Usage:
    # with GENLAYER_PRIVATE_KEY exported from .env:
    python scripts/deploy_studio_sdk.py knot --execute
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RPC = "https://studio-dev.genlayer.com/api"
CHAIN_ID = 61997
EXPLORER = "https://explorer-studio-dev.genlayer.com"

TARGETS = {
    "knot": ROOT / "contracts" / "knot.py",
    "participant": ROOT / "contracts" / "reference_participant.py",
}


def build_client():
    from copy import deepcopy

    from genlayer_py.accounts import create_account
    from genlayer_py.chains import studio_devnet
    from genlayer_py.client import GenLayerClient

    key = os.environ.get("GENLAYER_PRIVATE_KEY", "").strip()
    if not key:
        raise SystemExit(
            "ERROR: GENLAYER_PRIVATE_KEY is not set. Source it from .env; "
            "this script never reads .env itself."
        )
    account = create_account(key)
    config = deepcopy(studio_devnet)
    config.rpc_urls["default"]["http"] = [RPC]
    return GenLayerClient(config, account), account


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=sorted(TARGETS))
    parser.add_argument("--execute", action="store_true", help="submit the deploy transaction")
    args = parser.parse_args()

    source = TARGETS[args.target]
    if not source.is_file():
        raise SystemExit(f"ERROR: {source} is missing")

    print(f"TARGET  : Studio Next / Studio Devnet, chain {CHAIN_ID}")
    print(f"RPC     : {RPC}")
    print(f"EXPLORER: {EXPLORER}")
    print(f"CONTRACT: {source.relative_to(ROOT)} ({source.stat().st_size} bytes)")
    print(f"HEADER  : {source.read_text().splitlines()[0][:70]}...")

    client, account = build_client()
    print(f"SIGNER  : {account.address}")
    print(f"CHAIN   : {client.chain.id} (match: {client.chain.id == CHAIN_ID})")
    print(f"NONCE   : {client.get_current_nonce(account.address)}")

    if not args.execute:
        print("DRY RUN: no transaction submitted")
        return 0

    code = source.read_text()
    fees = client.estimate_transaction_fees()
    print("FEES    : " + json.dumps(fees["distribution"], separators=(",", ":")))
    print(f"FEEVAL  : {fees['feeValue']} wei")
    print("SUBMIT  : deploy transaction")
    tx_hash = client.deploy_contract(code=code, account=account, fees=fees)
    print(f"TX      : {tx_hash}")

    deadline = time.time() + 900
    while time.time() < deadline:
        try:
            lifecycle = client.get_transaction_lifecycle(tx_hash)
            detail = json.loads(json.dumps(client.get_transaction(tx_hash), default=str))
        except Exception as exc:  # transient RPC hiccups are expected while polling
            print(f"STATUS  : {type(exc).__name__}: {str(exc)[:100]}")
            time.sleep(8)
            continue
        name = str(lifecycle.get("stored_status_name", lifecycle))
        print(f"STATUS  : {name} (result {detail.get('result_name')})")
        if "finalized" in name.lower():
            print(f"TX      : {tx_hash}")
            print(f"ADDRESS : {detail.get('to_address')}")
            print(f"EXPLORE : {EXPLORER}/address/{detail.get('to_address')}")
            print(f"FEES    : deposit {detail.get('fees', {}).get('deposit')} wei")
            return 0
        time.sleep(8)

    print("ERROR: transaction did not finalize within 15 minutes", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
