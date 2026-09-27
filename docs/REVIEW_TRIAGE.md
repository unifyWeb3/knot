# Independent review triage

Reviewed report: read-only audit from the second session, 2026-09-25.

## Accepted and addressed

- **P1-1 hash canonicalization:** accepted. Knot now uses `knot-sha256-v1`, versioned domain tags, length-prefixed fields, ordered step aggregation, and a pinned runtime header.
- **P1-2 nondeterministic storage boundary:** accepted. The participant and Saga values used by the evidence block are copied with `gl.storage.copy_to_memory` before the leader/validator closures are created.
- **P1-3 timeout placement:** accepted and frozen. Deadlines use parent-dispatch transaction time with a 300-second minimum; a late callback is accepted until timeout crystallization.
- **P1-4 evidence provenance:** accepted and frozen. Public URL steps carry an exact frozen HTTPS evidence prefix.
- **P1-5 participant-text distinction:** accepted. Receipts carry `externally_corroborated`, which is false for participant text.
- **P1-6 validator error behavior:** accepted. The leader maps source/model failures to bounded verdicts; the validator independently re-derives and returns disagreement on malformed or exceptional results.
- **P2-1 storage records:** accepted. All persisted records use the v0.6 storage decorator and dataclass pattern.
- **P2-2 replay handling:** accepted. Step status and stable operation IDs make duplicate callbacks no-ops.
- **P2-3 terminal history:** accepted. The terminal hash includes the ordered receipt ID and receipt-hash history.
- **P2-4 controller policy:** accepted. The blueprint owner is the initial Saga controller in v1.
- **P2-5 retry semantics:** accepted. Compensation retries revalidate the same logical operation ID, with three total attempts maximum.
- **P2-7 dependency pin:** accepted. `genlayer-py==0.19.0rc2` is direct-pinned in the test requirements.

## Refuted or not actionable yet

- **Frontend/UX rubric mismatch (P0-3):** not accepted as a reason to add a frontend. The extracted `frontend_ux` scoring block is tied to the portal's `builder_project` review flow. The Intelligent Contracts contribution type is a separate standard review flow, and the user explicitly selected a standalone primitive. No product frontend is planned unless the live submission form explicitly requires one.
- **Public repository as a hard gate (P0-2):** the remote repository is known to be empty, but no remote was configured, committed, or pushed in this session. Local checkpoints proceed first; remote mutation still requires explicit approval.
- **No implementation (P0-1):** expected at the time of the report and now being addressed by the first contract implementation.

## Still requires live evidence

- Studio Next deployment with chain ID `61997`.
- Both successful and reverse-compensation flows.
- `FINISHED_WITH_RETURN` plus finalized transaction status for every transaction.
- Public evidence fetching and validator agreement.
- Fee profile covering child messages.
- Repeated consensus runs and undetermined-outcome rate.
