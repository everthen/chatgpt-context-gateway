import json
from pathlib import Path

from benchmarks.selection_context_pipeline_v0_1 import (
    SelectionContextMaterializationError,
    materialize_selection_assessment,
)


def _case(case_id):
    if case_id == "XP-02":
        return {
            "case_id": "XP-02",
            "provenance_map": {
                "xp02.openai": {
                    "provider": "openai",
                    "account_id": "main",
                    "conversation_id": "xp02-a",
                    "message_id": "m-openai",
                },
                "xp02.claude": {
                    "provider": "anthropic",
                    "account_id": "main",
                    "conversation_id": "xp02-b",
                    "message_id": "m-claude",
                },
                "xp02.dist": {
                    "provider": "openai",
                    "account_id": "secondary",
                    "conversation_id": "xp02-c",
                    "message_id": "m-dist",
                },
            },
            "corpus": {
                "conversations": [
                    {
                        "provider": "openai",
                        "account_id": "main",
                        "conversation_id": "xp02-a",
                        "messages": [
                            {
                                "evidence_key": "xp02.openai",
                                "message_id": "m-openai",
                                "text": "UCG should act as a provider-neutral context layer for OpenAI and other models.",
                            }
                        ],
                    },
                    {
                        "provider": "anthropic",
                        "account_id": "main",
                        "conversation_id": "xp02-b",
                        "messages": [
                            {
                                "evidence_key": "xp02.claude",
                                "message_id": "m-claude",
                                "text": "The same context should be portable into an Anthropic session without changing the source evidence.",
                            }
                        ],
                    },
                    {
                        "provider": "openai",
                        "account_id": "secondary",
                        "conversation_id": "xp02-c",
                        "messages": [
                            {
                                "evidence_key": "xp02.dist",
                                "message_id": "m-dist",
                                "text": "This account contains a separate implementation optimized only for one OpenAI workflow.",
                            }
                        ],
                    },
                ]
            },
        }

    if case_id == "XP-04":
        return {
            "case_id": "XP-04",
            "provenance_map": {
                "xp04.gold": {
                    "provider": "openai",
                    "account_id": "main",
                    "conversation_id": "xp04-a",
                    "message_id": "m-gold",
                },
                "xp04.dist": {
                    "provider": "openai",
                    "account_id": "secondary",
                    "conversation_id": "xp04-b",
                    "message_id": "m-dist",
                },
            },
            "corpus": {
                "conversations": [
                    {
                        "provider": "openai",
                        "account_id": "main",
                        "conversation_id": "xp04-a",
                        "messages": [
                            {
                                "evidence_key": "xp04.gold",
                                "message_id": "m-gold",
                                "text": "Evidence from the main account must remain isolated from another account.",
                            }
                        ],
                    },
                    {
                        "provider": "openai",
                        "account_id": "secondary",
                        "conversation_id": "xp04-b",
                        "messages": [
                            {
                                "evidence_key": "xp04.dist",
                                "message_id": "m-dist",
                                "text": "This secondary account has similarly worded evidence, but it is not valid for the main account.",
                            }
                        ],
                    },
                ]
            },
        }

    raise AssertionError(case_id)


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
        "xp02.dist",
    ]
    assert bundle["bundle"]["control_context"] == []
    assert bundle["bundle"]["answer_context"][2]["lane"] == "answer_contrast"


def test_complementary_relation_preserves_answer_support():
    case = _case("XP-02")
    semantic = {
        "assessments": [
            {"candidate_id": "C1", "worthiness_role": "direct_support"},
            {"candidate_id": "C2", "worthiness_role": "direct_support"},
            {"candidate_id": "C3", "worthiness_role": "contradiction"},
        ]
    }
    selection = {
        "selected_candidate_ids": ["C1", "C2", "C3"],
        "relations": [{"source": "C1", "target": "C2", "type": "complementary", "when_selected": True}],
        "coverage_groups": [],
        "excluded_candidate_ids": [],
        "confidence": 0.9,
    }

    bundle = materialize_selection_assessment(case, semantic, selection)
    assert [x["key"] for x in bundle["bundle"]["answer_context"][:2]] == [
        "xp02.openai", "xp02.claude"
    ]


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
