from __future__ import annotations

from math import log2
from typing import Any, Iterable


def _keys(items: Iterable[dict[str, Any]]) -> list[str]:
    return [str(item["evidence_key"]) for item in items]


def score_retrieval(
    returned: list[dict[str, Any]],
    gold_keys: set[str],
    *,
    k: int | None = None,
) -> dict[str, float]:
    ranked = returned[:k] if k else returned
    returned_keys = _keys(ranked)
    relevant_positions = [
        index for index, key in enumerate(returned_keys, start=1) if key in gold_keys
    ]
    hits = len(relevant_positions)
    denom = max(1, len(gold_keys))
    precision = hits / max(1, len(ranked))
    recall = hits / denom
    reciprocal_rank = 1 / relevant_positions[0] if relevant_positions else 0.0

    dcg = 0.0
    for position in relevant_positions:
        dcg += 1 / log2(position + 1)
    ideal_len = min(len(gold_keys), len(ranked))
    ideal_dcg = sum(1 / log2(position + 1) for position in range(1, ideal_len + 1))
    ndcg = dcg / ideal_dcg if ideal_dcg else 0.0

    return {
        "precision": precision,
        "recall": recall,
        "mrr": reciprocal_rank,
        "ndcg": ndcg,
        "gold_coverage": recall,
        "hits": float(hits),
        "returned": float(len(ranked)),
    }


def score_context_quality(
    returned: list[dict[str, Any]],
    *,
    allowed_keys: set[str],
) -> dict[str, float]:
    if not returned:
        return {
            "irrelevant_rate": 0.0,
            "context_noise_ratio": 0.0,
            "provenance_completeness": 1.0,
        }

    irrelevant = sum(1 for item in returned if item["evidence_key"] not in allowed_keys)
    missing_provenance = sum(
        1
        for item in returned
        if not all(
            item.get(field)
            for field in (
                "provider",
                "account_id",
                "id",
                "conversation_uid",
                "snapshot_id",
                "message_id",
                "raw_path",
                "raw_hash",
            )
        )
    )
    total = len(returned)
    return {
        "irrelevant_rate": irrelevant / total,
        "context_noise_ratio": irrelevant / total,
        "provenance_completeness": 1 - (missing_provenance / total),
    }


def aggregate(scores: list[dict[str, float]]) -> dict[str, float]:
    if not scores:
        return {}
    keys = sorted({key for score in scores for key in score})
    return {
        key: sum(float(score.get(key, 0.0)) for score in scores) / len(scores)
        for key in keys
    }
