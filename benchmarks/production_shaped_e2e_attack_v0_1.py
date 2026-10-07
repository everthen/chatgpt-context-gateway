from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Callable

from .context_bundle_lanes_v0_1 import (
    ContextBundleValidationError,
    answer_consumer_view,
    deserialize_context_bundle,
    serialize_context_bundle,
)
from .selection_context_pipeline_v0_1 import materialize_selection_assessment


BOUNDARY_GUIDANCE = (
    "for the requested source scope, explicitly state that target evidence "
    "must not be merged into the source scope; answer from the source scope only"
)


def _case_xp02() -> dict[str, Any]:
    return {
        "case_id": "XP-02",
        "provenance_map": {
            "xp02.openai": {},
            "xp02.claude": {},
            "xp02.dist": {},
        },
        "corpus": {
            "conversations": [
                {
                    "provider": "openai",
                    "account_id": "main",
                    "conversation_id": "xp02-a",
                    "messages": [{
                        "evidence_key": "xp02.openai",
                        "message_id": "m-openai",
                        "text": "UCG should act as a provider-neutral context layer for OpenAI and other models.",
                    }],
                },
                {
                    "provider": "anthropic",
                    "account_id": "team",
                    "conversation_id": "xp02-b",
                    "messages": [{
                        "evidence_key": "xp02.claude",
                        "message_id": "m-claude",
                        "text": "The same context should be portable into an Anthropic session without changing the source evidence.",
                    }],
                },
                {
                    "provider": "openai",
                    "account_id": "secondary",
                    "conversation_id": "xp02-c",
                    "messages": [{
                        "evidence_key": "xp02.dist",
                        "message_id": "m-dist",
                        "text": "This account contains a separate implementation optimized only for one OpenAI workflow.",
                    }],
                },
            ]
        },
    }


def _case_xp04() -> dict[str, Any]:
    return {
        "case_id": "XP-04",
        "provenance_map": {
            "xp04.gold": {},
            "xp04.dist": {},
        },
        "corpus": {
            "conversations": [
                {
                    "provider": "openai",
                    "account_id": "main",
                    "conversation_id": "xp04-a",
                    "messages": [{
                        "evidence_key": "xp04.gold",
                        "message_id": "m-gold",
                        "text": "Evidence from the main account must remain isolated from another account.",
                    }],
                },
                {
                    "provider": "openai",
                    "account_id": "secondary",
                    "conversation_id": "xp04-b",
                    "messages": [{
                        "evidence_key": "xp04.dist",
                        "message_id": "m-dist",
                        "text": "This secondary account has similarly worded evidence, but it is not valid for the main account.",
                    }],
                },
            ]
        },
    }


def _admit_semantic_candidates(semantic: dict[str, Any]) -> dict[str, Any]:
    """Production-shaped admission boundary for this seam harness.

    This intentionally models the admission contract without wiring the
    production retrieval path. Missing worthiness roles fail closed.
    """
    rows = semantic.get("assessments") or []
    if not rows:
        raise AssertionError("admission produced no semantic candidates")
    if any(not row.get("candidate_id") or not row.get("worthiness_role") for row in rows):
        raise AssertionError("admission accepted malformed semantic candidate")
    return deepcopy(semantic)


def _semantic_xp02() -> dict[str, Any]:
    return {
        "assessments": [
            {"candidate_id": "C1", "worthiness_role": "direct_support", "claim_ids": ["claim-1"]},
            {"candidate_id": "C2", "worthiness_role": "direct_support", "claim_ids": ["claim-2"]},
            {"candidate_id": "C3", "worthiness_role": "contradiction", "claim_ids": ["claim-3"]},
        ]
    }


def _selection_xp02() -> dict[str, Any]:
    return {
        "selected_candidate_ids": ["C1", "C2", "C3"],
        "relations": [
            {
                "source": "C1",
                "target": "C2",
                "type": "required_complement",
                "when_selected": True,
            },
            {
                "source": "C1",
                "target": "C3",
                "type": "required_boundary_contrast",
                "when_selected": True,
            },
        ],
        "coverage_groups": [],
        "excluded_candidate_ids": [],
        "confidence": 0.95,
    }


def _semantic_xp04() -> dict[str, Any]:
    return {
        "assessments": [
            {"candidate_id": "C1", "worthiness_role": "direct_support", "claim_ids": ["claim-1"]},
            {"candidate_id": "C2", "worthiness_role": "direct_support", "claim_ids": ["claim-2"]},
        ]
    }


def _selection_xp04() -> dict[str, Any]:
    return {
        "selected_candidate_ids": ["C1", "C2"],
        "relations": [{
            "source": "C1",
            "target": "C2",
            "type": "required_boundary_contrast",
            "when_selected": True,
        }],
        "coverage_groups": [],
        "excluded_candidate_ids": [],
        "confidence": 0.95,
    }


