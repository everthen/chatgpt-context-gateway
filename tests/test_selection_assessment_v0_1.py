from __future__ import annotations

import pytest

from benchmarks.selection_assessment_v0_1 import normalize_selection_assessment


IDS = {"C1", "C2", "C3"}


def test_normalizes_from_to_aliases():
    result = normalize_selection_assessment(
        {
            "selected_candidate_ids": ["C1", "C2"],
            "relations": [
                {
                    "from": "C1",
                    "to": "C2",
                    "type": "required_boundary_contrast",
                }
            ],
            "coverage_groups": ["account_isolation_boundary"],
            "excluded_candidate_ids": ["C3"],
            "confidence": 0.94,
        },
        IDS,
    )

    assert result["relations"] == [
        {
            "source": "C1",
            "target": "C2",
            "type": "required_boundary_contrast",
            "when_selected": True,
        }
    ]
    assert result["coverage_groups"][0]["group_id"] == "account_isolation_boundary"


def test_normalizes_from_id_relation_type_aliases():
    result = normalize_selection_assessment(
        {
            "selected_candidate_ids": ["C1", "C2"],
            "relations": [
                {
                    "from_id": "C1",
                    "to_id": "C2",
                    "relation_type": "required_contrast",
                }
            ],
            "excluded_candidate_ids": [],
            "confidence": 0.8,
        },
        IDS,
    )

    assert result["relations"][0]["source"] == "C1"
    assert result["relations"][0]["target"] == "C2"


def test_rejects_unknown_candidate_ids():
    with pytest.raises(ValueError, match="unknown candidate id"):
        normalize_selection_assessment(
            {
                "selected_candidate_ids": ["C99"],
                "relations": [],
                "excluded_candidate_ids": [],
                "confidence": 0.5,
            },
            IDS,
        )


def test_rejects_unknown_relation_type():
    with pytest.raises(ValueError, match="unknown relation type"):
        normalize_selection_assessment(
            {
                "selected_candidate_ids": ["C1", "C2"],
                "relations": [
                    {
                        "source": "C1",
                        "target": "C2",
                        "type": "arbitrary_relation",
                    }
                ],
                "excluded_candidate_ids": [],
                "confidence": 0.5,
            },
            IDS,
        )


def test_rejects_selected_and_excluded_overlap():
    with pytest.raises(ValueError, match="both selected and excluded"):
        normalize_selection_assessment(
            {
                "selected_candidate_ids": ["C1"],
                "relations": [],
                "excluded_candidate_ids": ["C1"],
                "confidence": 0.5,
            },
            IDS,
        )


def test_rejects_invalid_confidence():
    with pytest.raises(ValueError, match="between 0 and 1"):
        normalize_selection_assessment(
            {
                "selected_candidate_ids": ["C1"],
                "relations": [],
                "excluded_candidate_ids": [],
                "confidence": 1.5,
            },
            IDS,
        )

def test_normalizes_complementary_relation_aliases():
    from benchmarks.selection_assessment_v0_1 import normalize_selection_assessment

    result = normalize_selection_assessment(
        {
            "selected_candidate_ids": ["C1", "C2"],
            "relations": [
                {
                    "from": "C1",
                    "to": "C2",
                    "relation_type": "complementary",
                    "when_selected": True,
                }
            ],
            "excluded_candidate_ids": [],
            "confidence": 0.9,
        },
        {"C1", "C2"},
    )
    assert result["relations"] == [
        {
            "source": "C1",
            "target": "C2",
            "type": "required_complement",
            "when_selected": True,
        }
    ]

def test_missing_selected_candidate_ids_fails_closed():
    from benchmarks.selection_assessment_v0_1 import normalize_selection_assessment

    try:
        normalize_selection_assessment(
            {"selected_candidates": [{"candidate_id": "C1"}]},
            {"C1"},
        )
    except ValueError as exc:
        assert "selected_candidate_ids is required" in str(exc)
    else:
        raise AssertionError("non-canonical selection shape must fail closed")
