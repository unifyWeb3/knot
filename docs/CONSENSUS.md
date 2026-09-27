# Knot consensus design

## Question

For one exact Saga step and phase, validators answer:

> Does the observed evidence materially establish the frozen execution or compensation postcondition?

The model must return a bounded decision, not free-form authority.

## Planned decision shape

```json
{
  "verdict": "SATISFIED | NOT_SATISFIED | AMBIGUOUS | UNAVAILABLE",
  "reason": "bounded explanation",
  "evidence": "short verbatim supporting excerpt",
  "source_digest": "digest of the observed source when available"
}
```

The implementation may evolve this shape, but validators must compare the decision field and independently re-derive it from evidence.

## Leader and validator

The leader function:

1. validates the frozen step and evidence mode;
2. fetches or reads the bounded source;
3. asks the LLM for structured output;
4. validates and bounds the result;
5. returns the structured decision.

The validator function:

1. independently reads the same source or attestation;
2. independently produces a decision;
3. compares the stable verdict, not prose;
4. for `SATISFIED`, checks that the leader excerpt exists in the validator's own observed source;
5. returns `False` for malformed or unavailable results rather than trusting the leader.

Use the v0.6 `gl.vm.run_nondet` boundary and handle errors inside the validator. A JSON schema check alone is not consensus.

## Evidence modes

- `PUBLIC_URL`: preferred for material external effects. Each step freezes an exact HTTPS evidence prefix; the callback URL must remain inside that prefix.
- `PARTICIPANT_TEXT`: explicitly weaker attestation mode. It must have no source prefix, is marked `externally_corroborated = false` in receipts, and must not be described as independent external proof.

The first reviewer demo should use `PUBLIC_URL` with a commit-pinned prefix.

## Fail-closed policy

Only `SATISFIED` advances execution. `NOT_SATISFIED`, `AMBIGUOUS`, `UNAVAILABLE`, malformed output, disagreement, and callback timeout initiate conservative compensation. A non-satisfied compensation becomes `STUCK`.

This is a safety/liveness trade-off and must be documented: a malicious or unavailable participant can force rollback.

## Reliability testing

The test matrix must include:

- satisfied, not-satisfied, ambiguous, and unavailable results;
- leader/validator disagreement;
- malformed JSON and missing excerpts;
- unrelated, replayed, and contradictory pages;
- direct and multilingual prompt injection;
- different source versions between leader and validators;
- repeated runs to measure agreement and undetermined outcomes.

Do not claim consensus reliability from one successful fixture.
