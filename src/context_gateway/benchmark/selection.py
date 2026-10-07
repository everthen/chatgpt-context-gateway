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


_TEMPORAL_MODES = {"current", "history", "neutral"}


@dataclass(frozen=True)
class TemporalConflictPolicy:
    final_limit: int = 4
    mode: str = "current"


def _rank_key(item: dict[str, Any]) -> tuple[float, int, str]:
    return (
        -_rrf_score(item),
        min(
            int(entry["rank"])
            for entry in item.get("query_support", [{"rank": 10**9}])
        ),
        str(item.get("evidence_id", "")),
    )


def _annotate(item: dict[str, Any], **annotations: Any) -> dict[str, Any]:
    output = dict(item)
    existing = dict(output.get("admission_annotation") or {})
    existing.update(annotations)
    output["admission_annotation"] = existing
    return output


def admit_temporal_conflicts(
    candidates: list[dict[str, Any]],
    *,
    policy: TemporalConflictPolicy = TemporalConflictPolicy(),
) -> list[dict[str, Any]]:
    """Resolve temporal/conflicting candidates after evidence retrieval.

    This function consumes upstream temporal analysis. It does not infer truth
    from timestamps alone.

    Candidate metadata:
      temporal_state: current | obsolete | unknown
      conflict_group: identifier for mutually conflicting claims
      temporal_relation: supersedes | conflict_unresolved | optional
    """
    if policy.final_limit < 1:
        raise ValueError("final_limit must be >= 1")
    if policy.mode not in _TEMPORAL_MODES:
        raise ValueError(f"unsupported temporal mode: {policy.mode}")
    if not candidates:
        return []

    ranked = sorted(candidates, key=_rank_key)
    groups: dict[str, list[dict[str, Any]]] = {}
    ungrouped: list[dict[str, Any]] = []
    for item in ranked:
        group = item.get("conflict_group")
        if group:
            groups.setdefault(str(group), []).append(item)
        else:
            ungrouped.append(item)

    selected: list[dict[str, Any]] = []

    for item in ungrouped:
        state = item.get("temporal_state", "unknown")
        if policy.mode == "current" and state == "obsolete":
            continue
        selected.append(
            _annotate(item, temporal_resolution="standalone", conflict_status="none")
        )

    for group_id, items in groups.items():
        current = [x for x in items if x.get("temporal_state") == "current"]
        obsolete = [x for x in items if x.get("temporal_state") == "obsolete"]
        unknown = [
            x
            for x in items
            if x.get("temporal_state") not in {"current", "obsolete"}
        ]
        superseding = [x for x in current if x.get("temporal_relation") == "supersedes"]
        unresolved = [
            x
            for x in items
            if x.get("temporal_relation") == "conflict_unresolved"
        ]

        if policy.mode == "history":
            selected.extend(
                _annotate(
                    x,
                    temporal_resolution="history",
                    conflict_status="unresolved" if unresolved else "resolved",
                    conflict_group=group_id,
                )
                for x in sorted(current or unknown, key=_rank_key)
            )
            if obsolete:
                selected.append(
                    _annotate(
                        sorted(obsolete, key=_rank_key)[0],
                        temporal_resolution="historical_predecessor",
                        conflict_status="resolved",
                        conflict_group=group_id,
                    )
                )
            continue

        if superseding:
            winner = sorted(superseding, key=_rank_key)[0]
            selected.append(
                _annotate(
                    winner,
                    temporal_resolution="supersedes_previous",
                    conflict_status="resolved",
                    conflict_group=group_id,
                )
            )
            continue

        if current:
            if len(current) == 1 and obsolete:
                selected.append(
                    _annotate(
                        current[0],
                        temporal_resolution="current_over_obsolete",
                        conflict_status="resolved_by_temporal_state",
                        conflict_group=group_id,
                    )
                )
            else:
                selected.extend(
                    _annotate(
                        x,
                        temporal_resolution="current_unresolved",
                        conflict_status="unresolved",
                        conflict_group=group_id,
                    )
                    for x in sorted(current, key=_rank_key)
                )
            continue

        if unknown:
            selected.append(
                _annotate(
                    sorted(unknown, key=_rank_key)[0],
                    temporal_resolution="unknown",
                    conflict_status="unresolved",
                    conflict_group=group_id,
                )
            )

    selected = sorted(selected, key=_rank_key)
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in selected:
        key = str(item["evidence_id"])
        if key in seen:
            continue
        output.append(item)
        seen.add(key)
        if len(output) >= policy.final_limit:
            break
    return output
