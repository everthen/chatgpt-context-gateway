import json
from pathlib import Path

from benchmarks.selection_context_pipeline_v0_1 import (
    SelectionContextMaterializationError,
    materialize_selection_assessment,
)


ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads(
    (Path("/tmp/ucg_answer_quality_input_v0.1.json").read_text())
    if Path("/tmp/ucg_answer_quality_input_v0.1.json").exists()
    else "{}"
)


def _case(case_id):
    return CASES["cases"][case_id]


def test_real_shape_xp02_materializes_answer_contrast():
    case = _case("XP-02")
    semantic = {
        "assessments": [
            {
                "candidate_id": "C1",
                "worthiness_role": "direct_support",
                "claim_ids": ["claim-1"],
            },
            {
                "candidate_id": "C2",
                "worthiness_role": "direct_support",
                "claim_ids": ["claim-2"],
            },
            {
                "candidate_id": "C3",
                "worthiness_role": "contradiction",
                "claim_ids": ["claim-3"],
            },
        ]
    }
    selection = {
        "selected_candidate_ids": ["C1", "C2", "C3"],
        "relations": [
            {
                "source": "C1",
                "target": "C3",
                "type": "required_conflict",
                "when_selected": True,
            }
        ],
        "coverage_groups": [],
        "excluded_candidate_ids": [],
        "confidence": 0.9,
    }

    bundle = materialize_selection_assessment(case, semantic, selection)
    assert [x["key"] for x in bundle["bundle"]["answer_context"]] == [
        "xp02.openai",
        "xp02.claude",
    ]
    assert [x["key"] for x in bundle["bundle"]["control_context"]] == ["xp02.dist"]


def test_xp04_boundary_relation_forces_control_lane():
    case = _case("XP-04")
    semantic = {
        "assessments": [
            {
                "candidate_id": "C1",
                "worthiness_role": "direct_support",
                "claim_ids": ["claim-1"],
            },
            {
                "candidate_id": "C2",
                "worthiness_role": "direct_support",
                "claim_ids": ["claim-2"],
            },
        ]
    }
    selection = {
        "selected_candidate_ids": ["C1", "C2"],
        "relations": [
            {
                "source": "C1",
                "target": "C2",
                "type": "required_boundary_contrast",
                "when_selected": True,
            }
        ],
        "coverage_groups": [],
        "excluded_candidate_ids": [],
        "confidence": 0.9,
    }

    bundle = materialize_selection_assessment(case, semantic, selection)
    assert [x["key"] for x in bundle["bundle"]["answer_context"]] == ["xp04.gold"]
    assert [x["key"] for x in bundle["bundle"]["control_context"]] == ["xp04.dist"]


def test_missing_relation_target_fails_closed():
    case = _case("XP-04")
    semantic = {
        "assessments": [
            {"candidate_id": "C1", "worthiness_role": "direct_support"},
            {"candidate_id": "C2", "worthiness_role": "direct_support"},
        ]
    }
    selection = {
        "selected_candidate_ids": ["C1"],
        "relations": [
            {
                "source": "C1",
                "target": "C2",
                "type": "required_boundary_contrast",
                "when_selected": True,
            }
        ],
        "excluded_candidate_ids": ["C2"],
        "confidence": 0.9,
    }

    try:
        materialize_selection_assessment(case, semantic, selection)
    except (SelectionContextMaterializationError, ValueError):
        pass
    else:
        raise AssertionError("required relation target must fail closed")
