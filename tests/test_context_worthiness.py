import pytest

from context_gateway.benchmark.selection import (
    ContextWorthinessPolicy,
    evaluate_context_worthiness,
    select_context_worthy,
)


def candidate(
    key,
    *,
    rank=1,
    task_fit="direct",
    role="direct_support",
    provenance_complete=True,
    temporal_state="current",
    conflict_status="none",
    redundancy_group=None,
    claim_ids=(),
):
    item = {
        "evidence_id": key,
        "query_support": [{"query_index": 0, "query": "q", "rank": rank}],
        "task_fit": task_fit,
        "worthiness_role": role,
        "provenance_complete": provenance_complete,
        "temporal_state": temporal_state,
        "claim_ids": list(claim_ids),
    }
    if redundancy_group is not None:
        item["redundancy_group"] = redundancy_group
    if conflict_status != "none":
        item["admission_annotation"] = {"conflict_status": conflict_status}
    return item


def test_lexical_hit_without_claim_value_is_rejected():
    decision = evaluate_context_worthiness(
        candidate("lexical", role="none", task_fit="none")
    )
    assert decision["decision"] == "reject"


def test_direct_support_with_complete_provenance_is_admitted():
    decision = evaluate_context_worthiness(candidate("gold"))
    assert decision["decision"] == "admit"
    assert "supports_claim" in decision["reasons"]


def test_incomplete_provenance_is_blocked():
    decision = evaluate_context_worthiness(
        candidate("broken", provenance_complete=False)
    )
    assert decision["decision"] == "reject"
    assert "incomplete_provenance" in decision["reasons"]


def test_obsolete_evidence_is_rejected_for_current_task():
    decision = evaluate_context_worthiness(
        candidate("old", temporal_state="obsolete")
    )
    assert decision["decision"] == "reject"


def test_unresolved_contradiction_is_worth_sending():
    decision = evaluate_context_worthiness(
        candidate(
            "conflict",
            role="contradiction",
            conflict_status="unresolved",
        )
    )
    assert decision["decision"] == "admit_conflict"


def test_redundant_same_claim_is_collapsed():
    selected = select_context_worthy(
        [
            candidate("a", rank=1, redundancy_group="r1", claim_ids=("claim-1",)),
            candidate("b", rank=2, redundancy_group="r1", claim_ids=("claim-1",)),
        ],
        policy=ContextWorthinessPolicy(final_limit=4),
    )
    assert [item["evidence_id"] for item in selected] == ["a"]


def test_complementary_evidence_survives_deduplication():
    selected = select_context_worthy(
        [
            candidate("a", rank=1, redundancy_group="r1", claim_ids=("claim-1",)),
            candidate("b", rank=2, redundancy_group="r1", claim_ids=("claim-2",)),
        ],
        policy=ContextWorthinessPolicy(final_limit=4),
    )
    assert [item["evidence_id"] for item in selected] == ["a", "b"]


def test_conflicting_current_evidence_is_not_silently_dropped():
    selected = select_context_worthy(
        [
            candidate(
                "a",
                rank=1,
                role="contradiction",
                conflict_status="unresolved",
                claim_ids=("claim-1",),
            ),
            candidate(
                "b",
                rank=2,
                role="contradiction",
                conflict_status="unresolved",
                claim_ids=("claim-1",),
            ),
        ],
        policy=ContextWorthinessPolicy(final_limit=4),
    )
    assert [item["evidence_id"] for item in selected] == ["a", "b"]


@pytest.mark.parametrize(
    "role,task_fit",
    [
        ("supporting", "supporting"),
        ("contextual", "contextual"),
    ],
)
def test_non_direct_but_useful_evidence_can_be_admitted(role, task_fit):
    decision = evaluate_context_worthiness(
        candidate("support", role=role, task_fit=task_fit)
    )
    assert decision["decision"] == "admit"
