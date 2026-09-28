# Knot

**Knot** is a reusable GenLayer Intelligent Contract primitive for evidence-gated, multi-step workflows with deterministic reverse compensation.

Knot lets a builder define an immutable ordered workflow, dispatch participant Intelligent Contracts asynchronously, independently verify semantic evidence through GenLayer consensus, and compensate completed steps in reverse order when a later step cannot be verified.

> Status: deployed to Studio Next / Studio-dev (chain `61997`) with both lifecycles
> proven on-chain. No hackathon submission has been made yet.

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
 state/                    Project checkpoints and handoff notes
```

## Deployment on Studio Next

Deployed to Studio Next / Studio-dev, chain `61997`, RPC
`https://studio-dev.genlayer.com/api`, from account
`0x3211d1419709682b81c53cc51cb63622e25488d3`.

| Contract | Address | Deploy tx | Result |
| --- | --- | --- | --- |
| Knot | [`0xDFCd787F4E8048d29602ebd09b2B2B91f3E97C2B`](https://explorer-studio-dev.genlayer.com/address/0xDFCd787F4E8048d29602ebd09b2B2B91f3E97C2B) | `0xec1c79b4b5b9cc9c0e1b765c200ff10cbd63e56b2730a258504652983b1ffba6` | `MAJORITY_AGREE`, finalized |
| ReferenceParticipant | [`0x1131BB787287392a8d1E19F5bc5C76719296E433`](https://explorer-studio-dev.genlayer.com/address/0x1131BB787287392a8d1E19F5bc5C76719296E433) | `0x6a4f067b4660e42453497fb50f2c49840c116fe90f58254bdafa94566fdaec4c` | `MAJORITY_AGREE`, finalized |

Fee profile actually used, derived from the chain's fee policy
(`leaderTimeunitsAllocation 100`, `validatorTimeunitsAllocation 200`,
`rotations [3]`, `maxPriceGenPerTimeUnit 2`, caps `300000000`): fee deposit
`100000000000010352` wei per transaction.

### Lifecycle 1 — success, `COMPLETED`

Two steps, participant-text evidence, real validators, real model judgments. The
saga advanced through **asynchronous finalized child transactions**, which is the
behaviour the simulator could not prove.

| Receipt | Phase | Verdict | Excerpt |
| --- | --- | --- | --- |
| 1 | execution | `SATISFIED` | `Reservation H-100 is confirmed and active.` |
| 2 | execution | `SATISFIED` | `Reservation H-100 is confirmed and active.` |

Terminal hash `4f9ff0347db777fd22bd88607b357c599ad9e383ccf48e45052090ac357bde08`.

### Lifecycle 2 — failure, `COMPENSATED`

Step 1's evidence did not establish its criterion, so the step compensated in
reverse and the saga ended `COMPENSATED`; step 2 was never dispatched.

| Receipt | Phase | Verdict | Reason returned by the network's models |
| --- | --- | --- | --- |
| 3 | execution | `NOT_SATISFIED` | "…the reservation request for trip two was declined and that no booking exists, which contradicts confirmation and active status." |
| 4 | compensation | `SATISFIED` | "…trip two has no reservation, which materially establishes that no trip two reservation remains in effect." |

Terminal hash `e76c547f920ac3bf5eed...`; both receipts are
`externally_corroborated = false`, which is correct for participant-text
evidence and is the claim the round-2 review asked us to make honest.

Reproduce any of it read-only:

```bash
# export GENLAYER_PRIVATE_KEY from .env first; the key is never printed
python scripts/collect_evidence.py \
    --knot 0xDFCd787F4E8048d29602ebd09b2B2B91f3E97C2B \
    --participant 0x1131BB787287392a8d1E19F5bc5C76719296E433 --sagas 1 2
```

### Deployment notes, including what did not go to plan

- **The `genlayer` CLI cannot sign on this host.** It keeps keys in an OS
  keychain and reports `OS keychain is not available` under WSL, and it accepts
  no private-key environment variable. `scripts/deploy_studio_sdk.py` and
  `scripts/lifecycle_studio.py` therefore drive the network with `genlayer-py`,
  which signs in-process. Both scripts are dry-run by default and take
  `--execute`; neither ever prints the key.
- **`studio-dev` only exists in the `0.40.0-rc.3` CLI.** The `latest` CLI
  (`0.39.2`) knows only `studionet`, which is a different chain (`61999`).
- **A deploy needs an explicit fee distribution**, otherwise the consensus
  contract reverts with `FeesDistributionMissing`. Both scripts call
  `estimate_transaction_fees()` first.
- **One orphaned participant contract exists.** An earlier deploy (account nonce
  243) was submitted by a script whose status-polling bug discarded the
  transaction hash before printing it, and this node offers neither address
  derivation nor a usable block-receipt index to recover it. It is unused; the
  address above is the live participant. An empty blueprint (`id 2`) is likewise
  left over from that same interrupted run.
- **The script's blueprint-id lookup was a real bug** and is now fixed
  fail-closed: the transaction `result` field is not reliably the contract's
  return value, so the script identifies the fresh blueprint by title and
  verifies `step_count == 0` before adding steps.
- **`gen_call` cannot read the participant** (`Contract not found`) even though
  its writes and its triggered `execute_step` calls both finalized; the receipt
  `evidence_ref` values are the participant's own returned text. The evidence
  collector treats that read as optional and says so.

## Testing

Both suites run offline against the pinned Consensus v0.6 runtime; neither
submits a transaction or reads `.env`.

```bash
# 50 state-machine, seal/hash, guard, evidence, judge-seam, and validator tests
GENVM_VERSION=v0.6.0-rc6 pytest tests/direct -q

# 5 cross-contract lifecycle tests on the local GenLayer simulator (glsim)
GENVM_VERSION=v0.6.0-rc6 pytest tests/integration -q
```

`tests/direct/test_knot_evidence_adversarial.py` attacks the judge seam
directly: fenced and prose-wrapped replies, truncated and undecodable JSON,
wrong field types, forged digests, oversized fields, prompt injection in the
source, and leader/validator disagreement. The evidence destination filter and
the receipt corroboration flag each have their own regression test.

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
| `test_participant_only_accepts_dispatches_from_its_pinned_coordinator` | the **reference participant** rejects a dispatcher that is not its pinned coordinator, before any effect — that guard lives in the participant, not in Knot |

These tests prove the state machine *reaches* those states. glsim drains emitted
messages inside the calling transaction, so a whole two-step saga completes
within one `start_saga` call here; on Studio Next the same steps are asynchronous
child transactions, `start_saga` returns with the saga merely `ACTIVE`, and the
deadline, late-callback, and retry-budget behaviour become time-dependent.

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

### What the tests do not prove

Stated explicitly so the evidence is not read as stronger than it is.

- **A validator halt is not shown end to end.** In direct mode `run_nondet`
  returns the leader's value and captures the validator for later inspection, so
  the suites assert the validator's own vote (`run_validator()` is `False` on a
  different verdict, a divergent source digest, or a malformed leader result)
  rather than a saga refusing to advance. On chain the runtime drops a
  transaction whose validators do not agree, and that is what makes the gate
  fail closed; that step is verified by the deployment run, not by these suites.
- **The simulator runs a single validator**, so validator agreement in
  `tests/integration` is trivially satisfied. Multi-validator consensus, leader
  rotation, and the fee profile of multi-hop finalized messages are observable
  only on the target network.
- **Prompt-injection resistance is tested against a mocked model.** The tests
  show how the contract handles a compromised leader — independent
  re-derivation plus excerpt and digest binding — not that a live model resists
  injection, as `docs/THREAT_MODEL.md` also notes.
- **The evidence destination filter is bounded.** It rejects loopback,
  link-local, RFC1918, unique-local, non-routable, integer-form, and
  single-label hosts, and requires a directory prefix so the authority cannot be
  extended by a participant. It does not follow redirects, resolve DNS, or model
  resolver behaviour, so it is not complete SSRF protection.

## Development status

See [`state/PROJECT-STATE.md`](state/PROJECT-STATE.md) and [`state/LEFT-OFF.md`](state/LEFT-OFF.md) for the current checkpoint and next action.

## Security

The repository must never contain a private key, API key, or real `.env` file. Public evidence is untrusted input. The contract must fail closed and must never treat a valid-looking model response as proof without independent validator work.
