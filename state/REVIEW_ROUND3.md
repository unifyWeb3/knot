# Independent review — round 3 (on-chain evidence audit)

Reviewer session, 2026-09-28. Read-only review of `3517731` (deployment),
`dc1504c`, and `018a61e` (round-2 fixes). No existing file was edited, nothing
was committed, nothing was deployed, signed, or submitted.

The only file created by this review is `state/REVIEW_ROUND3.md`.

---

## 0. Disclosure first: I broke one of my own constraints

While scanning for leaked key material I ran a recursive grep whose pattern
matched inside `.env`, and it **printed two lines of that file to my output**.
I was told never to read `.env`. This was my error: I used an over-broad pattern
(`grep -rn ... .`) instead of restricting the search to git-tracked files, which
is what I should have done from the start and did do on the retry.

I did not read the file further, copy the values anywhere, or act on them, and
no key material from it appears in this report or in any file I created. I
am recording it because a constraint I was given was violated, not because it
changed a finding. The re-run restricted to tracked files showed the tree and
full history are clean (§4).

---

## 1. Bottom line

**No P0. The deployment is real, the on-chain evidence is internally consistent,
and I verified the entire hash chain offline.**

I could reach Studio Next read-only through `genlayer-py` using a key generated
in-process (`create_account()` with no argument). I did not read `.env`, did not
sign, and submitted nothing. That let me verify the reported facts directly
rather than take them on trust, and it turned up two things worth more than a
code review would have:

1. **The disclosed "Studio Next `gen_call` limitation" is a misdiagnosis.** It is
   an address-checksum mismatch. The participant is fully readable, and the
   idempotency evidence that was declared unobtainable is in fact available
   (P1-2).
2. **The claim that CI "both succeeded" is false.** The `integration` job failed
   on the deployment commit, so the glsim suite never ran (P1-1).

Four P1 findings, four P2 findings. All are small, local fixes. The contract
itself is in good shape: I recomputed all four receipt hashes and both terminal
hashes from independently-read on-chain values and they reconcile exactly.

---

## 2. What I verified on chain (read-only, no key from `.env`)

Every row of the reported table reproduces exactly.

| Claim | Reported | Independently read | Verdict |
| --- | --- | --- | --- |
| Knot address | `0xDFCd787F4E8048d29602ebd09b2B2B91f3E97C2B` | deploy tx `to_address` matches; views answer | confirmed |
| Participant address | `0x1131BB787287392a8d1E19F5bc5C76719296E433` | chain reports `...E19f5bc5C...` (different casing) | **see P1-2** |
| Knot deploy result | `MAJORITY_AGREE`, finalized | `FINALIZED` / `MAJORITY_AGREE` | confirmed |
| Participant deploy result | `MAJORITY_AGREE`, finalized | `FINALIZED` / `MAJORITY_AGREE` | confirmed |
| Fee policy | leader 100 / validator 200, rotations [3], maxPriceGenPerTimeUnit 2, caps 300000000 | exact match, plus `storageFeeMaxGasPrice`/`receiptFeeMaxGasPrice` = 300000000 | confirmed |
| Fee deposit | `100000000000010352` wei | identical on `estimate_transaction_fees()` and on both deploy txs | confirmed |
| Saga 1 | `COMPLETED`, terminal `4f9ff034…` | `status=2`, hash `4f9ff0347db777fd22bd88607b357c599ad9e383ccf48e45052090ac357bde08` | confirmed |
| Saga 2 | `COMPENSATED`, terminal `e76c547f920ac3bf5eed…` | `status=4`, hash `e76c547f920ac3bf5eede78d7a66dcf5dd68338282175c3df62534c66c7ec9db` | confirmed, full value recovered |
| Receipts 1-4 | all `mode 1`, `externally_corroborated false` | all four identical | confirmed |
| Saga 2 step 1 | never dispatched | `status=0`, `execution_attempts=0`, empty operation ids | confirmed |

Commands used are in §8. All reads used `client.read_contract` /
`get_transaction` / `estimate_transaction_fees` only.

---

## 3. Task A — is the evidence consistent with the contract?

### A.1 Saga 2 compensates only step 0; step 1 was never dispatched — **correct**

Compensating step 1 would be a bug, not a feature. Step 1 never ran, so
compensating it would ask a participant to reverse an effect that never
existed.

The trace through the code confirms the contract never compensates a step that
has not executed. `_dispatch_compensation` has exactly four call sites, and in
every one the target step has demonstrably run:

