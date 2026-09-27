"""Direct-mode tests for Knot's saga lifecycle, callbacks, and recovery paths."""

import json
import re

CONTRACT = "contracts/knot.py"
TEXT_MODE = 1

SAGA_ACTIVE = 1
SAGA_COMPLETED = 2
SAGA_COMPENSATING = 3
SAGA_COMPENSATED = 4
SAGA_STUCK = 5

STEP_DISPATCHED = 1
STEP_CONFIRMED = 2
STEP_EXECUTION_FAILED = 3
STEP_COMPENSATION_DISPATCHED = 4
STEP_COMPENSATED = 5
STEP_COMPENSATION_FAILED = 6

PHASE_EXECUTION = 1
PHASE_COMPENSATION = 2

VERDICT_SATISFIED = 1
VERDICT_NOT_SATISFIED = 2
VERDICT_TIMEOUT = 5

T0 = "2026-09-25T10:00:00+00:00"


def address(name):
    from gltest.direct import create_address

    return create_address(name)


def set_time(vm, timestamp: str) -> None:
    """Warp the VM clock *and* the message datetime the contract reads.

    gltest's ``vm.warp`` only updates its own clock; the SDK snapshot of
    ``genlayer.message.raw`` is injected once at import, so the contract's
    block timestamp has to be updated in place as well.
    """
    import sys

    vm.warp(timestamp)
    message = sys.modules.get("genlayer.message")
    raw = getattr(message, "raw", None) if message is not None else None
    if isinstance(raw, dict):
        raw["datetime"] = timestamp


def llm_text(payload: dict) -> str:
    """Encode a decision as prose+JSON text.

    The contract requests ``response_format="text"`` and parses the JSON object
    out of the model reply itself. gltest's mock layer auto-parses *bare* JSON
    strings into dicts, which the text decoder rejects, so a non-JSON prefix is
    required to keep the mock response as text.
    """
    return "Decision:\n" + json.dumps(payload)


def mock_verdict(vm, source: str, verdict: str) -> None:
    """Answer only prompts whose SOURCE equals *source* (first match wins)."""
    payload = {
        "verdict": verdict,
        "reason": "The source establishes the criterion.",
        "evidence": source[:80] if verdict == "SATISFIED" else "",
    }
    vm.mock_llm(r"SOURCE=" + re.escape(source), llm_text(payload))


def add_step(contract, blueprint_id, participant, label, timeout=600):
    return contract.add_step(
        blueprint_id,
        participant,
        label,
        f"perform {label}",
        f"The evidence establishes that {label} completed successfully.",
        TEXT_MODE,
        "",
        f"reverse {label}",
        f"The evidence establishes that {label} was reversed.",
        TEXT_MODE,
        "",
        timeout,
    )


def build_saga(vm, contract, participant, labels=("one", "two"), context="trip-1"):
    vm.sender = address("owner")
    blueprint_id = contract.create_blueprint("Travel", "Coordinate dependent steps.")
    for label in labels:
        add_step(contract, blueprint_id, participant, label)
    contract.seal_blueprint(blueprint_id)
    set_time(vm, T0)
    saga_id = contract.start_saga(blueprint_id, context)
    return blueprint_id, saga_id


def step_state(contract, saga_id, ordinal):
    return contract.get_step_state(saga_id, ordinal)


