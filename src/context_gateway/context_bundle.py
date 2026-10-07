from __future__ import annotations

from dataclasses import dataclass
import json
from collections.abc import Mapping
from typing import Any


ANSWER_LANES = {"answer_support", "answer_contrast"}
CONTROL_LANES = {
    "control_boundary",
    "control_conflict",
    "control_state",
    "control_rejection",
}
ALL_LANES = ANSWER_LANES | CONTROL_LANES
CONTEXT_BUNDLE_SCHEMA_VERSION = "ucg-context-bundle.v0.1"

_RELATION_TO_TARGET_LANE = {
    "required_contrast": "answer_contrast",
    "required_complement": "answer_support",
    "required_boundary_contrast": "control_boundary",
    "required_conflict": "control_conflict",
    "required_state_contrast": "control_state",
}

_ROLE_DEFAULT_LANE = {
    "supporting": "answer_support",
    "answer_support": "answer_support",
    "answer_contrast": "answer_contrast",
    "contrastive": "answer_contrast",
    "distractor": "control_rejection",
}


class ContextBundleValidationError(ValueError):
    """Raised when a lane-aware bundle violates a safety invariant."""


@dataclass(frozen=True)
class ContextBundle:
    answer_context: tuple[dict[str, Any], ...]
    control_context: tuple[dict[str, Any], ...]
    epistemic_relations: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "answer_context": list(self.answer_context),
            "control_context": list(self.control_context),
            "epistemic_relations": list(self.epistemic_relations),
        }


def _relations(item: dict[str, Any]) -> list[dict[str, Any]]:
    selection = item.get("selection") or {}
    value = selection.get("relations") or []
    return [rel for rel in value if isinstance(rel, dict)]


def _validate_explicit_lane(item: dict[str, Any], lane: str) -> None:
    role = str(item.get("role") or "").strip()
    if role == "supporting" and lane != "answer_support":
        raise ContextBundleValidationError(
            f"supporting evidence cannot be assigned to {lane}: {item.get('key')}"
        )
    if role == "distractor" and lane != "control_rejection":
        raise ContextBundleValidationError(
            f"distractor evidence cannot be assigned to {lane}: {item.get('key')}"
        )


def _infer_lane(
    item: dict[str, Any],
    *,
    incoming_relation_types: set[str],
) -> str:
    selection = item.get("selection") or {}
    explicit = selection.get("lane")
    if explicit is not None:
        lane = str(explicit)
        if lane not in ALL_LANES:
            raise ContextBundleValidationError(
                f"unknown lane for {item.get('key')}: {lane}"
            )
        _validate_explicit_lane(item, lane)
        return lane

    role = str(item.get("role") or "").strip()

    # A conflict can be answer-relevant (for example a rejected provider
    # alternative) or control-only. Let semantic role disambiguate it.
    if "required_conflict" in incoming_relation_types:
        if role in {"contrastive", "answer_contrast"}:
            return "answer_contrast"
        return "control_conflict"

    for relation_type in (
        "required_boundary_contrast",
        "required_state_contrast",
        "required_contrast",
        "required_complement",
    ):
        if relation_type in incoming_relation_types:
            return _RELATION_TO_TARGET_LANE[relation_type]
    if role in _ROLE_DEFAULT_LANE:
        return _ROLE_DEFAULT_LANE[role]

    raise ContextBundleValidationError(
        f"cannot infer lane for selected evidence: {item.get('key')}"
    )



def _relation_guidance(relation_type: str) -> str:
    return {
        "required_contrast": "treat the target as an explicit alternative or contrast, not positive support",
        "required_complement": "treat source and target as complementary positive support when both are selected",
        "required_boundary_contrast": "for the requested source scope, explicitly state that target evidence must not be merged into the source scope; answer from the source scope only",
        "required_conflict": "treat the target as a conflicting alternative; do not silently collapse the conflict",
        "required_state_contrast": "treat the target as a contrasting state and do not let it override the selected current state",
    }.get(relation_type, "")


