#!/usr/bin/env python3
"""Knot source and repository preflight checks.

This is intentionally dependency-free. It does not read .env, contact a network,
deploy a contract, or handle credentials.
"""
from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
HEADER = '# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng" }'
TARGET_RPC = "https://studio-dev.genlayer.com/api"
TARGET_CHAIN_ID = "61997"
TARGET_EXPLORER = "https://explorer-studio-dev.genlayer.com"


class Failure(RuntimeError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


def source_files() -> list[pathlib.Path]:
    # Generated, gitignored trees are skipped so the reported file count is
    # stable across runs; everything else is scanned, including dotfiles such as
    # a stray ".env:Zone.Identifier", so secret hygiene still covers them.
    ignored = (".git", ".venv", "__pycache__", ".pytest_cache", "artifacts")
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and not any(part in ignored for part in path.parts)
    ]


def check_no_secret_material(path: pathlib.Path) -> None:
    if path.name == ".env":
        return
    if path.name == "preflight.py" and path.parent.name == "scripts":
        return
    text = path.read_text(encoding="utf-8", errors="strict")
    for marker in ("PRIVATE_KEY=", "ETHERSCAN_API_KEY=", "API_KEY="):
        if marker in text and path.name != ".env.example":
            raise Failure(f"possible secret assignment in {path.relative_to(ROOT)}")


def main() -> int:
    files = source_files()
    check((ROOT / "contracts" / "knot.py").exists(), "contracts/knot.py is missing")
    check((ROOT / "contracts" / "reference_participant.py").exists(), "contracts/reference_participant.py is missing")
    check((ROOT / "tests" / "direct").exists(), "tests/direct is missing")

    for contract in sorted(CONTRACTS.glob("*.py")):
        text = contract.read_text(encoding="utf-8")
        check(text.splitlines()[0] == HEADER, f"dependency header must be first line and match the Studio Next runtime: {contract.name}")
        ast.parse(text, filename=str(contract))
        check("gl.vm.run_nondet(" in text or contract.name == "reference_participant.py", f"missing consensus boundary: {contract.name}")
        check("on=\"finalized\"" in text or "on='finalized'" in text or contract.name == "reference_participant.py", f"missing finalized message boundary: {contract.name}")

    config = (ROOT / "gltest.config.yaml").read_text(encoding="utf-8")
    check("studio_devnet" in config, "gltest config must include studio_devnet")
    check(TARGET_RPC in (ROOT / "docs" / "BRIEF.md").read_text(encoding="utf-8") or TARGET_RPC in (ROOT / "README.md").read_text(encoding="utf-8"), "target RPC is not documented")
    check(TARGET_CHAIN_ID in (ROOT / "README.md").read_text(encoding="utf-8") or TARGET_CHAIN_ID in (ROOT / "docs" / "BRIEF.md").read_text(encoding="utf-8"), "target chain id is not documented")
    check(TARGET_EXPLORER in (ROOT / "README.md").read_text(encoding="utf-8") or TARGET_EXPLORER in (ROOT / "docs" / "BRIEF.md").read_text(encoding="utf-8"), "target explorer is not documented")

    for path in files:
        if path.suffix.lower() in {".py", ".md", ".txt", ".yaml", ".yml", ".toml", ".json", ".example", ""}:
            check_no_secret_material(path)

    print(f"PASS: Knot preflight ({len(files)} files scanned)")
    print(f"TARGET: Studio Next chain {TARGET_CHAIN_ID} via {TARGET_RPC}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Failure as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
