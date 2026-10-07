from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvidenceAdmissionConfig:
    per_query_cap: int = 2
    final_limit: int = 4


def _rrf_score(item: dict[str, Any]) -> float:
    return sum(
        1.0 / (60 + int(entry["rank"]))
        for entry in item.get("query_support", [])
    )


def admit_rrf_candidates(
    candidates: list[dict[str, Any]],
    *,
    config: EvidenceAdmissionConfig = EvidenceAdmissionConfig(),
) -> list[dict[str, Any]]:
    """Select a compact, query-diverse evidence set.

    This is a context-budget policy, not a semantic truth oracle.
    """
    if config.per_query_cap < 1:
        raise ValueError("per_query_cap must be >= 1")
    if config.final_limit < 1:
        raise ValueError("final_limit must be >= 1")
    if not candidates:
        return []

    eligible = [
        item for item in candidates
        if item.get("query_support")
        and min(int(entry["rank"]) for entry in item["query_support"]) <= config.per_query_cap
    ]
    if not eligible:
        return []

    ranked = sorted(
        eligible,
        key=lambda item: (
            -_rrf_score(item),
            min(int(entry["rank"]) for entry in item.get("query_support", [])),
            str(item.get("evidence_id", "")),
        ),
    )

    best_by_query: dict[int, dict[str, Any]] = {}
    for item in ranked:
        for entry in item.get("query_support", []):
            rank = int(entry["rank"])
            query_index = int(entry["query_index"])
            if rank > config.per_query_cap:
                continue
            current = best_by_query.get(query_index)
            if current is None:
                best_by_query[query_index] = item
                continue
            current_rank = min(
                int(s["rank"])
                for s in current.get("query_support", [])
                if int(s["query_index"]) == query_index
            )
            if rank < current_rank:
                best_by_query[query_index] = item

    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for query_index in sorted(best_by_query):
        item = best_by_query[query_index]
        key = str(item["evidence_id"])
        if key in seen:
            continue
        selected.append(item)
        seen.add(key)
        if len(selected) >= config.final_limit:
            return selected[: config.final_limit]

    for item in ranked:
        key = str(item["evidence_id"])
        if key in seen:
            continue
        selected.append(item)
        seen.add(key)
        if len(selected) >= config.final_limit:
            break

    return selected[: config.final_limit]
