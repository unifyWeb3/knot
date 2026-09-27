"""Direct-mode tests for the reference participant's deterministic controls."""

CONTRACT = "contracts/reference_participant.py"


def address(name):
    from gltest.direct import create_address

    return create_address(name)


def test_scenario_seals_once(direct_vm, direct_deploy):
    participant = direct_deploy(CONTRACT)
    participant.configure_scenario(1, "execution receipt", "compensation receipt")
    participant.seal_scenario(1)
    assert participant.get_scenario(1)["sealed"] is True

    with direct_vm.expect_revert("already sealed"):
        participant.configure_scenario(1, "other", "other")


def test_coordinator_locks_once(direct_vm, direct_deploy):
    participant = direct_deploy(CONTRACT)
    participant.set_coordinator(address("coordinator"))

    with direct_vm.expect_revert("already locked"):
        participant.set_coordinator(address("other"))


def test_unsealed_scenario_cannot_claim_effects(direct_vm, direct_deploy):
    participant = direct_deploy(CONTRACT)
    participant.configure_scenario(1, "execution receipt", "compensation receipt")

    with direct_vm.expect_revert("coordinator is not configured"):
        participant.execute_step(address("coordinator"), 1, 0, "operation-1", "1", "context")
