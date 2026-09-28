# Project state

## Current status

Knot is implemented in `/home/unify/pavel` as a standalone GenLayer Intelligent Contract primitive: `contracts/knot.py` (blueprint/seal/saga state machine with bounded evidence judgment and reverse compensation) plus `contracts/reference_participant.py`. It is **deployed to Studio Next / Studio-dev (chain `61997`)** with both lifecycles proven on-chain, and pushed to the private repository `unifyWeb3/knot` (branch `main`).

## Decisions

- Keep the category as Intelligent Contracts, not Projects.
- Keep the first release frontend-free and backend-free; the contract and deployment/test tooling is the product.
- Use a simple one-word name: **Knot**.
- Target Studio Next / Studio-dev, chain ID `61997`, for the submission proof.
- Use finalized internal messages and an explicit bounded Equivalence Principle validator.
- Treat `.env` as a local secret file; never read, modify, stage, or commit it.

## Validation status

- `genvm-lint check` passes for both contracts (3 lint checks + validation: Knot 8 view/8 write, ReferenceParticipant 3 view/5 write).
- `scripts/preflight.py` passes; the scanned-file count is now stable because generated trees (`artifacts/`, `.pytest_cache/`) are skipped, while dotfiles are still scanned for secret hygiene.
- Direct-mode suite: **50 tests pass** (`GENVM_VERSION=v0.6.0-rc5 .venv/bin/pytest tests/direct -q`) — 10 blueprint, 2 evidence, 29 adversarial judge-seam, 6 saga lifecycle, 3 reference-participant.
- Integration suite: **5 tests pass** (`GENVM_VERSION=v0.6.0-rc5 .venv/bin/pytest tests/integration -q`) on glsim in-process, proving the cross-contract round trip that direct mode cannot execute: success lifecycle with hashed receipts and terminal hash, failed execution → reverse compensation, failed compensation → `STUCK` with 3 bounded retries that reuse one operation ID while the participant effect count stays at 1, deadline crystallization of an unanswered compensation plus late-callback rejection, and coordinator-pinned dispatch rejection.
- `contracts/knot.py` bug fixed earlier: `DynArray[u256]()` cannot be instantiated in the v0.6 std; the record field is now seeded with `[]`.
- `contracts/knot.py` judge switched to `exec_prompt(response_format="text")` + `_v_parse_decision` so one parser serves every runtime; gltest's mock layer auto-parses bare JSON strings, which the JSON path rejects and which made mocked SATISFIED verdicts impossible on glsim.

### Review round 2 adjudication (`state/REVIEW_ROUND2.md`)

Every finding was reproduced before it was acted on.

| Finding | Verdict | Action |
| --- | --- | --- |
| P1-1 no local/private destination filter | confirmed | `_v_public_https_host` rejects loopback, link-local, RFC1918, CGNAT, unique-local, multicast/reserved/documentation ranges, integer-form addresses, and local/internal names; the prefix must be a directory so `ref.startswith(prefix)` pins the authority. Regression tests added. |
| P1-2 `externally_corroborated` true on timeout receipts | confirmed | Derived from `mode == PUBLIC_URL and evidence_ref != ""`; regression test asserts both directions (verified fetch → `True`, timeout → `False`). |
| P1-3 direct mode returns the leader's value | partially confirmed | Real harness limitation, not a contract defect. Partially refuted as stated: `tests/direct/test_knot_evidence.py` and the adversarial suite already assert `run_validator() is False`, so the suite is not green with a broken validator. The saga-halting consequence is documented in README "What the tests do not prove" instead of being claimed. |
| P1-4 single-validator simulator | confirmed as a limit | No offline fix: glsim's `call_method` path bypasses consensus entirely, so validator count only matters for the signed-transaction path. Recorded as a known gap. |
| P1-5 synchronous drain | confirmed | README proof table now states that the simulator drains inside the calling transaction and that on chain the same steps are async child transactions. |
| P2-1 `run_nondet_unsafe` | **refuted** | It does not exist in the pinned std; the sandboxing variant is `run_nondet_default`, and `run_nondet`'s un-sandboxed `Disagree`-on-error behaviour is the fail-closed one we want. No code change; documented in `docs/CONSENSUS.md`. |
| P2-2 wrong comment on malformed output | confirmed | Comment corrected: no decodable object → `AMBIGUOUS`; undecodable object or executor error → `UNAVAILABLE`. |
| P2-3 dead `MAX_REASON_JSON` | confirmed | Removed. |
| P2-4 unstable preflight count | confirmed | Generated trees skipped. |
| P2-5 CI gaps | confirmed | Integration job now also runs preflight and `compileall`. CI has still never executed (no remote). |
| P2-6 validator fetched the source twice | confirmed | The validator now checks the excerpt against the source its own re-derivation just read, removing one fetch per judgment and the disagreement a mutating source would cause. |

- No deployment, transaction, or submission has been performed. No Git remote is configured; nothing has been pushed.

## Deployment

- Knot: `0xDFCd787F4E8048d29602ebd09b2B2B91f3E97C2B`, deploy tx `0xec1c79b4…b1ffba6`, `MAJORITY_AGREE`, finalized.
- ReferenceParticipant: `0x1131BB787287392a8d1E19F5bc5C76719296E433`, deploy tx `0x6a4f067b…fdaec4c`, `MAJORITY_AGREE`, finalized.
- Fee profile from the chain policy: leader 100 / validator 200 timeunits, `rotations [3]`, `maxPriceGenPerTimeUnit 2`, caps `300000000`, deposit `100000000000010352` wei per transaction.
- **Saga 1 = `COMPLETED`** (blueprint 1, 2 steps): receipts 1 and 2 both `SATISFIED` with verbatim excerpts from the participant's text, distinct receipt hashes, terminal hash `4f9ff034…`. The saga advanced through asynchronous finalized child transactions.
- **Saga 2 = `COMPENSATED`** (blueprint 3, 2 steps): execution receipt 3 `NOT_SATISFIED` (the model cited the contradiction in the source), compensation receipt 4 `SATISFIED`, terminal hash `e76c547f…`, step 1 never dispatched. Both receipts `externally_corroborated = false`, correct for participant-text evidence.
- Reproduce read-only with `scripts/collect_evidence.py --sagas 1 2`.
- CI on the two pushed commits: run `36395836769` (`dc1504c`) passed both jobs; run `36423309694` (`3517731`, the deployment commit) passed `direct-runtime` but **failed** `integration` during `pip install` with a PyPI `ReadTimeoutError` — a registry flake, not a dependency defect. Both jobs now install with `--retries 5 --timeout 60`, and the claim is re-verified on each push rather than assumed.
- Known artefacts of the deployment run: one orphaned participant contract (nonce 243, address unrecoverable), one empty blueprint (`id 2`), and the success leg's blueprint carrying a different title than the current script generates (saga 1 is readable but not re-creatable). All disclosed in `README.md`.
- The round-3 review's address-checksum finding removed a **false** disclosure: the participant read is available and carries the on-chain idempotency proof (four operations, `calls = 1` each; `{'execution_effects': 3, 'compensation_effects': 1}`). Addresses are now EIP-55 normalised in `scripts/studio_client.py`.

## Next checkpoint

Package the submission: confirm the live submission event and category, then hand the reviewer session the deployed addresses, transaction hashes, and explorer links so it can verify the on-chain evidence independently before anything is submitted.