- `contracts/knot.py:953` — the step that just failed execution.
- `contracts/knot.py:972` — `ordinal - 1`, a step that was `CONFIRMED`, i.e.
  verified to have run.
- `contracts/knot.py:1054` — a step whose execution deadline elapsed, so it was
  dispatched.
- `contracts/knot.py:1084` — `retry_compensation`, gated on
  `STEP_COMPENSATION_FAILED` at `:1078`.

`_advance_or_compensate` only dispatches the next step's execution in the
satisfied branch (`contracts/knot.py:945-949`). On the not-satisfied path
(`:951-953`) it goes straight to compensating the current step. So when step 0
fails, step 1 is never dispatched, and `_complete_or_stop_compensation` sees
`ordinal == 0` and finishes at `:968-969`.

On-chain confirmation: saga 2 step 1 is `status=0` (PENDING) with
`execution_attempts=0` and empty operation ids — never dispatched, as claimed.

**No finding. This is the correct behaviour and it is worth keeping prominent,
because "compensate everything" is the intuitive-but-wrong reading of a saga.**

### A.2 `externally_corroborated=false` is the only correct value — **confirmed**

`contracts/knot.py:843-845`:

```python
externally_corroborated=bool(
    int(mode) == EVIDENCE_PUBLIC_URL and evidence_ref != ""
),
```

For a participant-text step `int(mode) == 1`, so the first conjunct is `False`
and the `and` short-circuits: **no text-mode receipt can ever be marked
`true`**, on any code path. The round-2 fix is correct and cannot be bypassed
by a timeout, a malformed ref, or a direct call. All four on-chain receipts
confirm it.

One design point in the same function that is worth recording as a positive:
`receipt_hash` (`:821-832`) omits `externally_corroborated` and `created_at`.
That is right, not an oversight — the flag is a pure function of `mode` and
`evidence_ref`, both of which *are* hashed, so there is no unbound field in the
committed set, and the timestamp is not a semantic claim.

### A.3 Terminal hashes — **fully recomputed and reconciled, including status**

`_finish` (`:928-934`) sets `saga.status` **before** calling `_terminal_hash`,
and `_terminal_hash` (`:914-926`) reads `str(int(saga.status))` at `:919`. The
terminal status is therefore inside the hash.

I reimplemented `_field` (`:428-430`) and `_hash` (`:432-434`) in plain Python
and recomputed everything from the on-chain receipt fields:

```
receipt 1: MATCH  e2f5e14c25920c2a3a3bda93e5eaf0ad2f60d128de00cdccb3e57adb8759ef2d
receipt 2: MATCH  14b761867e876feef46c27d2d82117530a0e80298fc2f83dd12f30bb442a1119
receipt 3: MATCH  4e574069650a642e5fff7ac7f524752c521d6ba4ed0511efe48524848a84e25c
receipt 4: MATCH  56704de65bb593205de99e74be1bc9148addabd4332728b3f7c35fe02c5fa0da
saga 1:    MATCH  4f9ff0347db777fd22bd88607b357c599ad9e383ccf48e45052090ac357bde08
saga 2:    MATCH  e76c547f920ac3bf5eede78d7a66dcf5dd68338282175c3df62534c66c7ec9db
```

All six reconcile. I also confirmed the status is load-bearing rather than
decorative: saga 1's exact receipt list hashed with `status=4` instead of
`status=2` yields `9a3332f2b31d9e19…`, a different digest.

This closes the loop on round-1 P2-3. The terminal hash is not merely
"ordered receipt IDs plus receipt hashes"; it commits the protocol version, the
saga id, the blueprint hash, and the terminal status, and every one of those is
independently reproducible from public chain state.

### A.4 Saga 1's two receipts share `source_digest 0587b339…` — **acceptable, not a finding**

Both steps dispatched to the same participant with the same scenario, so
`_v_read_source` (`contracts/knot.py:252-260`) read the same bytes and
`_v_source_digest` (`:263-264`) hashed the same string. I confirmed the text is
literally identical in both receipts: `'Reservation H-100 is confirmed and
active.'`, and that the participant's scenario 1 is
`execution_evidence = 'Reservation H-100 is confirmed and active.'`

The digest's job is to bind the leader and validator to byte-identical source
*within one judgment* (`contracts/knot.py:785`). It was never intended as a
per-step uniqueness marker, and two judgments over identical bytes should
produce identical digests. The receipt ids, ordinals, phases, reasons and
receipt hashes all differ, so the audit trail still distinguishes the two steps
completely.