def serialize_context_bundle(bundle: ContextBundle) -> str:
    """Serialize a validated ContextBundle without flattening its lanes."""
    validate_context_bundle(bundle)
    envelope = {
        "schema_version": CONTEXT_BUNDLE_SCHEMA_VERSION,
        "bundle": bundle.as_dict(),
    }
    return json.dumps(
        envelope,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def deserialize_context_bundle(payload: str | Mapping[str, Any]) -> ContextBundle:
    """Deserialize and validate a wire ContextBundle fail-closed."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ContextBundleValidationError("serialized ContextBundle is not valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise ContextBundleValidationError("serialized ContextBundle must be an object")
    if payload.get("schema_version") != CONTEXT_BUNDLE_SCHEMA_VERSION:
        raise ContextBundleValidationError("unsupported ContextBundle schema version")

    raw_bundle = payload.get("bundle")
    if not isinstance(raw_bundle, Mapping):
        raise ContextBundleValidationError("serialized ContextBundle missing bundle object")

    def _records(name: str) -> tuple[dict[str, Any], ...]:
        value = raw_bundle.get(name)
        if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
            raise ContextBundleValidationError(f"serialized {name} must be an array of objects")
        return tuple(dict(item) for item in value)

    relations = raw_bundle.get("epistemic_relations")
    if not isinstance(relations, list) or not all(isinstance(item, Mapping) for item in relations):
        raise ContextBundleValidationError("serialized epistemic_relations must be an array of objects")

    bundle = ContextBundle(
        answer_context=_records("answer_context"),
        control_context=_records("control_context"),
        epistemic_relations=tuple(dict(item) for item in relations),
    )
    validate_context_bundle(bundle)
    return bundle


def answer_consumer_view(bundle: ContextBundle) -> dict[str, Any]:
    """Return only governed material exposed to the answer generator."""
    validate_context_bundle(bundle)
    return {
        "answer_context": [dict(item) for item in bundle.answer_context],
        "epistemic_relations": [dict(item) for item in bundle.epistemic_relations],
    }

def build_context_bundle(
    candidates: list[dict[str, Any]],
    selected_keys: list[str] | tuple[str, ...] | set[str],
) -> ContextBundle:
    """Materialize selected evidence into governed answer/control lanes.

    Boundary/state/rejection relations default to control lanes so retained
    evidence cannot silently become positive answer authority.
    """

    by_key = {item["key"]: item for item in candidates}
    selected = [str(key) for key in selected_keys]

    unknown = [key for key in selected if key not in by_key]
    if unknown:
        raise ContextBundleValidationError(
            f"selected evidence is not present in candidates: {sorted(unknown)}"
        )

    incoming_relation_types: dict[str, set[str]] = {key: set() for key in selected}
    relations: list[dict[str, Any]] = []

    for source_key in selected:
        source = by_key[source_key]
        for rel in _relations(source):
            if rel.get("when_selected") is not True:
                continue
            relation_type = str(rel.get("type") or "")
            target = rel.get("target")
            if relation_type not in _RELATION_TO_TARGET_LANE:
                continue
            if target not in selected:
                raise ContextBundleValidationError(
                    f"required relation target {target!r} missing from selected bundle"
                )
            incoming_relation_types[str(target)].add(relation_type)
            relation_record = {
                "from": source_key,
                "to": str(target),
                "relation_type": relation_type,
                "answer_guidance": _relation_guidance(relation_type),
            }
            relations.append(relation_record)

    answer_context: list[dict[str, Any]] = []
    control_context: list[dict[str, Any]] = []

    for key in selected:
        item = by_key[key]
        lane = _infer_lane(
            item,
            incoming_relation_types=incoming_relation_types[key],
        )
        answer_visible = lane in ANSWER_LANES
        citation_eligible = answer_visible

        record = {
            "key": key,
            "text": item.get("text") or item.get("evidence"),
            "provenance": item.get("provenance") or {},
            "role": item.get("role"),
            "lane": lane,
            "answer_visible": answer_visible,
            "citation_eligible": citation_eligible,
        }

        if answer_visible:
            answer_context.append(record)
        else:
            control_context.append(record)

    bundle = ContextBundle(
        answer_context=tuple(answer_context),
        control_context=tuple(control_context),
        epistemic_relations=tuple(relations),
    )
    validate_context_bundle(bundle)
    return bundle


def validate_context_bundle(bundle: ContextBundle) -> None:
    """Fail closed if lane or citation invariants are violated."""

    answer_keys = {item["key"] for item in bundle.answer_context}
    control_keys = {item["key"] for item in bundle.control_context}

    overlap = answer_keys & control_keys
    if overlap:
        raise ContextBundleValidationError(
            f"evidence cannot inhabit both lanes: {sorted(overlap)}"
        )

    for item in bundle.answer_context:
        if item.get("answer_visible") is not True:
            raise ContextBundleValidationError(
                f"answer_context item is not answer-visible: {item.get('key')}"
            )
        if item.get("citation_eligible") is not True:
            raise ContextBundleValidationError(
                f"answer_context item is not citation-eligible: {item.get('key')}"
            )
        if item.get("lane") not in ANSWER_LANES:
            raise ContextBundleValidationError(
                f"non-answer lane leaked into answer_context: {item.get('key')}"
            )

    for item in bundle.control_context:
        if item.get("answer_visible") is not False:
            raise ContextBundleValidationError(
                f"control evidence became answer-visible: {item.get('key')}"
            )
        if item.get("citation_eligible") is not False:
            raise ContextBundleValidationError(
                f"control evidence became citation-eligible: {item.get('key')}"
            )
        if item.get("lane") not in CONTROL_LANES:
            raise ContextBundleValidationError(
                f"non-control lane leaked into control_context: {item.get('key')}"
            )

    all_items = {
        item["key"]: item
        for item in list(bundle.answer_context) + list(bundle.control_context)
    }
    all_keys = set(all_items)
    incoming_relations: dict[str, set[str]] = {key: set() for key in all_keys}
    for rel in bundle.epistemic_relations:
        source = rel.get("from")
        target = rel.get("to")
        relation_type = rel.get("relation_type")
        if source not in all_keys or target not in all_keys:
            raise ContextBundleValidationError(
                "epistemic relation references evidence outside the bundle"
            )
        if source == target:
            raise ContextBundleValidationError("epistemic relation cannot target itself")
        if relation_type not in _RELATION_TO_TARGET_LANE:
            raise ContextBundleValidationError(f"unknown epistemic relation type: {relation_type}")
        expected_guidance = _relation_guidance(relation_type)
        if rel.get("answer_guidance") != expected_guidance:
            raise ContextBundleValidationError(
                "epistemic relation guidance does not match relation type"
            )
        incoming_relations[target].add(relation_type)

        target_item = all_items[target]
        target_role = str(target_item.get("role") or "").strip()
        expected_lane = _RELATION_TO_TARGET_LANE[relation_type]
        if relation_type == "required_conflict" and target_role in {"contrastive", "answer_contrast"}:
            expected_lane = "answer_contrast"
        if target_item.get("lane") != expected_lane:
            raise ContextBundleValidationError(
                f"epistemic relation target lane mismatch: {target} expected {expected_lane}"
            )

    for item in bundle.control_context:
        lane = item.get("lane")
        if lane in {"control_boundary", "control_conflict", "control_state"}:
            required_type = {
                "control_boundary": "required_boundary_contrast",
                "control_conflict": "required_conflict",
                "control_state": "required_state_contrast",
            }[lane]
            if required_type not in incoming_relations[item["key"]]:
                raise ContextBundleValidationError(
                    f"control lane lacks required epistemic relation: {item.get('key')}"
                )


def build_production_context_bundle(
    selection: Mapping[str, Any],
    evidence: list[Mapping[str, Any]],
) -> ContextBundle:
    """Materialize the production deterministic selector into the governed lanes.

    The current production selector promotes only its selected evidence. It does
    not invent epistemic relations that the selector did not establish.
    """
    decision = str(selection.get("decision") or "")
    selected_ids = [str(x) for x in (selection.get("selected_evidence_ids") or [])]
    if decision != "selected":
        selected_ids = []

    by_id = {
        str(item.get("evidence_id")): item
        for item in evidence
        if item.get("evidence_id")
    }
    missing = [item_id for item_id in selected_ids if item_id not in by_id]
    if missing:
        raise ContextBundleValidationError(
            f"selected production evidence is missing from materialization input: {sorted(missing)}"
        )

    answer_context: list[dict[str, Any]] = []
    for evidence_id in selected_ids:
        item = by_id[evidence_id]
        record = {
            "key": evidence_id,
            "text": item.get("excerpt") or item.get("content") or "",
            "provenance": {
                "provider": item.get("provider"),
                "account": item.get("account_id"),
                "conversation": item.get("conversation_uid"),
                "snapshot": item.get("snapshot_id"),
                "message": item.get("message_uid") or item.get("message_id"),
                "raw_path": item.get("raw_path"),
                "raw_hash": item.get("raw_hash"),
            },
            "role": "supporting",
            "lane": "answer_support",
            "answer_visible": True,
            "citation_eligible": True,
        }
        answer_context.append(record)

    bundle = ContextBundle(
        answer_context=tuple(answer_context),
        control_context=(),
        epistemic_relations=(),
    )
    validate_context_bundle(bundle)
    return bundle
