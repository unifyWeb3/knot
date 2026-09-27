# Knot participant integration

A participant is an Intelligent Contract that performs one logical action for a Knot step.

## Required write methods

```python
@gl.public.write
def execute_step(
    self,
    coordinator: gl.Address,
    saga_id: gl.u256,
    step_id: gl.u256,
    operation_id: str,
    action_payload: str,
    context: str,
) -> None: ...

@gl.public.write
def compensate_step(
    self,
    coordinator: gl.Address,
    saga_id: gl.u256,
    step_id: gl.u256,
    operation_id: str,
    compensation_payload: str,
    context: str,
) -> None: ...
```

After attempting the effect, the participant sends a finalized callback:

```python
gl.contract.get_at(coordinator).emit(on="finalized").report_execution(
    saga_id, step_id, operation_id, evidence_ref
)
```

Use `report_compensation` for the rollback phase.

## Participant invariants

- Pin and authenticate the Knot coordinator.
- Persist `operation_id` as an idempotency key.
- Never apply the same economic side effect twice.
- Return prior evidence for duplicate delivery unless a separately defined corrective attempt is authorized.
- Make compensation safe after full, partial, or absent forward execution.
- Prefer immutable, operation-bound public evidence for material effects.
- Do not put secrets in payloads or evidence URLs.

## Evidence

A participant should return the smallest useful evidence reference. Knot, not the participant, decides whether the evidence is accepted. The participant must not be treated as an authority merely because it returned a well-formed response.

The reference participant in this repository is a deterministic harness, not a real reservation, payment, or fulfillment system.