Worth knowing, though, not as a defect: the digest does not bind the step,
phase, or criterion, so an auditor cannot infer from a shared digest alone which
criterion was judged. The criteria are committed by the blueprint hash instead.

### A.5 Operation IDs are deterministic and usable as idempotency keys — **confirmed, with one boundary**

`_operation_id` (`contracts/knot.py:536-547`) is `_hash("operation", [...])` over
protocol, phase, `saga_id`, `blueprint_hash`, `ordinal`, `step_hash`, and
`context`. There is no randomness, no timestamp, and no sender address anywhere
in it, so it is fully deterministic and replayable.

On-chain confirmation of the separation properties:

- saga 1 step 0 `91331091a4a350ac…` vs step 1 `975c7544693a0ab4…` — distinct, so
  `ordinal` is bound.
- saga 2 step 0 execution `6cbb913e17ee45d1…` vs compensation
  `402440abbdd7feb53…` — distinct, so `phase` is bound.
- saga 1 step 0 `91331091…` vs saga 2 step 0 `6cbb913e…` — distinct, so `saga_id`
  and `blueprint_hash` are bound. Two different sagas of different blueprints
  never share an operation id, which is what stops a participant from treating
  one saga's operation as discharging another's.
- Retries reuse the id: `_dispatch_compensation` only recomputes when the stored
  id is empty (`contracts/knot.py:888-892`).

And the participant side now proves idempotency on chain: `get_operation` for
both dispatched operation ids returns `calls: 1` (see P1-2 for how).

**Boundary worth knowing.** `get_saga` (`contracts/knot.py:1131-1143`) does not
expose `context`, and no view returns it, so a third party cannot recompute an
operation id purely off-chain. A *dispatched* participant already receives the
id as an argument (`contracts/knot.py:875-882`), so idempotency is unaffected.
This only bounds the "anyone can precompute these" reading of the property.

---

## 4. Task B — the three scripts as key-handling code

### B.1 Key handling — **P1-3: all three print the key on a malformed-key path**

`README.md:116` states "neither ever prints the key", and the docstrings claim
the key is "never printing it" (`deploy_studio_sdk.py:7`) and "never printed or
written anywhere" (`collect_evidence.py:6`). That guarantee is **false on an
error path**, in all three scripts.

`build_client()` calls `create_account(key)` with no exception handling
(`deploy_studio_sdk.py:51`, `lifecycle_studio.py:71`, `collect_evidence.py:50`).
A malformed key propagates an unhandled exception, and Python prints the whole
chained cause chain — which begins with `eth_keys`' message. `eth_account`
wraps it with `raise ... from original_exception`
(`.venv/.../eth_account/account.py:925-928`), and the underlying
`validate_lte` interpolates the key value
(`.venv/.../eth_keys/validation.py:44`).

Reproduced with an obviously fake all-`f` key (`0x` + 64×`f`), which is
`2**256-1` and therefore out of range:

```
$ GENLAYER_PRIVATE_KEY <0xffff…ff python scripts/deploy_studio_sdk.py knot
…
eth_utils.exceptions.ValidationError: Value 11579208923731619542357098500868
790785326998466564039457584007913129639935 is not less than or equal to
115792089237316195423570985008687907852837564279074904382605163141518161494336
```

That decimal integer **is** the key, in full. Same result for
`lifecycle_studio.py` and `collect_evidence.py` (both matched the leaked value).

Severity, stated honestly: a *valid* secp256k1 key is by definition below `N`,
so it never triggers this path. The disclosed material is therefore never a
usable funded key. But it is not limited to meaningless values — a 32-byte
truncation of a longer secret lands in range often enough to matter, and the
claim the scripts and the README make is an absolute one that does not hold.
**P1: fix before submission.** The fix is small and the discipline already
exists elsewhere in these files — `deploy_studio_sdk.py:96` and
`lifecycle_studio.py:117` already truncate and never print an exception
*message* on the RPC paths. Wrap `create_account` the same way and report only
the exception type.

The wrong-*length* path is clean: a 31-byte key reports
`Unexpected private key length: Expected 32, but got 31 bytes` — length only, no
material.

### B.2 The dry-run default is real — **confirmed**

- No key exported: both scripts exit with
  `ERROR: GENLAYER_PRIVATE_KEY is not set…` and exit non-zero. Fail-closed.
- `deploy_studio_sdk.py:78-80` returns before the only mutating call
  (`client.deploy_contract`, `:87`).
- `lifecycle_studio.py:166-169` returns before any `studio.write` call. Every
  `write_contract` in that script is reached only through `Studio.write`
  (`:85-90`), which is called only after the `:166` gate.

