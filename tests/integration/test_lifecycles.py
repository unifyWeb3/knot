"""End-to-end lifecycle assertions for Knot on the local GenLayer simulator.

Each test deploys a fresh Knot + ReferenceParticipant pair, so the state
machine, the cross-contract dispatch leg, and the callback leg are exercised
exactly as they are on chain: ``start_saga`` emits ``execute_step``, the
participant answers with ``report_execution``, and Knot's bounded evidence
judgment decides the next transition.

Run with: ``GENVM_VERSION=v0.6.0-rc5 pytest tests/integration -q``
"""

import pytest

pytestmark = pytest.mark.integration

T0 = "2026-09-25T10:00:00+00:00"
T0_PLUS_301 = "2026-09-25T10:05:01+00:00"

EXEC_SOURCE = "Reservation H-100 is confirmed and active."
COMP_SOURCE = "The reservation for trip one was reversed in full."
EXEC_CRITERION = "The evidence establishes that trip logistics completed successfully."
COMP_CRITERION = "The evidence establishes that trip logistics was reversed."

SAGA_ACTIVE = 1
SAGA_COMPLETED = 2
SAGA_COMPENSATING = 3
SAGA_COMPENSATED = 4
SAGA_STUCK = 5

STEP_CONFIRMED = 2
STEP_COMPENSATION_DISPATCHED = 4
STEP_COMPENSATION_FAILED = 6

PHASE_EXECUTION = 1
PHASE_COMPENSATION = 2

VERDICT_SATISFIED = 1
VERDICT_NOT_SATISFIED = 2
VERDICT_TIMEOUT = 5

TEXT_MODE = 1


def decision(verdict: str, reason: str, evidence: str) -> dict:
    return {"verdict": verdict, "reason": reason, "evidence": evidence}


def verdict_mock(verdict: str, exec_llm, comp_llm, *, exec_evidence="", comp_evidence="") -> dict:
    """Mock set keyed by the criterion text each judgment prompt contains."""
    return {
        "completed successfully": exec_llm(
            decision(verdict if exec_evidence or verdict != "SATISFIED" else verdict,
                     "The evidence settles the execution criterion.",
                     exec_evidence)
        ),
        "was reversed": comp_llm(
            decision(verdict, "The evidence settles the compensation criterion.", comp_evidence)
        ),
    }


def new_workflow(sim, *, comp_payload: str = "1", timeout: int = 600):
    """Deploy Knot + participant, seal a two-step blueprint, return addresses."""
    knot = sim.deploy(sim.knot_path)
    participant = sim.deploy(sim.participant_path)

    sim.write(participant, "set_coordinator", [knot])
    sim.write(participant, "configure_scenario", [1, EXEC_SOURCE, COMP_SOURCE])
    sim.write(participant, "seal_scenario", [1])

    blueprint = sim.call(knot, "create_blueprint", ["Travel", "Coordinate dependent steps."])
    for label in ("flight", "hotel"):
        sim.write(
            knot,
            "add_step",
            [
                blueprint,
                participant,
                label,
                "1",  # action payload -> configured scenario 1
                EXEC_CRITERION,
                TEXT_MODE,
                "",
                comp_payload,
                COMP_CRITERION,
                TEXT_MODE,
                "",
                timeout,
            ],
        )
    sim.call(knot, "seal_blueprint", [blueprint])
    return knot, participant, blueprint


