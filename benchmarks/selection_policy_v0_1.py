from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_REQUIRED_RELATION_TYPES = {
    "required_contrast",
    "required_boundary_contrast",
    "required_conflict",
    "required_state_contrast",
}


@dataclass(frozen=True)
class SelectionDecision:
    selected_keys: tuple[str, ...]
    excluded_keys: tuple[str, ...]
    closure_added_keys: tuple[str, ...]


def _score(item: dict[str, Any]) -> float:
    value = item.get("semantic_score", 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _admitted(item: dict[str, Any]) -> bool:
    return item.get("admission") in {"required", "accepted", "optional"}


def _primary(item: dict[str, Any]) -> bool:
    selection = item.get("selection") or {}
    return bool(selection.get("primary"))


def _noise(item: dict[str, Any]) -> bool:
    selection = item.get("selection") or {}
    return bool(selection.get("optional_noise"))


def _relations(item: dict[str, Any]) -> list[dict[str, Any]]:
    selection = item.get("selection") or {}
    relations = selection.get("relations") or []
    return [r for r in relations if isinstance(r, dict)]


def select_context(
    candidates: list[dict[str, Any]],
    *,
    budget: int | None = None,
) -> SelectionDecision:
    """Select minimum sufficient context from admitted candidates.

    Policy:
    1. Select the strongest primary candidate for each claim.
    2. Close over explicitly required epistemic relations.
    3. Never add optional noise merely because it has a higher semantic score.
    4. If a budget is hit, relation-closure wins over raw semantic score.
    """

    by_key = {item["key"]: item for item in candidates if _admitted(item)}
    selected: list[str] = []

    primary_items = [
        item
        for item in by_key.values()
        if _primary(item) and not _noise(item)
    ]

    claim_to_items: dict[str, list[dict[str, Any]]] = {}
    for item in primary_items:
        for claim_id in (item.get("selection") or {}).get("claim_ids") or []:
            claim_to_items.setdefault(str(claim_id), []).append(item)

    for claim_id in sorted(claim_to_items):
        winner = max(
            claim_to_items[claim_id],
            key=lambda item: (_score(item), item["key"]),
        )
        if winner["key"] not in selected:
            selected.append(winner["key"])

    if not selected and by_key:
        fallback = max(by_key.values(), key=lambda item: (_score(item), item["key"]))
        if not _noise(fallback):
            selected.append(fallback["key"])

    closure_added: list[str] = []
    changed = True
    while changed:
        changed = False
        for source_key in list(selected):
            source = by_key[source_key]
            for relation in _relations(source):
                if relation.get("when_selected") is not True:
                    continue
                if relation.get("type") not in _REQUIRED_RELATION_TYPES:
                    continue
                target_key = relation.get("target")
                if target_key not in by_key or target_key in selected:
                    continue
                selected.append(target_key)
                closure_added.append(target_key)
                changed = True

    if budget is not None:
        if budget < 1:
            raise ValueError("budget must be >= 1")

        # Never remove a closure item first. Trim only non-closure selections,
        # keeping one primary anchor per claim whenever possible.
        if len(selected) > budget:
            closure = set(closure_added)
            protected = [key for key in selected if key in closure]
            anchors = [key for key in selected if key not in closure]
            remaining = budget - len(protected)
            if remaining < 0:
                raise ValueError("budget smaller than required contrastive closure")
            anchors = sorted(
                anchors,
                key=lambda key: (_score(by_key[key]), key),
                reverse=True,
            )[:remaining]
            selected = anchors + protected

    selected_set = set(selected)
    excluded = sorted(
        item["key"]
        for item in candidates
        if item["key"] not in selected_set
    )

    return SelectionDecision(
        selected_keys=tuple(selected),
        excluded_keys=tuple(excluded),
        closure_added_keys=tuple(closure_added),
    )
