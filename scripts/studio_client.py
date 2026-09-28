#!/usr/bin/env python3
"""Shared Studio Next client construction for the deployment and evidence scripts.

Two safety properties live here so all three scripts inherit them:

1. **The signing key can never be printed.** The key is read from the
   environment, shape-checked before use, and every signer error is replaced with
   a fixed message. Some signer paths quote the offending value, so an exception
   is never allowed to reach the terminal unfiltered.
2. **Addresses are EIP-55 normalised before use.** ``gen_call`` matches the
   stored address string exactly, so a mis-cased address resolves to
   "Contract not found" even though the contract demonstrably exists. This bit
   us once: the deploy helper printed a non-checksummed address and every later
   read of that contract failed.
"""
from __future__ import annotations

import os

RPC = "https://studio-dev.genlayer.com/api"
CHAIN_ID = 61997
EXPLORER = "https://explorer-studio-dev.genlayer.com"
KEY_ENV = "GENLAYER_PRIVATE_KEY"
HEX_DIGITS = set("0123456789abcdefABCDEF")


class StudioError(SystemExit):
    """A fatal, already-sanitised error message."""


def load_account():
    """Build a signing account without ever revealing the key."""
    from genlayer_py.accounts import create_account

    raw = os.environ.get(KEY_ENV, "").strip()
    if not raw:
        raise StudioError(f"ERROR: {KEY_ENV} is not set; source it from .env and re-run")
    body = raw[2:] if raw[:2].lower() == "0x" else raw
    if len(body) != 64 or any(character not in HEX_DIGITS for character in body):
        raise StudioError(f"ERROR: {KEY_ENV} is not a 32-byte hex key (value withheld)")
    try:
        return create_account(raw)
    except Exception:
        # Deliberately not re-raising: a signer error may quote the key.
        raise StudioError(f"ERROR: {KEY_ENV} was rejected by the signer (value withheld)")


def checksum(address: str) -> str:
    """Return the EIP-55 checksummed form of an address."""
    from eth_utils import to_checksum_address

    try:
        return to_checksum_address(address)
    except Exception:
        raise StudioError(f"ERROR: {address!r} is not a valid address")


def build_client(rpc: str = RPC):
    """Return ``(client, account)`` for Studio Next."""
    from copy import deepcopy

    from genlayer_py.chains import studio_devnet
    from genlayer_py.client import GenLayerClient

    account = load_account()
    config = deepcopy(studio_devnet)
    config.rpc_urls["default"]["http"] = [rpc]
    return GenLayerClient(config, account), account
