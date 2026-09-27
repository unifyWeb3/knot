"""Direct-mode tests for the bounded evidence judgment seam."""

import json

CONTRACT = "contracts/knot.py"
URL_MODE = 2
PREFIX = "https://raw.example.com/unifyWeb3/knot/commit/fixtures/"


def _llm_text(payload: dict) -> str:
    """Encode an LLM decision the way a chatty model reply looks.

    The contract asks for ``response_format="text"`` and extracts the JSON
    object itself, so the response is prose plus JSON. gltest's mock layer
    auto-parses *bare* JSON strings into dicts (which the text decoder then
    rejects), so the prefix is what keeps the mock response as text.
    """
    return "Decision:\n" + json.dumps(payload)


def test_evidence_judgment_rederives_and_agrees(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    direct_vm.check_pickling = True
    direct_vm.mock_web(
        r"raw\.example\.com/.*",
        {"status": 200, "body": "Reservation H-100 is confirmed and active."},
    )
    direct_vm.mock_llm(
        r".*",
        _llm_text(
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
        _llm_text(
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
        _llm_text(
            {
                "verdict": "NOT_SATISFIED",
                "reason": "The source states that the reservation was cancelled.",
                "evidence": "Reservation H-100 was cancelled.",
            }
        ),
    )
    assert direct_vm.run_validator() is False
