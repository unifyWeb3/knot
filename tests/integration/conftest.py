"""Integration harness: drive Knot's cross-contract leg on GenLayer Sim.

The direct-mode runner cannot execute cross-contract messages, so these tests
deploy both contracts on ``glsim`` (the in-process GenLayer simulator shipped
with gltest) and assert the dispatch -> participant -> callback round trip.

Two shims are needed to bridge glsim 0.30.0-rc2 to the pinned v0.6 std lib;
both are documented in :func:`_apply_glsim_shims` and :meth:`Sim.sync_time`.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
KNOT_PATH = str(REPO_ROOT / "contracts" / "knot.py")
PARTICIPANT_PATH = str(REPO_ROOT / "contracts" / "reference_participant.py")

OWNER = "0x" + "11" * 20
ATTACKER = "0x" + "22" * 20

# glsim resolves its GenVM bundle tree from GENVM_VERSION. The pinned contract
# header (py-genlayer:5jycge...) ships in both rc5 and rc6; rc5 is the tree that
# is cached locally. Export GENVM_VERSION before running to override.
os.environ.setdefault("GENVM_VERSION", "v0.6.0-rc5")


class SimError(RuntimeError):
    """A JSON-RPC level failure returned by glsim."""


def _apply_glsim_shims() -> None:
    """Teach glsim the two v0.6 std-lib details it does not know yet.

    1. **Cross-contract calldata key.** The v0.6 std lib encodes an emitted
       method name under the empty key (``{"": "execute_step", "args": [...]}``)
       while glsim reads ``calldata["method"]``, so every emitted message was
       dropped: ``[PostMessage] enqueueing None to Address("0x...")``. The shim
       copies the std-lib key into the key glsim expects; without it no dispatch
       ever reaches a participant.
    2. **Host -> guest argument types.** glsim decodes RPC calldata with the
       host ABI (``genlayer_py.CalldataAddress``) and hands those objects to
       contract code, but the guest encoder in ``genlayer.calldata`` only
       understands ``genlayer.types.Address``. Any address that is later stored
       and re-emitted (``set_coordinator`` -> ``CoordinatorPinned``) therefore
       raised ``not calldata encodable addr#...: CalldataAddress``. The shim
       rewrites arguments at the ``call_method`` boundary, which covers both
       RPC calls and the drained cross-contract messages.
    3. **Block datetime.** Handled in :meth:`Sim.sync_time` rather than by
       patching glsim: glsim only syncs sender/value/chain_id into
       ``genlayer.message.raw``, so ``raw["datetime"]`` (the block time contracts
       read) would stay frozen at import and ``sim_setTime`` would never reach
       Knot's deadline math.
    """
    from glsim.engine import SimEngine

    for name in ("_handle_post_in_contract", "_handle_call_in_contract"):
        original = getattr(SimEngine, name)
        if getattr(original, "_knot_calldata_shim", False):
            continue

        def shim(self, vm, data, _original=original):
            calldata_obj = data.get("calldata")
            if isinstance(calldata_obj, dict) and "method" not in calldata_obj and "" in calldata_obj:
                data = dict(data)
                data["calldata"] = {**calldata_obj, "method": calldata_obj[""]}
            return _original(self, vm, data)

        shim._knot_calldata_shim = True  # type: ignore[attr-defined]
        setattr(SimEngine, name, shim)

    original_call_method = SimEngine.call_method
    if not getattr(original_call_method, "_knot_guest_type_shim", False):
        from genlayer_py.types.calldata import CalldataAddress

        def to_guest(value):
            if isinstance(value, CalldataAddress):
                from genlayer.types import Address

                return Address(value.as_bytes)
            if isinstance(value, dict):
                return {key: to_guest(item) for key, item in value.items()}
            if isinstance(value, list):
                return [to_guest(item) for item in value]
            return value

        def call_method(self, contract_address, method_name, args=None, kwargs=None, sender=None):
            # Imported lazily: genlayer.types resolves only once the engine has
            # activated and installed the guest SDK paths.
            return original_call_method(
                self,
                contract_address,
                method_name,
                [to_guest(arg) for arg in (args or [])],
                {key: to_guest(value) for key, value in (kwargs or {}).items()},
                sender,
            )

        call_method._knot_guest_type_shim = True  # type: ignore[attr-defined]
        SimEngine.call_method = call_method


class Sim:
    """Thin JSON-RPC client over an in-process glsim app."""

    def __init__(self, client, store, engine):
        self.client = client
        self.store = store
        self.engine = engine
        self.owner = OWNER
        self.attacker = ATTACKER
        self.knot_path = KNOT_PATH
        self.participant_path = PARTICIPANT_PATH
        self._request_id = 0

    # -- plumbing -----------------------------------------------------------

    def sync_time(self) -> None:
        """Publish glsim's simulated clock as the contract block time."""
        message = sys.modules.get("genlayer.message")
        raw = getattr(message, "raw", None)
        if isinstance(raw, dict):
            raw["datetime"] = self.store.get_effective_datetime()

    def rpc(self, method: str, params=None):
        self.sync_time()
        self._request_id += 1
        response = self.client.post(
            "/api",
            json={
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": method,
                "params": params if params is not None else [],
            },
        )
        payload = response.json()
        error = payload.get("error")
        if error:
            raise SimError(f"{method}: {error.get('message')}")
        return payload.get("result")

    # -- contract actions ---------------------------------------------------

    def deploy(self, code_path: str, sender: str = OWNER) -> str:
        return self.rpc(
            "sim_deploy", {"code_path": code_path, "sender": sender}
        )["contract_address"]

    def call(self, to: str, method: str, args=(), sender: str = OWNER):
        """Persistent write that rolls back when the contract reverts.

        glsim's plain ``sim_call`` accepts JSON arguments only, so it is used
        for every method whose arguments are not addresses.
        """
        result = self.rpc(
            "sim_call",
            {"to": to, "method": method, "args": list(args), "kwargs": {}, "sender": sender},
        )
        return result["result"] if isinstance(result, dict) else result

    def write(self, to: str, method: str, args=(), sender: str = OWNER):
        """Persistent write for methods that take addresses.

        Addresses are typed through ``genlayer_py`` calldata (a bare JSON string
        would reach the storage setter as ``str`` and fail), so this goes
        through ``gen_call``, which persists state.
        """
        from genlayer_py.abi import calldata
        from genlayer_py.types.calldata import CalldataAddress

        def typed(value):
            if isinstance(value, str) and value.startswith("0x") and len(value) == 42:
                return CalldataAddress(value)
            return value

        encoded = calldata.encode(
            {"method": method, "args": [typed(a) for a in args], "kwargs": {}}
        )
        import rlp

        data = "0x" + rlp.encode([encoded, b"\x00"]).hex()
        raw = self.rpc(
            "gen_call", [{"type": "write", "to": to, "from": sender, "data": data}]
        )
        return calldata.decode(bytes.fromhex(raw))

    def read(self, to: str, method: str, args=()):
        result = self.rpc(
            "sim_read", {"to": to, "method": method, "args": list(args), "kwargs": {}}
        )
        return result["result"] if isinstance(result, dict) else result

    def install_mocks(self, llm_mocks: dict, web_mocks: dict | None = None, strict: bool = True) -> None:
        """Replace the persistent mock set (previous patterns are dropped)."""
        from glsim import server as glsim_server

        self.engine._persistent_llm_mocks = dict(llm_mocks)
        self.engine._persistent_web_mocks = dict(web_mocks or {})
        self.engine.vm._strict_mock_mode = bool(strict)
        glsim_server._clear_sim_config_mocks(self.engine)

    def set_time(self, iso_datetime: str) -> None:
        self.rpc("sim_setTime", {"datetime": iso_datetime})
        self.sync_time()


@pytest.fixture(scope="session")
def sim():
    pytest.importorskip("glsim", reason="integration tests need the glsim local network")
    pytest.importorskip(
        "starlette.testclient", reason="integration tests need starlette + httpx"
    )
    _apply_glsim_shims()

    from glsim.server import create_app
    from starlette.testclient import TestClient

    app = create_app(
        num_validators=1,
        max_rotations=1,
        llm_provider=None,
        use_browser=False,
        verbose=False,
        seed="knot-integration",
    )
    with TestClient(app) as client:
        yield Sim(client, app.state.store, app.state.engine)


@pytest.fixture
def llm_text():
    """Model reply as prose + JSON, which is what ``response_format="text"`` gets.

    gltest's mock layer auto-parses *bare* JSON strings into dicts, which the
    text decoder rejects, so a non-JSON prefix is required to keep a mock
    response in text form.
    """

    def make(payload: dict) -> str:
        return "Decision:\n" + json.dumps(payload)

    return make