def test_success_lifecycle_completes_saga(sim, llm_text):
    knot, participant, blueprint = new_workflow(sim)
    sim.install_mocks(
        {
            "completed successfully": llm_text(
                decision("SATISFIED", "The source establishes the criterion.", EXEC_SOURCE)
            ),
            "was reversed": llm_text(
                decision("SATISFIED", "The source establishes the criterion.", COMP_SOURCE)
            ),
        }
    )

    sim.set_time(T0)
    saga = sim.call(knot, "start_saga", [blueprint, "trip-1"])
    assert saga == 1

    view = sim.read(knot, "get_saga", [saga])
    assert view["status"] == SAGA_COMPLETED
    assert sim.read(knot, "is_completed", [saga]) is True
    assert len(view["receipt_ids"]) == 2
    assert len(view["terminal_hash"]) == 64

    assert sim.read(knot, "get_step_state", [saga, 0])["status"] == STEP_CONFIRMED
    assert sim.read(knot, "get_step_state", [saga, 1])["status"] == STEP_CONFIRMED

    receipts = [sim.read(knot, "get_receipt", [rid]) for rid in view["receipt_ids"]]
    assert [r["ordinal"] for r in receipts] == [0, 1]
    assert [r["phase"] for r in receipts] == [PHASE_EXECUTION, PHASE_EXECUTION]
    assert [r["verdict"] for r in receipts] == [VERDICT_SATISFIED, VERDICT_SATISFIED]
    assert all(len(r["receipt_hash"]) == 64 for r in receipts)
    assert all(r["evidence_ref"] == EXEC_SOURCE for r in receipts)

    # Exactly one side effect per dispatched step, none on the compensation leg.
    assert sim.read(participant, "get_effect_counts") == {
        "execution_effects": 2,
        "compensation_effects": 0,
    }


def test_failed_execution_runs_reverse_compensation(sim, llm_text):
    knot, participant, blueprint = new_workflow(sim)
    sim.install_mocks(
        {
            "completed successfully": llm_text(
                decision("NOT_SATISFIED", "The source does not settle the criterion.", "")
            ),
            "was reversed": llm_text(
                decision("SATISFIED", "The source establishes the criterion.", COMP_SOURCE)
            ),
        }
    )

    sim.set_time(T0)
    saga = sim.call(knot, "start_saga", [blueprint, "trip-1"])

    view = sim.read(knot, "get_saga", [saga])
    assert view["status"] == SAGA_COMPENSATED
    assert sim.read(knot, "is_compensated", [saga]) is True
    assert sim.read(knot, "is_stuck", [saga]) is False

    step = sim.read(knot, "get_step_state", [saga, 0])
    execution_receipt = sim.read(knot, "get_receipt", [step["execution_receipt_id"]])
    compensation_receipt = sim.read(knot, "get_receipt", [step["compensation_receipt_id"]])
    assert execution_receipt["phase"] == PHASE_EXECUTION
    assert execution_receipt["verdict"] == VERDICT_NOT_SATISFIED
    assert compensation_receipt["phase"] == PHASE_COMPENSATION
    assert compensation_receipt["verdict"] == VERDICT_SATISFIED
    assert compensation_receipt["evidence_ref"] == COMP_SOURCE

    assert sim.read(participant, "get_effect_counts") == {
        "execution_effects": 1,
        "compensation_effects": 1,
    }


def test_failed_compensation_parks_stuck_and_exhausts_retry_budget(sim, llm_text):
    knot, participant, blueprint = new_workflow(sim)
    sim.install_mocks(
        {
            "completed successfully": llm_text(
                decision("NOT_SATISFIED", "The source does not settle the criterion.", "")
            ),
            "was reversed": llm_text(
                decision("NOT_SATISFIED", "The source does not settle the criterion.", "")
            ),
        }
    )

    sim.set_time(T0)
    saga = sim.call(knot, "start_saga", [blueprint, "trip-1"])

    assert sim.read(knot, "get_saga", [saga])["status"] == SAGA_STUCK
    assert sim.read(knot, "is_stuck", [saga]) is True

    first_step = sim.read(knot, "get_step_state", [saga, 0])
    operation_id = first_step["compensation_operation_id"]
    assert operation_id

    # Only the blueprint owner (the saga controller) may retry.
    with pytest.raises(Exception, match="only saga controller"):
        sim.call(knot, "retry_compensation", [saga], sender=sim.attacker)

    for attempts in (2, 3):
        sim.call(knot, "retry_compensation", [saga], sender=sim.owner)
        step = sim.read(knot, "get_step_state", [saga, 0])
        assert step["compensation_attempts"] == attempts
        assert step["status"] == STEP_COMPENSATION_FAILED
        # The retry revalidates the same logical operation, never a new one.
        assert step["compensation_operation_id"] == operation_id
        assert sim.read(knot, "get_saga", [saga])["status"] == SAGA_STUCK

    with pytest.raises(Exception, match="attempt budget exhausted"):
        sim.call(knot, "retry_compensation", [saga], sender=sim.owner)

    record = sim.read(participant, "get_operation", [operation_id])
    assert record["calls"] == 3  # three dispatches, one effect
    assert sim.read(participant, "get_effect_counts")["compensation_effects"] == 1


