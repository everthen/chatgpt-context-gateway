from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .schema import BenchmarkCase
from .semantic_assessor import BlindCandidate, blind_candidates


def build_blind_case(
    case: BenchmarkCase,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create model-facing input without benchmark truth labels."""
    blind = blind_candidates(candidates)
    return {
        "case_id": case.case_id,
        "query": case.query,
        "candidates": [candidate.as_dict() for candidate in blind],
    }


def build_gold_sidecar(
    case: BenchmarkCase,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create evaluation-only labels keyed by the local blind candidate ID."""
    gold = {item.evidence_key for item in case.gold_evidence}
    supporting = {item.evidence_key for item in case.supporting_evidence}
    obsolete = set(case.temporal_state.get("obsolete", []))
    current = set(case.temporal_state.get("current", []))
    proposed = set(case.temporal_state.get("proposed", []))

    labels = []
    blind = blind_candidates(candidates)

    for candidate, raw in zip(blind, candidates):
        key = str(raw["evidence_key"])
        if key in gold:
            task_fit = "direct"
            role = "direct_support"
        elif key in supporting:
            task_fit = "supporting"
            role = "supporting"
        else:
            task_fit = "none"
            role = "none"

        if key in obsolete:
            temporal = "obsolete"
        elif key in proposed:
            temporal = "proposed"
        elif key in current:
            temporal = "current"
        else:
            temporal = "unknown"

        labels.append(
            {
                "candidate_id": candidate.candidate_id,
                "evidence_key": key,
                "task_fit": task_fit,
                "worthiness_role": role,
                "temporal_state": temporal,
            }
        )

    return {
        "case_id": case.case_id,
        "labels": labels,
    }
