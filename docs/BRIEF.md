# Knot product brief

## Decision

**Go, conditionally.** Build the smallest reusable Intelligent Contract that proves one complete success path and one failure/compensation path on Studio Next. Do not add product infrastructure until that slice works.

## User and problem

The user is a GenLayer builder who needs to coordinate several independent participant contracts when a step's success cannot be established by a deterministic return code alone.

The problem is not ordinary sequencing. The problem is deciding whether a real-world or participant-side effect actually happened, while preserving a safe rollback path when a later step fails.

## One user journey

1. The builder creates a blueprint with a title, purpose, and ordered steps.
2. Each step names a participant contract, action payload, semantic criterion, evidence mode, timeout, and compensation payload.
3. The builder seals the blueprint. Its ordered definition is hashed and cannot be edited.
4. An authorized controller starts a Saga instance with bounded context.
5. Knot dispatches the first step through a finalized internal message.
6. The participant performs its action and returns evidence.
7. Knot asks GenLayer validators to independently judge the frozen postcondition.
8. `SATISFIED` advances the Saga. Any other result begins compensation.
9. Compensation starts at the failed or uncertain dispatched step and proceeds backward only after each compensation is verified.
10. The Saga ends as `COMPLETED`, `COMPENSATED`, or `STUCK`, with a terminal commitment.

## External action

Knot itself does not call arbitrary external services. The external action is performed by the configured participant Intelligent Contract through its `execute_step` or `compensate_step` method. Knot verifies the evidence returned by that participant or a public source.

## Authorization model

- The blueprint creator owns draft editing and sealing.
- In v1, the blueprint owner is also the Saga controller and the only address that can start or retry that Saga.
- A participant accepts calls only from its pinned Knot coordinator.
- A callback is accepted only from the participant address frozen into the step.
- Timeout crystallization may be permissionless only after the recorded deadline.
- Compensation retries are bounded revalidation attempts and retain a stable logical operation identity.

The first implementation is secure by default: owner/controller authorized, not permissionless.

## Success observation

A successful operation requires more than a broadcast transaction. The reviewer must be able to verify the finalized transaction status and `FINISHED_WITH_RETURN` execution result. They must also observe the contract address on the Studio Next explorer, the blue print and terminal hashes, and the verification receipts. Finally, they must see the observed message order and participant effect counters.

## Smallest live end-to-end slice

Deploy:

- one `Knot` contract;
- one reference participant contract with two or three ordered steps;
- one public, commit-pinned success fixture;
- one public, commit-pinned failure fixture.

Run one Saga that completes and one Saga whose final step fails and compensates in reverse order. Record all transaction IDs and state snapshots.

## Main risks

1. Studio Next / Consensus v0.6 compatibility and fee-funded child messages.
2. Validator agreement on semantic evidence.
3. Evidence provenance and prompt injection.
4. Timeout and retry semantics when effects are partial.
5. Keeping the project a reusable primitive rather than a one-off demo.

## Go/no-go gate

Proceed to polish only if the unchanged minimal contract can be deployed on chain `61997`, finalize with `FINISHED_WITH_RETURN`, complete the success flow, and reach `COMPENSATED` on the failure flow. If deployment or consensus fails, diagnose compatibility before adding features.
