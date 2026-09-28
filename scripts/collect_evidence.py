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
STEP_NAMES = {0: "PENDING", 1: "EXECUTION_DISPATCHED", 2: "CONFIRMED", 3: "EXECUTION_FAILED",
              4: "COMPENSATION_DISPATCHED", 5: "COMPENSATED", 6: "COMPENSATION_FAILED"}
PHASE_NAMES = {1: "execution", 2: "compensation"}
VERDICT_NAMES = {1: "SATISFIED", 2: "NOT_SATISFIED", 3: "AMBIGUOUS", 4: "UNAVAILABLE", 5: "TIMEOUT"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--knot", required=True)
    parser.add_argument("--participant", required=True)
    parser.add_argument("--sagas", type=int, nargs="+", default=[1])
    parser.add_argument(
        "--allow-missing-participant",
        action="store_true",
        help="do not fail when the participant read is unavailable",
    )
    args = parser.parse_args()

    from studio_client import build_client, checksum

    client, account = build_client()
    knot = checksum(args.knot)
    participant = checksum(args.participant)

    def view(method, call_args=None):
        return client.read_contract(knot, method, call_args or [])

    print(f"CHAIN     : {client.chain.id}")
    print(f"KNOT      : {knot}")
    print(f"EXPLORER  : {EXPLORER}/address/{knot}")
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

    # The participant read carries the on-chain idempotency proof, so it is
    # required by default; a silent skip here would erase the best evidence we
    # have. Pass --allow-missing-participant only when diagnosing that read itself.
    try:
        effects = client.read_contract(participant, "get_effect_counts")
        print(f"PARTICIPANT: {participant}")
        print(f"  effects   : {effects}")
        for saga_id in args.sagas:
            saga = view("get_saga", [saga_id])
            for ordinal in range(int(saga.get("step_count", 0))):
                state = view("get_step_state", [saga_id, ordinal])
                for field in ("execution_operation_id", "compensation_operation_id"):
                    operation_id = state.get(field)
                    if not operation_id:
                        continue
                    record = client.read_contract(participant, "get_operation", [operation_id])
                    print(f"  operation : {field:26} calls={record.get('calls')} "
                          f"scenario={record.get('scenario_id')} evidence={str(record.get('evidence_ref'))[:60]!r}")
    except Exception as exc:
        message = str(exc)[:110]
        if args.allow_missing_participant:
            print(f"PARTICIPANT: unavailable, and --allow-missing-participant was passed ({message})")
        else:
            print(f"PARTICIPANT: read failed ({message})", file=sys.stderr)
            print("  This read carries the idempotency proof. Pass --allow-missing-participant", file=sys.stderr)
            print("  only when diagnosing the read itself. Check the address checksum first.", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