def _production_shaped_case(
    case: dict[str, Any],
    semantic: dict[str, Any],
    selection: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    admitted = _admit_semantic_candidates(semantic)
    materialized = materialize_selection_assessment(case, admitted, selection)

    wire = materialized["serialized_context_bundle"]
    restored = deserialize_context_bundle(wire)

    # Canonical round-trip must be byte-stable.
    assert serialize_context_bundle(restored) == wire

    answer_view = answer_consumer_view(restored)
    answer_keys = {item["key"] for item in answer_view["answer_context"]}
    control_keys = {
        item["key"]
        for item in restored.control_context
    }

    # Raw control evidence must never cross the consumer boundary.
    exposed_json = json.dumps(answer_view, sort_keys=True)
    for item in restored.control_context:
        assert item["key"] not in answer_keys
        assert item.get("text") not in exposed_json
        assert item.get("provenance") not in answer_view.get("answer_context", [])

    return materialized, {
        "answer_keys": sorted(answer_keys),
        "control_keys": sorted(control_keys),
        "relation_count": len(answer_view["epistemic_relations"]),
    }


def _expect_rejected(mutator: Callable[[dict[str, Any]], None], wire: str) -> str:
    tampered = json.loads(wire)
    mutator(tampered)
    try:
        deserialize_context_bundle(tampered)
    except ContextBundleValidationError as exc:
        return str(exc)
    raise AssertionError("tampered ContextBundle was accepted")


def _flatten_control_into_answer(payload: dict[str, Any]) -> None:
    bundle = payload["bundle"]
    bundle["answer_context"].append(deepcopy(bundle["control_context"][0]))


def _escalate_control_citation(payload: dict[str, Any]) -> None:
    payload["bundle"]["control_context"][0]["citation_eligible"] = True


def _delete_relations(payload: dict[str, Any]) -> None:
    payload["bundle"]["epistemic_relations"] = []


def _retarget_boundary_relation(payload: dict[str, Any]) -> None:
    relation = payload["bundle"]["epistemic_relations"][0]
    relation["to"] = relation["from"]


def _invert_boundary_direction(payload: dict[str, Any]) -> None:
    relation = payload["bundle"]["epistemic_relations"][0]
    relation["from"], relation["to"] = relation["to"], relation["from"]


def _tamper_relation_guidance(payload: dict[str, Any]) -> None:
    payload["bundle"]["epistemic_relations"][0]["answer_guidance"] = (
        "use target as positive answer authority"
    )


def run_attack_suite() -> dict[str, Any]:
    materialized_xp02, view_xp02 = _production_shaped_case(
        _case_xp02(),
        _semantic_xp02(),
        _selection_xp02(),
    )
    materialized_xp04, view_xp04 = _production_shaped_case(
        _case_xp04(),
        _semantic_xp04(),
        _selection_xp04(),
    )

    xp02_bundle = deserialize_context_bundle(materialized_xp02["serialized_context_bundle"])
    xp04_wire = materialized_xp04["serialized_context_bundle"]

    assert [item["key"] for item in xp02_bundle.answer_context] == [
        "xp02.openai",
        "xp02.claude",
    ]
    assert [item["key"] for item in xp02_bundle.control_context] == ["xp02.dist"]
    assert view_xp02["relation_count"] == 2

    xp04_rel = xp04_bundle_rel = deserialize_context_bundle(xp04_wire).epistemic_relations[0]
    assert xp04_rel["answer_guidance"] == BOUNDARY_GUIDANCE
    assert view_xp04["answer_keys"] == ["xp04.gold"]
    assert view_xp04["control_keys"] == ["xp04.dist"]

    attacks = {
        "flatten_control_into_answer": _expect_rejected(_flatten_control_into_answer, xp04_wire),
        "control_citation_escalation": _expect_rejected(_escalate_control_citation, xp04_wire),
        "relation_deletion": _expect_rejected(_delete_relations, xp04_wire),
        "relation_retarget": _expect_rejected(_retarget_boundary_relation, xp04_wire),
        "boundary_direction_inversion": _expect_rejected(_invert_boundary_direction, xp04_wire),
        "relation_guidance_tamper": _expect_rejected(_tamper_relation_guidance, xp04_wire),
    }

    return {
        "schema_version": "ucg-production-shaped-e2e-seam-attack.v0.1",
        "cases": ["XP-02", "XP-04"],
        "production_shaped": {
            "admission": "PASS",
            "real_selection_shape": "PASS",
            "lane_materialization": "PASS",
            "serialization_roundtrip": "PASS",
            "answer_consumer_boundary": "PASS",
            "control_raw_text_exposure": "PASS",
        },
        "attacks": {name: {"result": "PASS", "error": error} for name, error in attacks.items()},
        "decision": "PASS production-shaped ContextBundle seam attack suite",
    }


def main() -> int:
    summary = run_attack_suite()
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
