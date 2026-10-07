import json

from benchmarks.context_bundle_lanes_v0_1 import (
    ContextBundleValidationError,
    deserialize_context_bundle,
)
from benchmarks.production_shaped_e2e_attack_v0_1 import (
    _case_xp02,
    _selection_xp02,
    _semantic_xp02,
    _case_xp04,
    _selection_xp04,
    _semantic_xp04,
    _production_shaped_case,
)


def _expect_reject(payload, mutate):
    tampered = json.loads(payload)
    mutate(tampered)
    try:
        deserialize_context_bundle(tampered)
    except ContextBundleValidationError:
        return
    raise AssertionError("tampered ContextBundle was accepted")


def test_xp04_roundtrip_preserves_lane_contract():
    _, view = _production_shaped_case(
        _case_xp04(),
        _semantic_xp04(),
        _selection_xp04(),
    )
    assert view["answer_keys"] == ["xp04.gold"]
    assert view["control_keys"] == ["xp04.dist"]


def test_relation_retarget_to_answer_support_fails_closed():
    materialized, _ = _production_shaped_case(
        _case_xp02(),
        _semantic_xp02(),
        _selection_xp02(),
    )

    def mutate(payload):
        relation = payload["bundle"]["epistemic_relations"][-1]
        relation["to"] = "xp02.claude"

    _expect_reject(materialized["serialized_context_bundle"], mutate)


def test_relation_deletion_from_boundary_bundle_fails_closed():
    materialized, _ = _production_shaped_case(
        _case_xp04(),
        _semantic_xp04(),
        _selection_xp04(),
    )

    def mutate(payload):
        payload["bundle"]["epistemic_relations"] = []

    _expect_reject(materialized["serialized_context_bundle"], mutate)
