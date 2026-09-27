# Project state

## Current status

Knot is implemented in `/home/unify/pavel` as a standalone GenLayer Intelligent Contract primitive: `contracts/knot.py` (blueprint/seal/saga state machine with bounded evidence judgment and reverse compensation) plus `contracts/reference_participant.py`.

## Decisions

- Keep the category as Intelligent Contracts, not Projects.
- Keep the first release frontend-free and backend-free; the contract and deployment/test tooling is the product.
- Use a simple one-word name: **Knot**.
- Target Studio Next / Studio-dev, chain ID `61997`, for the submission proof.
- Use finalized internal messages and an explicit bounded Equivalence Principle validator.
- Treat `.env` as a local secret file; never read, modify, stage, or commit it.

## Validation status

- `genvm-lint check` passes for both contracts (3 lint checks + validation: Knot 8 view/8 write, ReferenceParticipant 3 view/5 write).
- `scripts/preflight.py` passes (32 files scanned; target chain 61997).
- Direct-mode suite: **21 tests pass** (`GENVM_VERSION=v0.6.0-rc5 .venv/bin/pytest tests/direct -q`), covering seal determinism and hash-mutation sensitivity, owner/controller guards, malformed input rejection, evidence re-derivation plus validator disagreement, full success lifecycle with receipts, duplicate-callback no-op, reverse compensation, STUCK + bounded retry budget, and timeout crystallization before late callbacks.
- `contracts/knot.py` bug fixed this session: `DynArray[u256]()` cannot be instantiated in the v0.6 std; the record field is now seeded with `[]` (the record setter accepts a sequence).
- No deployment, transaction, or submission has been performed. No Git remote is configured; nothing has been pushed.

## Next checkpoint

Add integration tests for cross-contract dispatch (the direct runner swallows `execute_step`/`compensate_step` calls), make a local commit checkpoint, then request approval before reading `.env`, signing, or deploying to Studio Next `61997`.
