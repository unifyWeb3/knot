# Left off

## Next action

Request approval to read `.env`, configure the `unifyWeb3/knot` Git remote, and sign transactions; then deploy `contracts/knot.py` and `contracts/reference_participant.py` to Studio Next `61997`, prove both lifecycles on-chain, and capture receipts, fee profile, and explorer links.

## Verified this session

- `GENVM_VERSION=v0.6.0-rc5 .venv/bin/pytest tests/direct -q` → 50 passed.
- `GENVM_VERSION=v0.6.0-rc5 .venv/bin/pytest tests/integration -q` → 5 passed (glsim in-process, full cross-contract round trip).
- `genvm-lint check contracts/knot.py` and `genvm-lint check contracts/reference_participant.py` → pass.
- `python scripts/preflight.py` → pass.
- Review round 2 (`state/REVIEW_ROUND2.md`) adjudicated: P1-1 and P1-2 fixed with regression tests, P1-5 and P1-3/P1-4 documented as limits, P2-1 refuted against the pinned std, P2-2/P2-3/P2-4/P2-5/P2-6 fixed.
- Contract changes this session: judge in text mode, evidence destination filter, directory-prefix rule, receipt corroboration flag, single-fetch validator, dead constant removed.
- Local commits `137ff42`, `f690083`, plus this follow-up checkpoint; no remote configured, nothing pushed.

## Constraints

- Do not read or modify `.env`.
- Do not copy the third-party Recoil implementation.
- Do not deploy, sign transactions, configure a Git remote, or push anything without explicit approval.
- Do not initialize a frontend or product backend for this track.

## Open decisions

- Whether the authoritative review rubric requires any reviewer-facing UX; the current IC rubric text does not require a product frontend, so no frontend is planned unless the live submission form says otherwise.
- Whether v2 should add a new corrective-operation ID for partial compensation; v1 keeps revalidation-only retries.
- Whether a later version should support delegated controllers or permissionless open blueprints.
- Target deployment event window and submission category still need confirmation before any live transaction.
- Whether the glsim compatibility shims (calldata method key, host→guest address type, block datetime) should be upstreamed to `genlayerlabs/genlayer-testing-suite`; they live only in `tests/integration/conftest.py` and never touch contract code.
- Whether a multi-validator disagreement test is worth building on glsim's signed-transaction path, which is the only way to exercise real consensus offline; the deployment run is expected to cover it instead.
