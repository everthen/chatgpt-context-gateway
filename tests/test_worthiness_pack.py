from context_gateway.benchmark.semantic_assessor import blind_candidates
from context_gateway.benchmark.worthiness_pack import (
    build_blind_case,
    build_gold_sidecar,
)
from context_gateway.benchmark.schema import BenchmarkCase, EvidenceRef


def make_case():
    return BenchmarkCase(
        case_id="W-01",
        task_family="long_session",
        corpus={},
        query="production region",
        gold_evidence=(EvidenceRef("gold", "chatgpt", "main", "c1", "m1"),),
        supporting_evidence=(),
        distractors=(EvidenceRef("dist", "chatgpt", "main", "c2", "m2"),),
        temporal_state={},
        expected_claims=("Production region is Singapore.",),
        provenance_map={
            "gold": {},
            "dist": {},
        },
        difficulty="easy",
        retrieval_queries=("production region",),
    )


def candidates():
    return [
        {
            "evidence_key": "gold",
            "excerpt": "Production region is Singapore.",
            "provider": "chatgpt",
            "account_id": "main",
            "id": "c1",
            "message_id": "m1",
        },
        {
            "evidence_key": "dist",
            "excerpt": "Frankfurt was considered earlier.",
            "provider": "chatgpt",
            "account_id": "main",
            "id": "c2",
            "message_id": "m2",
        },
    ]


def test_blind_pack_contains_no_gold_keys():
    packed = build_blind_case(make_case(), candidates())
    serialized = str(packed)
    assert "gold" not in serialized
    assert "dist" not in serialized
    assert packed["candidates"][0]["candidate_id"] == "C1"


def test_gold_sidecar_keeps_truth_separate():
    sidecar = build_gold_sidecar(make_case(), candidates())
    assert sidecar["labels"][0]["evidence_key"] == "gold"
    assert sidecar["labels"][0]["task_fit"] == "direct"
    assert sidecar["labels"][1]["task_fit"] == "none"