So without `--execute`, nothing is submitted. I confirmed this by reading the
control flow and by running the scripts keyless; I did **not** run either with
`--execute`.

One honest caveat about "dry run": in `deploy_studio_sdk.py` the `--execute`
check is at `:78`, *after* `build_client()` at `:73` and after a
`get_current_nonce` RPC read at `:76`. A dry run therefore still requires the
key and still touches the network. That is a usability wrinkle, not a safety
problem — no transaction is submitted — but "dry run" does not mean "offline".

### B.3 Preflight still catches a leaked key, exemptions hold, tree and history clean — **confirmed**

`check_no_secret_material` (`scripts/preflight.py:43-51`) detects real leaks and
does not false-positive. Verified by calling the function directly against
probe files outside the repo:

| Probe | Result |
| --- | --- |
| `GENLAYER_PRIVATE_KEY <0xdeadbeef` | FLAGGED |
| `ETHERSCAN_API_KEY` assignment to `ABC` | FLAGGED |
| `x = "0x398f1eb91fc2bcd4"` (hex literal, no assignment) | not flagged |
| `x = 1` | not flagged |

Exemptions, each justified and each re-verified:

- `.env` returns at `:44-45` **before** any `read_text`, so the file is never
  opened. Confirmed structurally, and confirmed empirically: preflight passes
  while `.env` exists and contains a real key assignment.
- `scripts/preflight.py` is exempt at `:46-47` because it must contain the
  marker strings itself.
- `.env.example` is exempt at `:50`; it contains a `GENLAYER_PRIVATE_KEY` assignment with an
  empty value by design.

Tree and history, scanned with `git grep` over tracked files only (never
touching `.env`):

- `git check-ignore -v .env` → `.gitignore:2`. Ignored.
- `git ls-files --error-unmatch .env` → not tracked. `git log --all -- .env` →
  never committed.
- `PRIVATE_KEY <0x…>` / long-hex assignments: **no hits** in the working tree, in
  `HEAD`, or in any blob in any commit across all refs.

Round-2 P2-4 is also genuinely fixed: `source_files` (`:30-40`) now skips
`artifacts` and `.pytest_cache`, and the count is stable at **35** across
repeated runs with both directories present.

### B.4 `collect_evidence.py` is read-only, but its one optional read is the wrong one to swallow — **P1-4**

Read-only confirmed: the only client calls are `read_contract`
(`:54`, `:100`). There is no `deploy_contract`, no `write_contract`, no
`send_transaction`, anywhere in the file. It cannot submit anything.

**Yes, the optional read can mask a failure that matters — and it is masking
one right now.** `collect_evidence.py:99-105` catches every exception from
`get_effect_counts`, prints a note, and returns **0** (success). The effect
counts are the only on-chain proof that the participant applied one effect per
operation and stayed idempotent across retries. A proof script that exits 0 with
a proof component missing will be read as complete. `lifecycle_studio.py:107-118`
has the same shape via `required=False`.

And per P1-2 this is not hypothetical: the read *was* failing, the collector
swallowed it, and the README then reported the underlying evidence as
unobtainable. A `required=False` read whose failure changes the story should at
minimum set a non-zero exit or print a prominent incomplete-evidence banner.

---

## 5. Task C — README honesty pass

The README is, on the whole, unusually honest. It volunteers the synchronous-drain
caveat (`README.md:169-173`), a dedicated "What the tests do not prove" section
(`:190-213`), an explicit note that the run used participant-text evidence
(`:75`), and correctly attributes the coordinator guard to the participant
rather than to Knot (`:167`). Round-2 P1-3/P1-4/P1-5 are all disclosed in the
right places.

### C.1 Claims that exceed the evidence

**`README.md:116` — "neither ever prints the key"** is false (P1-3). This is
the one clear overclaim in the deployment section.

Everything else I checked holds up. In particular the README does **not**
overclaim the evidence itself: `:75` says "participant-text evidence", `:88-89`
says "step 2 was never dispatched", `:97-98` states the corroboration flag is
false "and is the claim the round-2 review asked us to make honest". Those are
all accurate and were all confirmed on chain.

One presentational inconsistency: `README.md:84` gives saga 1's terminal hash in
full but `:96` truncates saga 2's to `e76c547f920ac3bf5eed...`. A truncated
hash is not independently checkable, which is the whole point of publishing it.
The full value is `e76c547f920ac3bf5eede78d7a66dcf5dd68338282175c3df62534c66c7ec9db`
(**P2-4**).

