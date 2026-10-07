from __future__ import annotations

from typing import Any


RELATION_TYPES = {
    "required_contrast",
    "required_complement",
    "required_boundary_contrast",
    "required_conflict",
    "required_state_contrast",
}

_RELATION_SOURCE_KEYS = ("source", "from", "from_id")
_RELATION_TARGET_KEYS = ("target", "to", "to_id")
_RELATION_TYPE_KEYS = ("type", "relation_type")

_RELATION_TYPE_ALIASES = {
    "complementary": "required_complement",
    "required_complement": "required_complement",
}


def _first(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def normalize_selection_assessment(
    raw: dict[str, Any],
    candidate_ids: set[str],
) -> dict[str, Any]:
    """Normalize tolerated LLM aliases into the canonical selection contract.

    The adapter is intentionally narrow: unknown candidate IDs and unknown
    relation types remain hard errors rather than being silently dropped.
    """

    if "selected_candidate_ids" not in raw or not isinstance(raw.get("selected_candidate_ids"), list):
        raise ValueError("selected_candidate_ids is required and must be an array")

    selected = list(dict.fromkeys(raw.get("selected_candidate_ids") or []))
    excluded = list(dict.fromkeys(raw.get("excluded_candidate_ids") or []))

    for value in selected + excluded:
        if value not in candidate_ids:
            raise ValueError(f"unknown candidate id: {value}")

    overlap = set(selected) & set(excluded)
    if overlap:
        raise ValueError(f"candidate both selected and excluded: {sorted(overlap)}")

    relations = []
    for relation in raw.get("relations") or []:
        if not isinstance(relation, dict):
            raise ValueError("relation must be an object")

        source = _first(relation, _RELATION_SOURCE_KEYS)
        target = _first(relation, _RELATION_TARGET_KEYS)
        relation_type = _first(relation, _RELATION_TYPE_KEYS)

        relation_type = _RELATION_TYPE_ALIASES.get(relation_type, relation_type)

        if source not in candidate_ids or target not in candidate_ids:
            raise ValueError(
                f"relation references unknown candidate: {source!r} -> {target!r}"
            )
        if relation_type not in RELATION_TYPES:
            raise ValueError(f"unknown relation type: {relation_type!r}")

        relations.append(
            {
                "source": source,
                "target": target,
                "type": relation_type,
                "when_selected": bool(relation.get("when_selected", True)),
            }
        )

    coverage_groups = []
    for index, group in enumerate(raw.get("coverage_groups") or [], 1):
        if isinstance(group, str):
            coverage_groups.append(
                {
                    "group_id": group,
                    "candidate_ids": [],
                    "mode": "best",
                }
            )
            continue

        if not isinstance(group, dict):
            raise ValueError("coverage group must be an object or string")

        members = list(dict.fromkeys(group.get("candidate_ids") or []))
        for value in members:
            if value not in candidate_ids:
                raise ValueError(f"coverage group references unknown candidate: {value}")

        coverage_groups.append(
            {
                "group_id": group.get("group_id")
                or group.get("coverage_group")
                or f"group-{index}",
                "candidate_ids": members,
                "mode": group.get("mode", "best"),
            }
        )

    confidence = raw.get("confidence", 0.0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence must be numeric") from exc

    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")

    return {
        "selected_candidate_ids": selected,
        "relations": relations,
        "coverage_groups": coverage_groups,
        "excluded_candidate_ids": excluded,
        "confidence": confidence,
    }
