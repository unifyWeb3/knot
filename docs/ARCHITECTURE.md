# Knot architecture

## Design boundary

Knot has two layers:

1. **Deterministic coordination** — blueprint immutability, dispatch state, operation IDs, deadlines, ordering, retries, and terminal state.
2. **Consensus-critical evidence judgment** — a bounded question about whether observed evidence establishes a frozen postcondition.

The model must not choose the next step, create a compensation, authorize a participant, or decide terminal status.

## Frozen design decisions

- **Hashing:** `knot-sha256-v1` uses a versioned, domain-separated, length-prefixed encoding for every field. Step hashes are aggregated in ordinal order into the blueprint hash.
- **Evidence source:** every public-URL step freezes an exact `https://` evidence prefix, which must be a directory prefix served by a public host (see `docs/THREAT_MODEL.md`). Participant text steps must have an empty prefix.
- **Controller:** the blueprint owner is the initial and default Saga controller. Permissionless start is not part of v1.
- **Timeout:** the deadline is parent-dispatch transaction time plus the step timeout, with a minimum of 300 seconds. A late callback may still be accepted until a timeout transaction crystallizes failure.
- **Retry:** compensation retry is bounded revalidation of the same logical operation and reuses its operation ID. v1 does not silently start a new corrective effect.
- **Terminal commitment:** the terminal hash includes the full ordered receipt ID history and the terminal Saga status.

## Durable state

```text
Blueprint
  id, owner, title, purpose, status, step_count, definition_hash

StepDefinition
  blueprint_id, ordinal, participant, action_payload,
  execution_criterion, execution_evidence_mode,
  compensation_payload, compensation_criterion,
  compensation_evidence_mode, timeout_seconds, definition_hash

Saga
  id, blueprint_id, blueprint_hash, controller, context,
  status, current_step, timestamps, terminal_hash

StepState
  saga_id, ordinal, status, operation IDs, dispatch timestamps,
  attempt counters, latest verification receipt IDs

VerificationReceipt
  saga_id, ordinal, phase, verdict, evidence mode/reference,
  reason, supporting excerpt, source digest, receipt hash
```

All collections use GenLayer storage types (`TreeMap`/`DynArray`), never ordinary Python `dict`/`list` fields.

## State machines

```text
Blueprint: DRAFT -> SEALED

Saga: ACTIVE -> COMPLETED
           |
           +-> COMPENSATING -> COMPENSATED
                             -> STUCK

Step: PENDING -> EXECUTION_DISPATCHED -> CONFIRMED
                         |
                         +-> EXECUTION_FAILED
                                  |
                                  v
                         COMPENSATION_DISPATCHED
                           |              |
                           v              v
                      COMPENSATED   COMPENSATION_FAILED
```

A failed or timed-out dispatched step is included in compensation. Earlier steps are not touched until the current compensation is `SATISFIED`.

## Message sequence

```text
controller -> Knot.start_saga
Knot --finalized--> participant.execute_step
participant effect
participant --finalized--> Knot.report_execution(evidence)
Knot leader/validator evidence check
Knot --finalized--> next participant or compensation
...
Knot -> terminal state/event
```

Every internal message uses `on="finalized"`. State is persisted before a child message is emitted. Participants must be idempotent because finalized delivery can still be repeated by retries or protocol replays.

## Trust boundaries

- Blueprint owner/controller: workflow authorization.
- Participant contract: external effect and initial evidence.
- Public source: independently fetchable evidence, but not automatically authoritative.
- GenLayer validators: independent semantic judgment.
- LLM: untrusted parser/judge, never the workflow authority.

## No backend

Knot does not need a conventional backend, database, API server, or frontend. The deployment/test scripts are tooling. The first release is one core contract plus a reference participant adapter used to prove the integration contract.

## Open design decisions

These are intentionally explicit before implementation grows:

- exact evidence-source allowlist representation;
- whether a retry revalidates the same logical effect or starts a new corrective attempt;
- timeout start point relative to finalized child creation;
- whether terminal commitments include all historical receipts or only current receipt IDs.