def test_timeout_crystallizes_an_unanswered_compensation(sim, llm_text):
    # The compensation payload points at a scenario the participant never
    # configured, so the callback never comes back and only the timeout can
    # advance the saga.
    knot, participant, blueprint = new_workflow(sim, comp_payload="999", timeout=300)
    sim.install_mocks(
        {
            "completed successfully": llm_text(
                decision("NOT_SATISFIED", "The source does not settle the criterion.", "")
            ),
            "was reversed": llm_text(
                decision("SATISFIED", "The source establishes the criterion.", COMP_SOURCE)
            ),
        }
    )

    sim.set_time(T0)
    saga = sim.call(knot, "start_saga", [blueprint, "trip-1"])

    assert sim.read(knot, "get_saga", [saga])["status"] == SAGA_COMPENSATING
    step = sim.read(knot, "get_step_state", [saga, 0])
    assert step["status"] == STEP_COMPENSATION_DISPATCHED
    operation_id = step["compensation_operation_id"]
    assert operation_id
    # The participant rejected the dispatch (scenario 999 was never sealed), so
    # the operation exists on Knot's side but never reached the participant.
    with pytest.raises(Exception, match="operation not found"):
        sim.read(participant, "get_operation", [operation_id])
    assert sim.read(participant, "get_effect_counts") == {
        "execution_effects": 1,
        "compensation_effects": 0,
    }

    with pytest.raises(Exception, match="deadline has not passed"):
        sim.call(knot, "timeout_current", [saga])

    sim.set_time(T0_PLUS_301)
    sim.call(knot, "timeout_current", [saga])

    assert sim.read(knot, "get_saga", [saga])["status"] == SAGA_STUCK
    assert sim.read(knot, "is_stuck", [saga]) is True

    step = sim.read(knot, "get_step_state", [saga, 0])
    assert step["status"] == STEP_COMPENSATION_FAILED
    timeout_receipt = sim.read(knot, "get_receipt", [step["compensation_receipt_id"]])
    assert timeout_receipt["phase"] == PHASE_COMPENSATION
    assert timeout_receipt["verdict"] == VERDICT_TIMEOUT
    assert timeout_receipt["reason"] == "compensation callback deadline passed"

    # A late callback cannot revive a crystallized step.
    with pytest.raises(Exception, match="saga is not compensating"):
        sim.call(
            knot,
            "report_compensation",
            [saga, 0, operation_id, COMP_SOURCE],
            sender=participant,
        )
    assert sim.read(knot, "get_saga", [saga])["status"] == SAGA_STUCK


def test_participant_only_accepts_dispatches_from_its_pinned_coordinator(sim):
    knot = sim.deploy(sim.knot_path)
    unconfigured = sim.deploy(sim.participant_path)
    participant = sim.deploy(sim.participant_path)

    sim.write(participant, "set_coordinator", [knot])
    sim.write(participant, "configure_scenario", [1, EXEC_SOURCE, COMP_SOURCE])
    sim.write(participant, "seal_scenario", [1])

    with pytest.raises(Exception, match="coordinator is not configured"):
        sim.write(
            unconfigured,
            "execute_step",
            [knot, 1, 0, "aa" * 32, "1", "trip-1"],
            sender=sim.owner,
        )

    # A third party cannot dispatch work even while naming the real coordinator.
    with pytest.raises(Exception, match="caller is not the pinned coordinator"):
        sim.write(
            participant,
            "execute_step",
            [knot, 1, 0, "bb" * 32, "1", "trip-1"],
            sender=sim.attacker,
        )

    # The pinned coordinator can, and the effect is recorded exactly once.
    sim.write(
        participant,
        "execute_step",
        [knot, 1, 0, "cc" * 32, "1", "trip-1"],
        sender=knot,
    )
    assert sim.read(participant, "get_effect_counts") == {
        "execution_effects": 1,
        "compensation_effects": 0,
    }
