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
- `scripts/preflight.py` passes (34 files scanned; target chain 61997).
- Direct-mode suite: **21 tests pass** (`GENVM_VERSION=v0.6.0-rc5 .venv/bin/pytest tests/direct -q`), covering seal determinism and hash-mutation sensitivity, owner/controller guards, malformed input rejection, evidence re-derivation plus validator disagreement, full success lifecycle with receipts, duplicate-callback no-op, reverse compensation, STUCK + bounded retry budget, and timeout crystallization before late callbacks.
- Integration suite: **5 tests pass** (`GENVM_VERSION=v0.6.0-rc5 .venv/bin/pytest tests/integration -q`) on glsim in-process, proving the cross-contract round trip that direct mode cannot execute: success lifecycle with hashed receipts and terminal hash, failed execution → reverse compensation, failed compensation → `STUCK` with 3 bounded retries that reuse one operation ID while the participant effect count stays at 1, deadline crystallization of an unanswered compensation plus late-callback rejection, and coordinator-pinned dispatch rejection.
- `contracts/knot.py` bug fixed this session: `DynArray[u256]()` cannot be instantiated in the v0.6 std; the record field is now seeded with `[]` (the record setter accepts a sequence).
- `contracts/knot.py` judge switched to `exec_prompt(response_format="text")` + `_v_parse_decision` so one parser serves every runtime; gltest's mock layer auto-parses bare JSON strings, which the JSON path rejects and which made mocked SATISFIED verdicts impossible on glsim.
- CI (`.github/workflows/ci.yml`) runs preflight, compileall, `genvm-lint`, and the direct suite under `v0.6.0-rc6`, plus a second job for the glsim integration suite (`requirements-integration.txt`). CI has not yet been exercised because no push has occurred.
- No deployment, transaction, or submission has been performed. No Git remote is configured; nothing has been pushed.

## Next checkpoint

Request approval to read `.env`, configure the Git remote, and sign a transaction; then deploy both contracts to Studio Next `61997`, prove both lifecycles there, and capture receipts, fee profile, and explorer evidence.
