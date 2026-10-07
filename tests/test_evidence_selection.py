from context_gateway.benchmark.selection import (
    EvidenceAdmissionConfig,
    admit_rrf_candidates,
)


def candidate(key, score, *supports):
    return {
        "evidence_id": key,
        "rrf_score": score,
        "query_support": [
            {"query_index": query_index, "query": f"q{query_index}", "rank": rank}
            for query_index, rank in supports
        ],
    }


def test_admission_keeps_query_coverage_but_caps_context_size():
    candidates = [
        candidate("a", 0.030, (0, 1)),
        candidate("b", 0.028, (0, 2)),
        candidate("c", 0.029, (1, 1)),
        candidate("d", 0.027, (1, 2)),
        candidate("e", 0.026, (2, 1)),
    ]

    selected = admit_rrf_candidates(
        candidates,
        config=EvidenceAdmissionConfig(per_query_cap=2, final_limit=4),
    )

    assert len(selected) == 4
    assert {0, 1, 2}.issubset(
        {
            support["query_index"]
            for item in selected
            for support in item["query_support"]
            if support["rank"] <= 2
        }
    )


def test_admission_drops_candidates_only_found_below_cap():
    candidates = [
        candidate("top", 0.030, (0, 1)),
        candidate("deep", 0.029, (0, 4)),
        candidate("other", 0.028, (1, 1)),
    ]

    selected = admit_rrf_candidates(
        candidates,
        config=EvidenceAdmissionConfig(per_query_cap=2, final_limit=4),
    )

    assert [item["evidence_id"] for item in selected] == ["top", "other"]


def test_admission_is_not_a_truth_oracle():
    candidates = [candidate("distractor-but-top", 0.030, (0, 1))]
    selected = admit_rrf_candidates(candidates)

    assert selected[0]["evidence_id"] == "distractor-but-top"
