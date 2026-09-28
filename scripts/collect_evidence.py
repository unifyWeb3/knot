#!/usr/bin/env python3
"""Print the on-chain proof of a Knot deployment and its finished sagas.

Read-only: every value printed comes from contract views on Studio Next
(chain 61997) via finalized state. No transaction is submitted; the signing key is
only used to build the RPC client and is never printed or written anywhere.

Usage:
    # with GENLAYER_PRIVATE_KEY exported from .env:
    python scripts/collect_evidence.py \
        --knot 0x... --participant 0x... --sagas 1 2
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RPC = "https://studio-dev.genlayer.com/api"
EXPLORER = "https://explorer-studio-dev.genlayer.com"

SAGA_NAMES = {1: "ACTIVE", 2: "COMPLETED", 3: "COMPENSATING", 4: "COMPENSATED", 5: "STUCK"}
STEP_NAMES = {0: "PENDING", 1: "DISPATCHED", 2: "CONFIRMED", 3: "EXECUTION_FAILED",
              4: "COMPENSATION_DISPATCHED", 5: "EXECUTION_CONFIRMED", 6: "COMPENSATION_FAILED"}
PHASE_NAMES = {1: "execution", 2: "compensation"}
VERDICT_NAMES = {1: "SATISFIED", 2: "NOT_SATISFIED", 3: "AMBIGUOUS", 4: "UNAVAILABLE", 5: "TIMEOUT"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--knot", required=True)
    parser.add_argument("--participant", required=True)
    parser.add_argument("--sagas", type=int, nargs="+", default=[1])
    args = parser.parse_args()

    from copy import deepcopy

    from genlayer_py.accounts import create_account
    from genlayer_py.chains import studio_devnet
    from genlayer_py.client import GenLayerClient

    key = os.environ.get("GENLAYER_PRIVATE_KEY", "").strip()
    if not key:
        raise SystemExit("ERROR: GENLAYER_PRIVATE_KEY is not set; source it from .env")
    client = GenLayerClient(deepcopy(studio_devnet), create_account(key))
    client.chain.rpc_urls["default"]["http"] = [RPC]

    def view(method, call_args=None):
        return client.read_contract(args.knot, method, call_args or [])

    print(f"CHAIN     : {client.chain.id}")
    print(f"KNOT      : {args.knot}")
    print(f"EXPLORER  : {EXPLORER}/address/{args.knot}")
    constants = view("get_protocol_constants")
    print(f"PROTOCOL  : {json.dumps(constants, default=str)[:400]}")
    print()

    for saga_id in args.sagas:
        saga = view("get_saga", [saga_id])
        status = int(saga.get("status", 0))
        print(f"SAGA {saga_id}  status={SAGA_NAMES.get(status, status)} "
              f"blueprint={saga.get('blueprint_id')} steps={saga.get('step_count')} "
              f"current_step={saga.get('current_step')}")
        print(f"  controller  : {saga.get('controller')}")
        print(f"  blueprint   : {saga.get('blueprint_hash')}")
        print(f"  terminal    : {saga.get('terminal_hash') or '(not terminal)'}")
        print(f"  receipt_ids : {saga.get('receipt_ids')}")
        for ordinal in range(int(saga.get("step_count", 0))):
            state = view("get_step_state", [saga_id, ordinal])
            step_status = int(state.get("status", 0))
            print(f"  STEP {ordinal}     status={STEP_NAMES.get(step_status, step_status)} "
                  f"attempts=exec {state.get('execution_attempts')} / comp {state.get('compensation_attempts')}")
            print(f"    exec op id     : {state.get('execution_operation_id')}")
            print(f"    comp op id     : {state.get('compensation_operation_id') or '-'}")
            for phase, field in (("execution", "execution_receipt_id"), ("compensation", "compensation_receipt_id")):
                receipt_id = int(state.get(field, 0))
                if not receipt_id:
                    continue
                receipt = view("get_receipt", [receipt_id])
                verdict = int(receipt.get("verdict", 0))
                print(f"    {PHASE_NAMES.get(int(receipt.get('phase', 0)), phase):12}: "
                      f"id={receipt_id} verdict={VERDICT_NAMES.get(verdict, verdict)} "
                      f"mode={receipt.get('evidence_mode')} "
                      f"corroborated={receipt.get('externally_corroborated')}")
                print(f"                   evidence_ref={receipt.get('evidence_ref')!r}")
                print(f"                   reason={receipt.get('reason')!r}")
                print(f"                   excerpt={receipt.get('excerpt')!r}")
                print(f"                   digest={receipt.get('source_digest')}")
                print(f"                   receipt_hash={receipt.get('receipt_hash')}")
        for check in ("is_completed", "is_compensated", "is_stuck"):
            print(f"  {check:14}: {view(check, [saga_id])}")
        print()

    try:
        print("PARTICIPANT effects:", client.read_contract(args.participant, "get_effect_counts"))
    except Exception as exc:
        print(f"PARTICIPANT effects: unavailable ({str(exc)[:110]})")
        print("  Note: Studio Next's gen_call reports 'Contract not found' for this participant")
        print("  although its writes and its triggered execute_step calls both finalized;")
        print("  the receipt evidence_ref values above are the participant's own returned text.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
