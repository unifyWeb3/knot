# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng" }

import genlayer as gl
from dataclasses import dataclass

Address = gl.Address
TreeMap = gl.storage.TreeMap
allow_storage = gl.storage.allow
u8 = gl.u8
u256 = gl.u256


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
MAX_EVIDENCE_REF_LEN = 1200
PHASE_EXECUTION = 1
PHASE_COMPENSATION = 2


@allow_storage
@dataclass
class Scenario:
    execution_evidence: str
    compensation_evidence: str
    sealed: bool


@allow_storage
@dataclass
class OperationRecord:
    saga_id: u256
    step_id: u256
    scenario_id: u256
    kind: u8
    evidence_ref: str
    calls: u8


class ScenarioConfigured(gl.chain.Event):
    def __init__(self, scenario_id: u256, /, **blob): ...


class ScenarioSealed(gl.chain.Event):
    def __init__(self, scenario_id: u256, /, **blob): ...


class OperationRecorded(gl.chain.Event):
    def __init__(self, operation_id: str, saga_id: u256, step_id: u256, /, **blob): ...


class ReferenceParticipant(gl.contract.Contract):
    """Deterministic, idempotent participant harness for Knot integration tests."""

    owner: Address
    coordinator: Address
    coordinator_locked: bool
    scenarios: TreeMap[u256, Scenario]
    operations: TreeMap[str, OperationRecord]
    execution_effect_count: u256
    compensation_effect_count: u256

    def __init__(self):
        self.owner = gl.message.sender_address
        self.coordinator_locked = False

    def _address_text(self, value: Address) -> str:
        return str(value).lower()

    def _require_owner(self) -> None:
        if self._address_text(gl.message.sender_address) != self._address_text(self.owner):
            raise gl.vm.UserError("EXPECTED: only participant owner may perform this action")

    def _require_coordinator(self, coordinator: Address) -> None:
        if not self.coordinator_locked:
            raise gl.vm.UserError("EXPECTED: participant coordinator is not configured")
        if self._address_text(gl.message.sender_address) != self._address_text(coordinator):
            raise gl.vm.UserError("EXPECTED: caller is not the pinned coordinator")
        if self._address_text(self.coordinator) != self._address_text(coordinator):
            raise gl.vm.UserError("EXPECTED: coordinator mismatch")

    def _scenario_id(self, payload: str) -> u256:
        text = str(payload).strip()
        if text == "" or not text.isdigit() or int(text) <= 0:
            raise gl.vm.UserError("EXPECTED: participant payload must be a positive scenario id")
        return u256(int(text))

    def _evidence_ref(self, value: str) -> str:
        text = str(value).strip()
        if text == "" or len(text) > MAX_EVIDENCE_REF_LEN:
            raise gl.vm.UserError("EXPECTED: invalid scenario evidence reference")
        return text

    def _record(
        self,
        coordinator: Address,
        saga_id: u256,
        step_id: u256,
        operation_id: str,
        scenario_id: u256,
        kind: u8,
    ) -> str:
        existing = self.operations.get(operation_id)
        if existing is not None:
            existing.calls = u8(int(existing.calls) + 1)
            self.operations[operation_id] = existing
            return existing.evidence_ref

        scenario = self.scenarios.get(scenario_id)
        if scenario is None or not scenario.sealed:
            raise gl.vm.UserError("EXPECTED: scenario is missing or not sealed")
        if int(kind) == PHASE_EXECUTION:
            evidence_ref = scenario.execution_evidence
            self.execution_effect_count = u256(int(self.execution_effect_count) + 1)
        else:
            evidence_ref = scenario.compensation_evidence
            self.compensation_effect_count = u256(int(self.compensation_effect_count) + 1)
        self.operations[operation_id] = OperationRecord(
            saga_id=saga_id,
            step_id=step_id,
            scenario_id=scenario_id,
            kind=kind,
            evidence_ref=evidence_ref,
            calls=u8(1),
        )
        OperationRecorded(operation_id, saga_id, step_id, kind=int(kind)).emit()
        return evidence_ref

    @gl.public.write
    def set_coordinator(self, coordinator: Address) -> None:
        self._require_owner()
        if self.coordinator_locked:
            raise gl.vm.UserError("EXPECTED: coordinator is already locked")
        if self._address_text(coordinator) == ZERO_ADDRESS:
            raise gl.vm.UserError("EXPECTED: coordinator must not be zero address")
        self.coordinator = coordinator
        self.coordinator_locked = True

    @gl.public.write
    def configure_scenario(self, scenario_id: u256, execution_evidence: str, compensation_evidence: str) -> None:
        self._require_owner()
        existing = self.scenarios.get(scenario_id)
        if existing is not None and existing.sealed:
            raise gl.vm.UserError("EXPECTED: scenario is already sealed")
        self.scenarios[scenario_id] = Scenario(
            execution_evidence=self._evidence_ref(execution_evidence),
            compensation_evidence=self._evidence_ref(compensation_evidence),
            sealed=False,
        )
        ScenarioConfigured(scenario_id).emit()

    @gl.public.write
    def seal_scenario(self, scenario_id: u256) -> None:
        self._require_owner()
        scenario = self.scenarios.get(scenario_id)
        if scenario is None:
            raise gl.vm.UserError("EXPECTED: scenario not found")
        if scenario.sealed:
            raise gl.vm.UserError("EXPECTED: scenario is already sealed")
        scenario.sealed = True
        self.scenarios[scenario_id] = scenario
        ScenarioSealed(scenario_id).emit()

    @gl.public.write
    def execute_step(
        self,
        coordinator: Address,
        saga_id: u256,
        step_id: u256,
        operation_id: str,
        action_payload: str,
        context: str,
    ) -> None:
        self._require_coordinator(coordinator)
        scenario_id = self._scenario_id(action_payload)
        evidence_ref = self._record(coordinator, saga_id, step_id, operation_id, scenario_id, u8(PHASE_EXECUTION))
        gl.contract.get_at(coordinator).emit(on="finalized").report_execution(
            saga_id, step_id, operation_id, evidence_ref
        )

    @gl.public.write
    def compensate_step(
        self,
        coordinator: Address,
        saga_id: u256,
        step_id: u256,
        operation_id: str,
        compensation_payload: str,
        context: str,
    ) -> None:
        self._require_coordinator(coordinator)
        scenario_id = self._scenario_id(compensation_payload)
        evidence_ref = self._record(coordinator, saga_id, step_id, operation_id, scenario_id, u8(PHASE_COMPENSATION))
        gl.contract.get_at(coordinator).emit(on="finalized").report_compensation(
            saga_id, step_id, operation_id, evidence_ref
        )

    @gl.public.view
    def get_scenario(self, scenario_id: u256) -> dict:
        scenario = self.scenarios.get(scenario_id)
        if scenario is None:
            raise gl.vm.UserError("EXPECTED: scenario not found")
        return {
            "scenario_id": int(scenario_id),
            "execution_evidence": scenario.execution_evidence,
            "compensation_evidence": scenario.compensation_evidence,
            "sealed": scenario.sealed,
        }

    @gl.public.view
    def get_operation(self, operation_id: str) -> dict:
        record = self.operations.get(operation_id)
        if record is None:
            raise gl.vm.UserError("EXPECTED: operation not found")
        return {
            "operation_id": operation_id,
            "saga_id": int(record.saga_id),
            "step_id": int(record.step_id),
            "scenario_id": int(record.scenario_id),
            "kind": int(record.kind),
            "evidence_ref": record.evidence_ref,
            "calls": int(record.calls),
        }

    @gl.public.view
    def get_effect_counts(self) -> dict:
        return {
            "execution_effects": int(self.execution_effect_count),
            "compensation_effects": int(self.compensation_effect_count),
        }
