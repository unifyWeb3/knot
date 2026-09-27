# Knot

**Knot** is a reusable GenLayer Intelligent Contract primitive for evidence-gated, multi-step workflows with deterministic reverse compensation.

Knot lets a builder define an immutable ordered workflow, dispatch participant Intelligent Contracts asynchronously, independently verify semantic evidence through GenLayer consensus, and compensate completed steps in reverse order when a later step cannot be verified.

> Status: implementation foundation. No deployment or submission is claimed yet.

## Why GenLayer?

A conventional Saga engine can sequence actions and issue compensating actions. It cannot, by itself, establish whether an external participant actually completed a natural-language postcondition or whether a compensation really removed the effect. Knot keeps deterministic workflow state on-chain and uses the GenLayer Equivalence Principle only for that bounded semantic decision.

## Scope

Knot is intentionally a contract primitive, not a frontend product.

Included in the first release:

- immutable workflow blueprints;
- ordered participant dispatch;
- finalized internal messages;
- evidence modes with independent leader/validator checking;
- reverse compensation and explicit `STUCK` recovery;
- stable operation IDs and participant idempotency guidance;
- direct tests and one Studio Next reviewer demo.

Intentionally out of scope for the first release:

- a web frontend or product dashboard;
- automatic compensation generation;
- arbitrary off-chain API credentials;
- a general-purpose workflow engine;
- automatic discovery of the correct compensation action.

## Target environment

The submission target is Studio Next / Studio-dev:

- RPC: `https://studio-dev.genlayer.com/api`
- chain ID: `61997`
- explorer: `https://explorer-studio-dev.genlayer.com`

The project uses the Consensus v0.6 / Studio v0.123 release-candidate family as one coherent toolchain. Contracts are pinned to the published GenVM v0.6.0-rc6 `py-genlayer` runner. The first milestone is a successful Studio Next deployment and lifecycle proof, not a polished UI.

## Repository layout

```text
contracts/                 Core Intelligent Contract and reference participant
 docs/                     Architecture, consensus, integration, and demo notes
 tests/direct/             Fast state-machine and validator tests
 tests/integration/        Cross-contract lifecycle tests on the local simulator
 scripts/                  Preflight, deployment, and evidence helpers
 fixtures/                 Commit-pinned public evidence fixtures
 state/                    Project checkpoints and handoff notes
```

## Testing

Both suites run offline against the pinned Consensus v0.6 runtime; neither
submits a transaction or reads `.env`.

```bash
# 21 state-machine, seal/hash, guard, evidence, and validator tests
GENVM_VERSION=v0.6.0-rc6 pytest tests/direct -q

# 5 cross-contract lifecycle tests on the local GenLayer simulator (glsim)
GENVM_VERSION=v0.6.0-rc6 pytest tests/integration -q
```

The integration suite deploys Knot and the reference participant on glsim and
drives the real round trip — `start_saga` emits `execute_step`, the participant
answers with `report_execution`, and Knot's judgment decides the next
transition:

| Test | Proves |
| --- | --- |
| `test_success_lifecycle_completes_saga` | both steps confirm, receipts are hashed, terminal hash is set, one effect per step |
| `test_failed_execution_runs_reverse_compensation` | failed evidence verdict triggers compensation in reverse and ends `COMPENSATED` |
| `test_failed_compensation_parks_stuck_and_exhausts_retry_budget` | `STUCK` after 3 attempts, retries reuse the operation ID, participant effect count stays at 1 |
| `test_timeout_crystallizes_an_unanswered_compensation` | an unanswered callback crystallizes on deadline; a late callback is rejected |
| `test_participant_only_accepts_dispatches_from_its_pinned_coordinator` | foreign dispatchers are rejected before any effect |

Three documented compatibility shims bridge glsim to the pinned std lib; they
live in `tests/integration/conftest.py` and touch the simulator only, never the
contracts:

1. the std lib encodes an emitted method name under `""` while glsim reads
   `calldata["method"]`;
2. RPC addresses are host-side `CalldataAddress` objects while the guest encoder
   only accepts `genlayer.types.Address`;
3. glsim never refreshes `genlayer.message.raw["datetime"]`, so the harness
   publishes the simulated clock before each call.

The local checkpoint cache resolves `GENVM_VERSION=v0.6.0-rc5`; rc5 and rc6 ship
the same pinned runner (`5jycge…`) and std-lib hash (`kzr02…`), so behavior is
identical. CI runs both suites under `v0.6.0-rc6`.

## Development status

See [`state/PROJECT-STATE.md`](state/PROJECT-STATE.md) and [`state/LEFT-OFF.md`](state/LEFT-OFF.md) for the current checkpoint and next action.

## Security

The repository must never contain a private key, API key, or real `.env` file. Public evidence is untrusted input. The contract must fail closed and must never treat a valid-looking model response as proof without independent validator work.
