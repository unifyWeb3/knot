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
 tests/integration/        Opt-in Studio Next lifecycle tests
 scripts/                  Preflight, deployment, and evidence helpers
 fixtures/                 Commit-pinned public evidence fixtures
 state/                    Project checkpoints and handoff notes
```

## Development status

See [`state/PROJECT-STATE.md`](state/PROJECT-STATE.md) and [`state/LEFT-OFF.md`](state/LEFT-OFF.md) for the current checkpoint and next action.

## Security

The repository must never contain a private key, API key, or real `.env` file. Public evidence is untrusted input. The contract must fail closed and must never treat a valid-looking model response as proof without independent validator work.