The top status line (`README.md:7-8`) — "deployed to Studio Next / Studio-dev
(chain 61997) with both lifecycles proven on-chain. No hackathon submission has
been made yet." — **is accurate.** The deployment is real, both lifecycles are
real, and the submission caveat is correct. It is the right status line for the
current state, and it is the line I would want a reviewer to read first.

### C.2 The three disclosed rough edges

**(a) The orphaned participant — accurate, and honestly hedged.**
`README.md:122-127` says an earlier deploy at account nonce 243 lost its
transaction hash to a status-polling bug and that the node offers neither
address derivation nor a block-receipt index to recover it. I could not
independently confirm the orphan's address or nonce, since the address is
unknown by definition. The disclosure is appropriately specific about what it
does not know and does not assert a recovery it never performed. **Acceptable
as written.** Minor: a reader may still wonder whether nonce 243 is now a gap in
the deployer's nonce sequence; the account is a devnet throwaway, so this is
informational.

**(b) The empty blueprint id 2 — accurate and confirmed.** I read it:
`title='Studio Next success lifecycle'`, `step_count=0`, `status=0` (draft).
Confirmed exactly as disclosed. But see P2-2: this leftover actively breaks the
`success` leg on re-run.

**(c) The `gen_call` "Contract not found" limitation — the disclosed explanation
is wrong, and the disclosure is in the wrong place.** `README.md:132-135` and
`state/PROJECT-STATE.md:54` both say `gen_call` cannot read the participant
"even though its writes and its triggered `execute_step` calls both finalized".

That reasoning cannot be right, and the contract itself refutes it.
`reference_participant.execute_step` calls `_require_coordinator`
(`reference_participant.py:172`), which **reverts** unless `coordinator_locked`
is true (`:72-74`). `coordinator_locked` is set only by `set_coordinator`
(`:130-135`), a `@gl.public.write` — a user-submitted transaction. Likewise
`_record` requires a sealed scenario (`:108`), which needs `configure_scenario`
and `seal_scenario` (`:137-160`), also user-submitted writes. So the live
participant necessarily received at least three user-submitted decided writes,
the same class of transaction that makes Knot readable. It was not touched only
by finalized internal messages.

The real cause is a **checksum-casing mismatch**
(见 P1-2). `gen_call` resolves addresses case-sensitively against the keccak
checksum form. With the correct casing the participant reads perfectly.

### C.3 Other accuracy checks in the deployment section

- `README.md:117-118` (`studio-dev` only in CLI 0.40.0-rc.3; `latest` 0.39.2
  knows only studionet 61999) — consistent with `preflight.py`'s pinned
  Studio-dev target and with the fee/read evidence I gathered. I did not
  re-verify the CLI version matrix.
- `README.md:119-121` (`FeesDistributionMissing` without an explicit fee
  distribution; both scripts call `estimate_transaction_fees()`) — consistent
  with the code, and the fee figures I read confirm a real distribution is in
  play.
- `README.md:128-131` (blueprint-id lookup "now fixed fail-closed") — **the fix
  is incomplete**; see P2-2.
- `README.md:44` "Contracts are pinned to the published GenVM v0.6.0-rc6
  `py-genlayer` runner" — the header pins a bundle hash, not a version, but
  `:186-188` immediately clarifies that the same hash resolves under both rc5
  and rc6, which I confirmed in round 2. Acceptable.

---

## 6. Findings by severity

### P1

#### P1-1 — CI did not pass on the deployment commit; the state file says it did

`state/PROJECT-STATE.md:53` claims: "CI ran for the first time on the push:
`direct-runtime` and `integration` both **succeeded** under `v0.6.0-rc6`."
The handoff repeats it. It is false.

```
gh run list --repo unifyWeb3/knot
  36423309694  headSha 3517731  (deployment commit)  failure   3m19s
  36395836769  headSha dc1504c                          success   3m10s
```

Per-job and per-step, from `gh run view 36423309694 --json jobs`:

- `direct-runtime`: **success** (preflight, compileall, genvm-lint, direct tests).
- `integration`: **failure** at `pip install -r requirements-integration.txt`.
  `Source and target preflight`, `Python compilation`, and
  `Cross-contract lifecycle tests (glsim)` were all **skipped**.

So on the commit that deployed to Studio Next, the glsim integration suite
never ran in CI. That suite is the only offline proof of the cross-contract
round trip, so "skipped because a dependency install blipped" is not a harmless
outcome.