def test_saga_success_completes_with_receipts(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    participant = address("participant")
    _, saga_id = build_saga(direct_vm, contract, participant)

    state0 = step_state(contract, saga_id, 0)
    assert state0["status"] == STEP_DISPATCHED
    assert state0["execution_attempts"] == 1
    assert len(state0["execution_operation_id"]) == 64
    assert contract.get_saga(saga_id)["status"] == SAGA_ACTIVE

    direct_vm.sender = participant
    first_source = "Reservation H-100 is confirmed and active."
    mock_verdict(direct_vm, first_source, "SATISFIED")
    contract.report_execution(saga_id, 0, state0["execution_operation_id"], first_source)

    state0 = step_state(contract, saga_id, 0)
    state1 = step_state(contract, saga_id, 1)
    assert state0["status"] == STEP_CONFIRMED
    assert state1["status"] == STEP_DISPATCHED
    assert len(contract.get_saga(saga_id)["receipt_ids"]) == 1

    second_source = "The second booking reference is active."
    mock_verdict(direct_vm, second_source, "SATISFIED")
    contract.report_execution(saga_id, 1, state1["execution_operation_id"], second_source)

    saga = contract.get_saga(saga_id)
    assert saga["status"] == SAGA_COMPLETED
    assert contract.is_completed(saga_id) is True
    assert contract.is_stuck(saga_id) is False
    assert len(saga["receipt_ids"]) == 2
    assert len(saga["terminal_hash"]) == 64

    first_receipt = contract.get_receipt(saga["receipt_ids"][0])
    second_receipt = contract.get_receipt(saga["receipt_ids"][1])
    assert first_receipt["phase"] == PHASE_EXECUTION
    assert first_receipt["ordinal"] == 0
    assert first_receipt["verdict"] == VERDICT_SATISFIED
    assert second_receipt["ordinal"] == 1
    assert second_receipt["verdict"] == VERDICT_SATISFIED
    assert len(first_receipt["receipt_hash"]) == 64


def test_duplicate_execution_callback_is_a_noop(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    participant = address("participant")
    _, saga_id = build_saga(direct_vm, contract, participant)

    state0 = step_state(contract, saga_id, 0)
    source = "Reservation H-100 is confirmed and active."
    direct_vm.sender = participant
    mock_verdict(direct_vm, source, "SATISFIED")
    contract.report_execution(saga_id, 0, state0["execution_operation_id"], source)

    state1 = step_state(contract, saga_id, 1)
    contract.report_execution(saga_id, 0, state0["execution_operation_id"], source)

    assert step_state(contract, saga_id, 0)["status"] == STEP_CONFIRMED
    assert step_state(contract, saga_id, 1)["status"] == STEP_DISPATCHED
    assert step_state(contract, saga_id, 1)["execution_attempts"] == 1
    assert len(contract.get_saga(saga_id)["receipt_ids"]) == 1
    assert state1["execution_operation_id"] == step_state(contract, saga_id, 1)[
        "execution_operation_id"
    ]


def test_callback_guards_reject_foreign_senders_and_ids(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    participant = address("participant")
    _, saga_id = build_saga(direct_vm, contract, participant)
    state0 = step_state(contract, saga_id, 0)
    source = "Reservation H-100 is confirmed and active."

    direct_vm.sender = address("attacker")
    with direct_vm.expect_revert("frozen participant"):
        contract.report_execution(saga_id, 0, state0["execution_operation_id"], source)

    direct_vm.sender = participant
    with direct_vm.expect_revert("operation id mismatch"):
        contract.report_execution(saga_id, 0, "00" * 32, source)
    with direct_vm.expect_revert("out of range"):
        contract.report_execution(saga_id, 7, state0["execution_operation_id"], source)

    # The controller guard on retry is independent of the callback path.
    direct_vm.sender = address("attacker")
    with direct_vm.expect_revert("only saga controller"):
        contract.retry_compensation(saga_id)

    # Retrying is permissionless only for the controller; a non-stuck saga
    # still rejects the call after the controller check passes.
    direct_vm.sender = address("owner")
    with direct_vm.expect_revert("not stuck"):
        contract.retry_compensation(saga_id)


def test_failed_execution_runs_reverse_compensation(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    participant = address("participant")
    _, saga_id = build_saga(direct_vm, contract, participant)

    state0 = step_state(contract, saga_id, 0)
    source = "Reservation H-100 was cancelled by the provider."
    direct_vm.sender = participant
    mock_verdict(direct_vm, source, "NOT_SATISFIED")
    contract.report_execution(saga_id, 0, state0["execution_operation_id"], source)

    assert contract.get_saga(saga_id)["status"] == SAGA_COMPENSATING
    state0 = step_state(contract, saga_id, 0)
    assert state0["status"] == STEP_COMPENSATION_DISPATCHED
    assert state0["compensation_attempts"] == 1
    assert len(state0["compensation_operation_id"]) == 64
    execution_receipt = contract.get_receipt(state0["execution_receipt_id"])
    assert execution_receipt["verdict"] == VERDICT_NOT_SATISFIED

    comp_source = "The reservation for trip one was reversed in full."
    mock_verdict(direct_vm, comp_source, "SATISFIED")
    contract.report_compensation(saga_id, 0, state0["compensation_operation_id"], comp_source)

    assert contract.get_saga(saga_id)["status"] == SAGA_COMPENSATED
    assert contract.is_compensated(saga_id) is True
    assert contract.is_stuck(saga_id) is False
    saga = contract.get_saga(saga_id)
    assert len(saga["receipt_ids"]) == 2
    assert len(saga["terminal_hash"]) == 64
    compensation_receipt = contract.get_receipt(step_state(contract, saga_id, 0)[
        "compensation_receipt_id"
    ])
    assert compensation_receipt["phase"] == PHASE_COMPENSATION
    assert compensation_receipt["verdict"] == VERDICT_SATISFIED


def test_failed_compensation_becomes_stuck_then_budget_exhausts(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    participant = address("participant")
    controller = address("owner")
    _, saga_id = build_saga(direct_vm, contract, participant)

    state0 = step_state(contract, saga_id, 0)
    exec_source = "Reservation H-100 was cancelled by the provider."
    direct_vm.sender = participant
    mock_verdict(direct_vm, exec_source, "NOT_SATISFIED")
    contract.report_execution(saga_id, 0, state0["execution_operation_id"], exec_source)

    comp_source = "The reversal attempt for trip one failed."
    mock_verdict(direct_vm, comp_source, "NOT_SATISFIED")
    first_operation = step_state(contract, saga_id, 0)["compensation_operation_id"]
    contract.report_compensation(saga_id, 0, first_operation, comp_source)

    assert contract.get_saga(saga_id)["status"] == SAGA_STUCK
    assert contract.is_stuck(saga_id) is True
    assert step_state(contract, saga_id, 0)["status"] == STEP_COMPENSATION_FAILED

    # Only the controller may retry, and retries reuse the same operation id.
    direct_vm.sender = participant
    with direct_vm.expect_revert("only saga controller"):
        contract.retry_compensation(saga_id)

    direct_vm.sender = controller
    for attempt in (2, 3):
        direct_vm.sender = controller
        contract.retry_compensation(saga_id)
        state = step_state(contract, saga_id, 0)
        assert state["status"] == STEP_COMPENSATION_DISPATCHED
        assert state["compensation_attempts"] == attempt
        assert state["compensation_operation_id"] == first_operation

        direct_vm.sender = participant
        contract.report_compensation(saga_id, 0, first_operation, comp_source)
        assert contract.get_saga(saga_id)["status"] == SAGA_STUCK

    direct_vm.sender = controller
    with direct_vm.expect_revert("attempt budget exhausted"):
        contract.retry_compensation(saga_id)


def test_timeout_crystallizes_before_late_callbacks(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    participant = address("participant")
    _, saga_id = build_saga(direct_vm, contract, participant)
    state0 = step_state(contract, saga_id, 0)

    with direct_vm.expect_revert("deadline has not passed"):
        contract.timeout_current(saga_id)

    set_time(direct_vm, "2026-09-25T10:10:01+00:00")
    contract.timeout_current(saga_id)

    state0 = step_state(contract, saga_id, 0)
    assert state0["status"] == STEP_COMPENSATION_DISPATCHED
    timeout_receipt = contract.get_receipt(state0["execution_receipt_id"])
    assert timeout_receipt["verdict"] == VERDICT_TIMEOUT
    assert contract.get_saga(saga_id)["status"] == SAGA_COMPENSATING

    # A late execution callback can no longer move a crystallized step.
    direct_vm.sender = participant
    with direct_vm.expect_revert("saga is not active"):
        contract.report_execution(saga_id, 0, state0["execution_operation_id"], "late evidence")

    # The compensation window closes the same way, parking the saga as STUCK.
    set_time(direct_vm, "2026-09-25T10:20:02+00:00")
    contract.timeout_current(saga_id)
    assert contract.get_saga(saga_id)["status"] == SAGA_STUCK
    assert contract.is_stuck(saga_id) is True
    assert len(contract.get_saga(saga_id)["terminal_hash"]) == 64
