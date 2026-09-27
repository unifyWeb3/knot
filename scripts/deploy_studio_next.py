#!/usr/bin/env python3
"""Prepare or execute a Studio Next deployment without handling private keys.

The default mode is a dry run. Use --execute only after the operator has
configured and unlocked the GenLayer CLI account and has reviewed the fee
profile. This script never reads or prints .env values.
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RPC = "https://studio-dev.genlayer.com/api"
CHAIN_ID = 61997
EXPLORER = "https://explorer-studio-dev.genlayer.com"
TARGETS = {
    "knot": ROOT / "contracts" / "knot.py",
    "participant": ROOT / "contracts" / "reference_participant.py",
}


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=sorted(TARGETS))
    parser.add_argument("--execute", action="store_true", help="submit the deployment transaction")
    args = parser.parse_args()

    print(f"TARGET: Studio Next chain {CHAIN_ID}")
    print(f"RPC: {RPC}")
    print(f"EXPLORER: {EXPLORER}")
    print(f"CONTRACT: {TARGETS[args.target].relative_to(ROOT)}")

    if not args.execute:
        print("DRY RUN: no transaction submitted")
        print("Run with --execute only after the CLI account, fees, and source are reviewed.")
        return 0

    cli = shutil.which("genlayer")
    if cli is None:
        print("ERROR: genlayer CLI is not installed or not on PATH", file=sys.stderr)
        return 2
    run([cli, "network", "set", "studio-dev"])
    run([cli, "network", "info"])
    run([cli, "account", "show"])
    run([cli, "deploy", "--contract", str(TARGETS[args.target]), "--rpc", RPC])
    print(f"Verify the finalized deployment at {EXPLORER}/address/<address>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