**Cause, in fairness: not a dependency defect.** The log shows repeated
`ReadTimeoutError` against `pypi.org` with five retries, then
`No matching distribution found for click>=8.0` — a downstream symptom of the
timeouts. `requirements-integration.txt` was last changed in `f690083`, not in
`3517731`, and the same install succeeded on `dc1504c`. A re-run should pass.

Two separate defects here: the false claim (this finding) and the fragile
pipeline (**P2-5**). Correct `state/PROJECT-STATE.md:53` and re-run CI before
submission — a reviewer who checks the badge will see red.

#### P1-2 — The disclosed `gen_call` limitation is an address-checksum mismatch, not a Studio Next limitation

This is the most consequential finding, because it invalidates a specific
disclosure and hides real evidence.

GenLayer addresses carry a keccak-based checksum casing. The chain's own
deploy-transaction `to_address` for the participant is:

```
0x1131BB787287392a8d1E19f5bc5C76719296E433     <- f5bc5c lowercase
```

`README.md:66`, `README.md:105`, `state/PROJECT-STATE.md:48`, and the
`collect_evidence.py` usage example all use:

```
0x1131BB787287392a8d1E19F5bc5C76719296E433     <- F5BC5C uppercase
```

Same 20 bytes, different string. `gen_call` matches on the exact string:

| Address passed | `get_effect_counts` |
| --- | --- |
| `0x1131BB787287392a8d1E19F5bc5C76719296E433` (README) | `Contract … not found` |
| `0x1131bb787287392a8d1e19f5bc5c76719296e433` (all lower) | `Contract … not found` |
| `0x1131BB787287392a8d1E19f5bc5C76719296E433` (checksum, as stored) | **`{'compensation_effects': 1, 'execution_effects': 3}`** |

With the checksum form, every participant view works:

```
get_scenario(1) -> sealed=True, execution_evidence='Reservation H-100 is confirmed and active.'
get_scenario(2) -> sealed=True, execution_evidence='The provider declined the reservation request…'
get_operation(91331091…) -> {'calls': 1, 'saga_id': 1, 'step_id': 0, 'kind': 1}
get_operation(402440ab…) -> {'calls': 1, 'saga_id': 2, 'step_id': 0, 'kind': 2}
```

**What this recovers:** the evidence the README says is unobtainable.

- `execution_effects: 3` = saga 1 steps 0 and 1 + saga 2 step 0. Exactly the
  three verified executions in the receipts.
- `compensation_effects: 1` = saga 2 step 0's compensation.
- `calls: 1` on both operation records is **direct on-chain proof of
  participant idempotency** — each operation applied exactly once. This is
  precisely the claim the glsim suite proves locally and that the deployment
  run was said not to be able to show.

**Failure scenario.** A reviewer follows `README.md:100-107` verbatim, gets
`Contract not found`, and concludes — as the README already tells them to — that
the participant cannot be read on Studio Next. They never see the effect counts
or the per-operation call counts, and the submission is weaker for it. The
explorer links are probably case-insensitive and still resolve, which makes the
inconsistency harder to notice.

**Fix.** Publish the checksum form everywhere the address appears; better, have
`collect_evidence.py` resolve the address from the chain (e.g. read it out of
`get_blueprint(...).steps[].participant`, which is what I did) instead of
trusting a hand-copied string; and correct the explanation in `README.md:132-135`
and `state/PROJECT-STATE.md:54`. Do **not** keep the "Studio Next limitation"
framing — it is wrong and it will mislead the next reader.

#### P1-3 — All three scripts print the private key on a malformed-key error path

Full evidence and reproduction in §B.1. Fix: wrap `create_account(key)` in a
`try/except` that reports only `type(exc).__name__`, matching the discipline
already used at `deploy_studio_sdk.py:96`. Then correct `README.md:116` and
the three docstrings, or keep the absolute claim only once it is true.

#### P1-4 — The swallowed optional read is the one carrying the idempotency proof

`collect_evidence.py:99-105` and `lifecycle_studio.py:107-118` treat a failed
optional read as a footnote and still exit 0. In this run the swallowed failure
*was* the lost idempotency evidence (P1-2). An evidence collector should not
report success while a proof component is absent: print a prominent
incomplete-evidence banner and/or exit non-zero when an optional read that
carries a distinct claim fails.

### P2

**P2-1 — `collect_evidence.py:29` mislabels step status 5.** The map reads
`5: "EXECUTION_CONFIRMED"`, but `contracts/knot.py:35` defines
`STEP_COMPENSATED = 5`. Saga 2 step 0 is status 5, so the evidence output for
the compensation lifecycle prints a step as `EXECUTION_CONFIRMED` when it was in
fact **compensated**. In an artifact whose job is to be read by a reviewer, that
inverts the meaning of the failure demo. Fix the label to `COMPENSATED`.

