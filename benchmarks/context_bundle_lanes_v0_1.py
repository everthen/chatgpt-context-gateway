from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ANSWER_LANES = {"answer_support", "answer_contrast"}
CONTROL_LANES = {
    "control_boundary",
    "control_conflict",
    "control_state",
    "control_rejection",
}
ALL_LANES = ANSWER_LANES | CONTROL_LANES

_RELATION_TO_TARGET_LANE = {
    "required_contrast": "answer_contrast",
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
    ):
        if relation_type in incoming_relation_types:
            return _RELATION_TO_TARGET_LANE[relation_type]
    if role in _ROLE_DEFAULT_LANE:
        return _ROLE_DEFAULT_LANE[role]

    raise ContextBundleValidationError(
        f"cannot infer lane for selected evidence: {item.get('key')}"
    )


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
            relations.append(
                {
                    "from": source_key,
                    "to": str(target),
                    "relation_type": relation_type,
                }
            )

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

    all_keys = answer_keys | control_keys
    for rel in bundle.epistemic_relations:
        if rel.get("from") not in all_keys or rel.get("to") not in all_keys:
            raise ContextBundleValidationError(
                "epistemic relation references evidence outside the bundle"
            )
