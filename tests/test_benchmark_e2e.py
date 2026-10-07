from pathlib import Path

from context_gateway.benchmark.e2e import (
    UnavailableAdapter,
    make_request,
    run_e2e_case,
)
from context_gateway.benchmark.schema import load_dataset


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "benchmarks" / "data" / "seed_v0.1.jsonl"


def test_e2e_request_prompt_is_shared_shape_and_hashed():
    case = load_dataset(DATASET)[0]
    request = make_request("oracle", case, [{"evidence_key": "x", "text": "fact"}])
    assert request.prompt_hash
    assert "QUERY:" in request.prompt
    assert "CONTEXT:" in request.prompt
    assert "fact" in request.prompt


def test_e2e_does_not_fake_missing_native_adapter():
    case = load_dataset(DATASET)[0]
    result = run_e2e_case(
        case,
        oracle_context=[{"evidence_key": "gold", "text": "fact"}],
        native_context=None,
        ucg_context=[{"evidence_key": "gold", "text": "fact"}],
        adapters={
            "oracle": UnavailableAdapter("oracle", "fixture only"),
            "ucg": UnavailableAdapter("ucg", "fixture only"),
        },
    )
    statuses = {item["arm"]: item["status"] for item in result["responses"]}
    assert statuses["native"] == "unavailable"
    assert statuses["oracle"] == "unavailable"
    assert statuses["ucg"] == "unavailable"