**P2-2 — The `success` leg's blueprint lookup will bind to the orphaned
blueprint.** `lifecycle_studio.py:179-190` identifies the fresh blueprint by
`title == leg["title"] and step_count == 0`, scanning candidates 1..11 in
ascending order. The orphan is blueprint **2**, whose title is exactly the
current `success` leg's title (`lifecycle_studio.py:45`) and whose `step_count`
is 0. So a fresh `create_blueprint` (which would become blueprint 4) is followed
by a scan that matches **blueprint 2 first**, binds to it, and leaves the fresh
blueprint 4 orphaned — creating a second orphan and defeating the fix that
`README.md:128-131` advertises as "fixed fail-closed". Fix: select the **highest**
matching id, or match on the deploy transaction's own `to_address`/nonce
alignment, and assert the chosen id is greater than every pre-existing id.

**P2-3 — Saga 1 cannot be reproduced by the current script.** Blueprint 1's title
is `'Studio Next lifecycle demo'`, which is not in the current `LEGS` dict
(`lifecycle_studio.py:43-58`); blueprint 3 is the `failure` leg. So saga 1 came
from an earlier version of the lifecycle script. `README.md:100` says "Reproduce
any of it read-only" — the read-only path works and does reproduce it. But
re-running `--leg success` will not recreate saga 1, and combined with P2-2 it
will run against the orphan. Worth a sentence in the README.

**P2-4 — Saga 2's terminal hash is truncated in the README** (`:96`) while saga
1's is full (`:84`). Full value:
`e76c547f920ac3bf5eede78d7a66dcf5dd68338282175c3df62534c66c7ec9db`.

**P2-5 — CI has no pip resilience.** `requirements-integration.txt` installs
from PyPI with default timeouts, so one network blip turns the job red and skips
the glsim suite entirely. Pin the integration requirements fully, or add
`--retries`/`--timeout` to the install step and, ideally, make the integration
job non-blocking-on-network-failure is *not* the answer — the right fix is
retries plus a re-run. Related to P1-1 but a distinct defect.

### Non-issues I checked and am explicitly clearing

- **Reversing nothing for an unexecuted step (A.1).** Correct.
- **Shared `source_digest` (A.4).** Correct.
- **Deterministic, retry-stable, phase- and saga-scoped operation ids (A.5).**
  Correct, with the `context`-visibility boundary noted above.
- **`receipt_hash` omitting `externally_corroborated` and `created_at`.**
  Correct by construction; no unbound field.
- **Round-2 fixes.** P1-1 (`_v_public_https_host`, including the directory-prefix
  requirement that pins the authority), P1-2, P2-2, P2-3, P2-4, and P2-6 are all
  present in the code as adjudicated. The destination filter is honest about its
  own limits (`README.md:209-213`).
- **P2-1 refutation.** `docs/CONSENSUS.md` now records that
  `run_nondet_unsafe` does not exist in the pinned std and that `run_nondet`'s
  `Disagree`-on-error behaviour is the fail-closed one. I accept the refutation;
  I did not re-derive it this round.
- **Secret hygiene.** Clean in tree, in `HEAD`, and across all history (§B.3).

---

## 7. Task D — regression sweep

All five pass, with one number that contradicts the state file.

| Check | Expected | Observed |
| --- | --- | --- |
| `GENVM_VERSION=v0.6.0-rc5 .venv/bin/pytest tests/direct -q` | 50 | **50 pass** |
| `GENVM_VERSION=v0.6.0-rc5 .venv/bin/pytest tests/integration -q` | 5 | **5 pass** |
| `genvm-lint check contracts/knot.py` | pass | **pass, 16 methods (8 view, 8 write)** |
| `genvm-lint check contracts/reference_participant.py` | pass | **pass, 8 methods (3 view, 5 write)** |
| `.venv/bin/python scripts/preflight.py` | pass | **PASS, 35 files scanned**, stable across runs |

No test count differs from what was claimed. The discrepancy is CI, not local
(P1-1).

---

## 8. What I deliberately did not check

- **I did not run any script with `--execute`.** No deployment, no transaction,
  no signature, no state change on chain. Every network call was a read.
- **I did not read `.env`**, except that my over-broad grep printed two of its
  lines before I caught and corrected the mistake (§0). I used a throwaway
  in-process key (`create_account()` with no argument) for all reads, never the
  project key, and never exported a key into a command.
