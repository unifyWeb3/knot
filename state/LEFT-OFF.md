# Left off

## Next action

Package the submission for Knot: confirm the live submission event and category, then hand the reviewer session the deployed addresses, transaction hashes, and explorer links so it verifies the on-chain evidence independently before anything is submitted.

## Verified this session

- `GENVM_VERSION=v0.6.0-rc5 .venv/bin/pytest tests/direct -q` → 50 passed.
- `GENVM_VERSION=v0.6.0-rc5 .venv/bin/pytest tests/integration -q` → 5 passed.
- `genvm-lint check` on both contracts → pass; `scripts/preflight.py` → pass; `compileall` clean.
- First CI run on `main`: `direct-runtime` and `integration` both **succeeded** under `v0.6.0-rc6`.
- Deployed to Studio Next (chain `61997`): Knot `0xDFCd787F4E8048d29602ebd09b2B2B91f3E97C2B`, ReferenceParticipant `0x1131BB787287392a8d1E19F5bc5C76719296E433`, both `MAJORITY_AGREE` and finalized, fee deposit `100000000000010352` wei each.
- **Saga 1 `COMPLETED`** (receipts 1 and 2, both `SATISFIED`, terminal hash `4f9ff034…`).
- **Saga 2 `COMPENSATED`** (receipt 3 `NOT_SATISFIED`, receipt 4 `SATISFIED`, terminal hash `e76c547f…`, step 1 never dispatched).
- Review round 2 (`state/REVIEW_ROUND2.md`) adjudicated: P1-1 and P1-2 fixed with regression tests, P1-5 and P1-3/P1-4 documented as limits, P2-1 refuted against the pinned std, P2-2/P2-3/P2-4/P2-5/P2-6 fixed.

## Disclosed rough edges

- One orphaned participant contract (nonce 243) whose address could not be recovered, and one empty blueprint (`id 2`), both from an interrupted deploy run with a status-polling bug. Neither is referenced by either proven saga.
- `scripts/lifecycle_studio.py` originally trusted a transaction's `result` field as the contract return value, which put the success leg's steps on the wrong blueprint. Fixed fail-closed (identify by title, verify `step_count == 0`).
- `gen_call` cannot read the participant contract on Studio Next, although its writes and triggered calls finalized. `scripts/collect_evidence.py` treats that read as optional and says why.

## Constraints

- Do not read, print, modify, stage, or commit `.env`.
- Do not copy the third-party Recoil implementation.
- No further deployment or signing without explicit approval (Batch A and Batch B are spent).
- Do not initialize a frontend or product backend for this track.

## Open decisions

- The live submission event and category are still unconfirmed and are the user's call.
- Whether the reviewer session should verify the on-chain evidence before or after the submission package is drafted.
- Whether the glsim compatibility shims (calldata method key, host→guest address type, block datetime) should be upstreamed to `genlayerlabs/genlayer-testing-suite`; they live only in `tests/integration/conftest.py` and never touch contract code.
- Whether a multi-validator disagreement test is worth building on glsim's signed-transaction path; the Studio Next run exercised real validators for the happy and compensation paths, but not a disagreement.
