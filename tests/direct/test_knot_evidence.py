"""Direct-mode tests for the bounded evidence judgment seam."""

import json

CONTRACT = "contracts/knot.py"
URL_MODE = 2
PREFIX = "https://raw.example.com/unifyWeb3/knot/commit/fixtures/"


def _llm_json(payload: dict) -> bytes:
    """Encode an LLM decision as bytes.

    gltest's mock auto-parses JSON *strings* into dicts, but the v0.6 std lib
    requires ``exec_prompt(response_format="json")`` to receive the raw JSON
    text. Passing bytes keeps the mock from parsing while remaining valid JSON
    for the std lib decoder.
    """
    return json.dumps(payload).encode("utf-8")


def test_evidence_judgment_rederives_and_agrees(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    direct_vm.check_pickling = True
    direct_vm.mock_web(
        r"raw\.example\.com/.*",
        {"status": 200, "body": "Reservation H-100 is confirmed and active."},
    )
    direct_vm.mock_llm(
        r".*",
        _llm_json(
            {
                "verdict": "SATISFIED",
                "reason": "The source states that the reservation is confirmed.",
                "evidence": "Reservation H-100 is confirmed and active.",
            }
        ),
    )

    decision = contract._judge(
        URL_MODE,
        "The reservation is confirmed and active.",
        "hotel",
        "trip-1",
        PREFIX + "hotel.txt",
        PREFIX,
    )
    assert decision["verdict"] == 1
    assert direct_vm.run_validator() is True


def test_validator_rejects_a_different_source(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    direct_vm.mock_web(
        r"raw\.example\.com/.*",
        {"status": 200, "body": "Reservation H-100 is confirmed and active."},
    )
    direct_vm.mock_llm(
        r".*",
        _llm_json(
            {
                "verdict": "SATISFIED",
                "reason": "The source states that the reservation is confirmed.",
                "evidence": "Reservation H-100 is confirmed and active.",
            }
        ),
    )
    contract._judge(
        URL_MODE,
        "The reservation is confirmed and active.",
        "hotel",
        "trip-1",
        PREFIX + "hotel.txt",
        PREFIX,
    )

    direct_vm.clear_mocks()
    direct_vm.mock_web(
        r"raw\.example\.com/.*",
        {"status": 200, "body": "Reservation H-100 was cancelled."},
    )
    direct_vm.mock_llm(
        r".*",
        _llm_json(
            {
                "verdict": "NOT_SATISFIED",
                "reason": "The source states that the reservation was cancelled.",
                "evidence": "Reservation H-100 was cancelled.",
            }
        ),
    )
    assert direct_vm.run_validator() is False