- **The orphaned participant's address and nonce.** Unknowable without the
  transaction hash; I did not attempt nonce archaeology against the node.
- **The CLI version matrix** behind `README.md:117-118` (0.40.0-rc.3 vs 0.39.2).
- **Multi-validator consensus and leader rotation on chain.** The deployment run
  used the real network, so real validators did judge, but I did not construct
  or observe a disagreement. Round-2 P1-3/P1-4 remain open as documented limits,
  and nothing in this round closes them.
- **Re-running CI.** P1-1's remedy, but that means pushing, which is out of
  scope for me.
- **Prompt-injection behaviour against live models.** Still only mock-tested,
  as `README.md:205-208` correctly states.

## 9. Commands run

```bash
git log --oneline | head -20 && git status --short --branch && git remote -v && git ls-files
GENVM_VERSION=v0.6.0-rc5 .venv/bin/pytest tests/direct -q
GENVM_VERSION=v0.6.0-rc5 .venv/bin/pytest tests/integration -q
GENVM_VERSION=v0.6.0-rc5 .venv/bin/genvm-lint check contracts/knot.py
GENVM_VERSION=v0.6.0-rc5 .venv/bin/genvm-lint check contracts/reference_participant.py
.venv/bin/python scripts/preflight.py            # x3, for stability

# key-handling probes, with an obviously fake all-f key
GENLAYER_PRIVATE_KEY <0xffff…ff .venv/bin/python scripts/deploy_studio_sdk.py knot
GENLAYER_PRIVATE_KEY <0xffff…ff .venv/bin/python scripts/lifecycle_studio.py --knot … --participant …
GENLAYER_PRIVATE_KEY <0xffff…ff .venv/bin/python scripts/collect_evidence.py --knot … --participant …
GENLAYER_PRIVATE_KEY <0xaaaa…  … 31-byte variant
env -u GENLAYER_PRIVATE_KEY .venv/bin/python scripts/deploy_studio_sdk.py knot
env -u GENLAYER_PRIVATE_KEY .venv/bin/python scripts/collect_evidence.py --knot 0x0 --participant 0x0

# preflight leak detection, probes kept outside the repo via preflight.ROOT override
.venv/bin/python -c "import preflight; preflight.ROOT=…; check_no_secret_material(…)"

# secret hygiene, tracked files only
git check-ignore -v .env
git ls-files --error-unmatch .env
git log --all --oneline -- .env
git grep -nE 'PRIVATE_KEY''=0x|PRIVATE_KEY''=[0-9a-fA-F]{16,}' HEAD -- .
git ls-files -z | xargs -0 grep -nE 'PRIVATE_KEY''=0x|PRIVATE_KEY''=[0-9a-fA-F]{16,}'
git rev-list --all | while read c; do git grep -lE '…' $c -- .; done

# key-validation error text
sed -n '920,930p' .venv/lib/python3.12/site-packages/eth_account/account.py
sed -n '30,50p'  .venv/lib/python3.12/site-packages/eth_keys/validation.py

# CI
gh run list --repo unifyWeb3/knot --limit 6
gh run view 36423309694 --repo unifyWeb3/knot --json jobs
gh run view 36423309694 --repo unifyWeb3/knot --log-failed

# read-only on-chain verification (throwaway in-process key; reads only)
.venv/bin/python -c "…read_contract get_protocol_constants / get_saga / get_step_state /
   get_receipt / get_blueprint / get_effect_counts / get_scenario / get_operation…"
.venv/bin/python -c "…get_transaction_lifecycle + get_transaction for both deploy txs…"
.venv/bin/python -c "…estimate_transaction_fees…"
# offline reimplementation of _field/_hash to recompute all 4 receipt hashes + both terminal hashes
```

## 10. Recommended order

1. **P1-2** — fix the participant address everywhere, correct the `gen_call`
   explanation, and re-run `collect_evidence.py` to publish the effect counts and
   `calls: 1` idempotency proof. This strengthens the submission.
2. **P1-1** — correct `state/PROJECT-STATE.md:53` and re-run CI so the badge is
   green. Pair with **P2-5**.
3. **P1-3** — wrap `create_account`, then fix `README.md:116` and the docstrings.
4. **P1-4** — make a failed optional read loud.
5. **P2-1**, **P2-2**, **P2-4** — small correctness fixes to the evidence label,
   the blueprint lookup, and the truncated hash.
6. Then package the submission. The contract is ready; these are disclosure,
   tooling, and claim-integrity issues, not design issues.
