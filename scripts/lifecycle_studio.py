#!/usr/bin/env python3
"""Drive a Knot lifecycle on Studio Next (chain 61997) against deployed contracts.

Nothing is mocked: participant-text evidence, real validators, real LLM
judgments, and every transition is a finalized transaction. Because finalized
internal messages are asynchronous on chain, the saga advances in child
transactions that this script discovers and follows to finalization.

Legs:
  success  - both steps confirm; the saga ends COMPLETED with hashed receipts.
  failure  - step 1's evidence does not establish its criterion, so the step is
             compensated in reverse and the saga ends COMPENSATED.

Dry run by default. ``--execute`` submits the transactions.

Usage:
    # with GENLAYER_PRIVATE_KEY exported from .env:
    python scripts/lifecycle_studio.py \
        --knot 0x... --participant 0x... --leg success --execute
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

TEXT_MODE = 1
STEP_TIMEOUT = 1800

SAGA_ACTIVE, SAGA_COMPLETED, SAGA_COMPENSATING, SAGA_COMPENSATED, SAGA_STUCK = 1, 2, 3, 4, 5
TERMINAL = (SAGA_COMPLETED, SAGA_COMPENSATED, SAGA_STUCK)

LEGS = {
    "success": {
        "title": "Studio Next success lifecycle",
        "purpose": "Two steps whose participant evidence establishes the criterion.",
        "payload": "1",
        "execution_criterion": "The evidence establishes that the reservation is confirmed and active.",
        "compensation_criterion": "The evidence establishes that the reservation was reversed in full.",
    },
    "failure": {
        "title": "Studio Next failure lifecycle",
        "purpose": "A first step whose evidence does not establish the criterion, so it compensates.",
        "payload": "2",
        "execution_criterion": "The evidence establishes that the trip two reservation is confirmed and active.",
        "compensation_criterion": "The evidence establishes that no trip two reservation remains in effect.",
    },
}


def build_client():
    from copy import deepcopy

    from genlayer_py.accounts import create_account
    from genlayer_py.chains import studio_devnet
    from genlayer_py.client import GenLayerClient

    key = os.environ.get("GENLAYER_PRIVATE_KEY", "").strip()
    if not key:
        raise SystemExit("ERROR: GENLAYER_PRIVATE_KEY is not set; source it from .env")
    account = create_account(key)
    config = deepcopy(studio_devnet)
    config.rpc_urls["default"]["http"] = [RPC]
    return GenLayerClient(config, account), account


class Studio:
    def __init__(self, client, account, knot, participant):
        self.client = client
        self.account = account
        self.knot = knot
        self.participant = participant
        self.txs: list[tuple[str, str]] = []

    def write(self, target, method, args, label):
        fees = self.client.estimate_transaction_fees()
        tx = self.client.write_contract(target, method, account=self.account, args=args, fees=fees)
        self.txs.append((label, str(tx)))
        print(f"SUBMIT   : {label}\n           {tx}")
        return self.await_final(tx, label)

    def await_final(self, tx, label, timeout=1200):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                life = self.client.get_transaction_lifecycle(tx)
                detail = json.loads(json.dumps(self.client.get_transaction(tx), default=str))
            except Exception:
                time.sleep(6)
                continue
            if "finalized" in str(life.get("stored_status_name", life)).lower():
                print(f"FINAL    : {label} -> {detail.get('result_name')}")
                return detail
            time.sleep(6)
        raise SystemExit(f"ERROR: {label} did not finalize within {timeout}s")

    def view(self, target, method, args=None, required=True):
        try:
            return self.client.read_contract(target, method, args or [])
        except Exception as exc:
            if required:
                raise
            # Optional evidence reads can fail on Studio Next: gen_call reports
            # "Contract not found" for a participant that demonstrably executed,
            # because its writes and its triggered calls both finalized. Never let
            # that erase the lifecycle evidence already collected above.
            print(f"  (optional read {method} unavailable: {str(exc)[:90]})")
            return None

    def follow_saga(self, saga_id, root_tx, label, timeout=2400):
        """Follow triggered child transactions until the saga is terminal."""
        deadline = time.time() + timeout
        pending = [str(root_tx)]
        while time.time() < deadline:
            saga = self.view(self.knot, "get_saga", [saga_id])
            status = int(saga.get("status", 0))
            print(f"  {label} status={status} current_step={saga.get('current_step')} "
                  f"receipts={len(saga.get('receipt_ids', []))}")
            if status in TERMINAL:
                return saga
            for parent in list(pending):
                try:
                    children = self.client.get_triggered_transaction_ids(parent)
                except Exception:
                    continue
                for child in children or []:
                    child = str(child)
                    if any(child == seen for _, seen in self.txs):
                        continue
                    print(f"  {label} following child {child[:20]}...")
                    detail = self.await_final(child, f"{label} child {child[:12]}")
                    self.txs.append((f"{label} child", child))
                    pending.append(child)
            time.sleep(8)
        raise SystemExit(f"ERROR: {label} saga did not reach a terminal state")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--knot", required=True)
    parser.add_argument("--participant", required=True)
    parser.add_argument("--leg", choices=sorted(LEGS), default="success")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    leg = LEGS[args.leg]
    client, account = build_client()
    studio = Studio(client, account, args.knot, args.participant)

    print(f"CHAIN    : {client.chain.id} (target {CHAIN_ID})")
    print(f"SIGNER   : {account.address}")
    print(f"KNOT     : {args.knot}")
    print(f"PARTICIP : {args.participant}")
    print(f"LEG      : {args.leg}")

    if not args.execute:
        print("DRY RUN: no transaction submitted")
        print(f"PLAN     : create blueprint -> 2 steps (scenario {leg['payload']}) -> seal -> start_saga")
        return 0

    from genlayer_py.types.calldata import CalldataAddress

    participant = CalldataAddress(args.participant)
    blueprint = studio.write(
        args.knot, "create_blueprint", [leg["title"], leg["purpose"]], "create_blueprint"
    )
    # The transaction's "result" field is not reliably the contract's return
    # value, so identify the fresh blueprint by its title instead of trusting it.
    blueprint_id = None
    for candidate in range(1, 12):
        try:
            definition = studio.view(args.knot, "get_blueprint", [candidate])
        except Exception:
            continue
        if definition.get("title") == leg["title"] and int(definition.get("step_count", 0)) == 0:
            blueprint_id = candidate
            break
    if blueprint_id is None:
        raise SystemExit("ERROR: could not identify the freshly created blueprint")
    print(f"BLUEPRINT: {blueprint_id} (tx result field was {blueprint.get('result')})")

    for label in ("flight", "hotel"):
        studio.write(
            args.knot,
            "add_step",
            [
                blueprint_id, participant, label, leg["payload"],
                leg["execution_criterion"], TEXT_MODE, "",
                leg["payload"], leg["compensation_criterion"], TEXT_MODE, "",
                STEP_TIMEOUT,
            ],
            f"add_step({label})",
        )
    studio.write(args.knot, "seal_blueprint", [blueprint_id], "seal_blueprint")

    definition = studio.view(args.knot, "get_blueprint", [blueprint_id])
    print(f"SEALED   : steps={definition.get('step_count')} hash={str(definition.get('blueprint_hash'))[:20]}...")

    started = studio.write(
        args.knot, "start_saga", [blueprint_id, f"trip-{args.leg}"], "start_saga"
    )
    saga_id = None
    for candidate in range(1, 12):
        try:
            probe = studio.view(args.knot, "get_saga", [candidate])
        except Exception:
            continue
        if int(probe.get("blueprint_id", 0)) == blueprint_id:
            saga_id = candidate
            break
    if saga_id is None:
        raise SystemExit("ERROR: could not identify the saga created from this blueprint")
    print(f"SAGA     : {saga_id} (tx result field was {started.get('result')})")

    saga = studio.follow_saga(saga_id, started.get("hash"), f"saga {saga_id}")
    print(f"FINAL    : saga {saga_id} status={saga.get('status')} "
          f"terminal_hash={str(saga.get('terminal_hash'))[:20]}...")

    for ordinal in range(int(saga.get("step_count", 0))):
        state = studio.view(args.knot, "get_step_state", [saga_id, ordinal])
        print(f"STEP {ordinal}  : status={state.get('status')} "
              f"attempts={state.get('execution_attempts')}/{state.get('compensation_attempts')}")
        for phase, key in (("execution", "execution_receipt_id"), ("compensation", "compensation_receipt_id")):
            receipt_id = int(state.get(key, 0))
            if receipt_id:
                receipt = studio.view(args.knot, "get_receipt", [receipt_id])
                print(f"    {phase:12}: id={receipt_id} phase={receipt.get('phase')} "
                      f"verdict={receipt.get('verdict')} corroborated={receipt.get('externally_corroborated')}")
                print(f"                  reason={receipt.get('reason')}")
                print(f"                  excerpt={str(receipt.get('excerpt'))[:90]}")

    print("EFFECTS  :", studio.view(args.participant, "get_effect_counts", required=False))
    for check in ("is_completed", "is_compensated", "is_stuck"):
        print(f"{check:11}:", studio.view(args.knot, check, [saga_id], required=False))
    print("--- transactions ---")
    for label, tx in studio.txs:
        print(f"{label:28} {tx}")
    print(f"EXPLORER : {EXPLORER}/address/{args.knot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
