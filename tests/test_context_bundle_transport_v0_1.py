import json

from benchmarks.context_bundle_lanes_v0_1 import (
    ContextBundleValidationError,
    deserialize_context_bundle,
    serialize_context_bundle,
)
from benchmarks.production_shaped_e2e_attack_v0_1 import (
    _case_xp04,
    _production_shaped_case,
    _selection_xp04,
    _semantic_xp04,
)


def test_transport_roundtrip_is_canonical_and_lane_preserving():
    materialized, _ = _production_shaped_case(
        _case_xp04(),
        _semantic_xp04(),
        _selection_xp04(),
    )
    wire = materialized["serialized_context_bundle"]
    restored = deserialize_context_bundle(wire)
    assert serialize_context_bundle(restored) == wire
    assert [item["key"] for item in restored.answer_context] == ["xp04.gold"]
    assert [item["key"] for item in restored.control_context] == ["xp04.dist"]


def test_schema_version_tamper_fails_closed():
    materialized, _ = _production_shaped_case(
        _case_xp04(),
        _semantic_xp04(),
        _selection_xp04(),
    )
    payload = json.loads(materialized["serialized_context_bundle"])
    payload["schema_version"] = "ucg-context-bundle.v999"
    try:
        deserialize_context_bundle(payload)
    except ContextBundleValidationError as exc:
        assert "schema version" in str(exc)
    else:
        raise AssertionError("schema-version tamper was accepted")


def test_missing_bundle_object_fails_closed():
    materialized, _ = _production_shaped_case(
        _case_xp04(),
        _semantic_xp04(),
        _selection_xp04(),
    )
    payload = json.loads(materialized["serialized_context_bundle"])
    del payload["bundle"]
    try:
        deserialize_context_bundle(payload)
    except ContextBundleValidationError as exc:
        assert "missing bundle object" in str(exc)
    else:
        raise AssertionError("missing bundle payload was accepted")
