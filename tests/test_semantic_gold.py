from context_gateway.benchmark.semantic_gold import (
    SemanticCaseGold,
    SemanticGoldLabel,
    derive_admission,
)


def test_semantic_gold_taxonomy_and_admission():
    label = SemanticGoldLabel(
        evidence_key="x",
        task_fit="contextual",
        worthiness_role="contradiction",
        temporal_state="obsolete",
        admission="reject",
        sufficiency_role="not_needed",
        conflict_group="g",
    )
    label.validate()
    assert derive_admission(
        task_fit="contextual",
        worthiness_role="contradiction",
        temporal_state="unknown",
        query_mode="current_goal_with_conflict_awareness",
    ) == "admit_conflict"
    assert derive_admission(
        task_fit="contextual",
        worthiness_role="contradiction",
        temporal_state="obsolete",
        query_mode="latest_current_decision",
    ) == "reject"


def test_case_gold_validation():
    case = SemanticCaseGold(
        case_id="C1",
        query_mode="current_fact",
        labels=(
            SemanticGoldLabel(
                evidence_key="g",
                task_fit="direct",
                worthiness_role="direct_support",
                temporal_state="current",
                admission="admit",
                sufficiency_role="required",
            ),
        ),
        minimal_sufficient_set=("g",),
        conflict_complete_set=("g",),
        audit_rationale="single fact",
    )
    case.validate()
