from __future__ import annotations

from collections import Counter
import re
from typing import Any, Iterable

from .schema import BenchmarkCase
from .worthiness import EvidenceAssessment


_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "is", "it", "of", "on", "or", "the", "to", "was", "what",
    "when", "who", "why", "with", "current", "latest", "after", "before",
}


def _tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in _STOPWORDS
    ]


def lexical_overlap(query: str, text: str) -> float:
    q = Counter(_tokens(query))
    if not q:
        return 0.0
    source = set(_tokens(text))
    matched = sum(1 for token in q if token in source)
    return matched / len(q)


def rule_assess(
    *,
    evidence: dict[str, Any],
    query: str,
    temporal_state: str = "unknown",
) -> EvidenceAssessment:
    """Deliberately weak, lexical-only worthiness baseline.

    It does not inspect gold labels, claim annotations, or expected outcomes.
    It is a lower-bound control for the future semantic/model assessor.
    """
    overlap = lexical_overlap(query, str(evidence.get("excerpt") or evidence.get("content") or ""))
    if overlap >= 0.67:
        task_fit = "direct"
        role = "direct_support"
    elif overlap >= 0.34:
        task_fit = "supporting"
        role = "supporting"
    else:
        task_fit = "none"
        role = "none"

    evidence_hash = str(
        evidence.get("raw_hash")
        or evidence.get("content_hash")
        or evidence.get("evidence_id")
        or ""
    )
    return EvidenceAssessment(
        evidence_id=str(evidence["evidence_id"]),
        evidence_hash=evidence_hash,
        task_fit=task_fit,
        worthiness_role=role,
        claim_ids=(),
        temporal_state=temporal_state,
        provenance_complete=all(
            evidence.get(field)
            for field in (
                "provider",
                "account_id",
                "id",
                "message_id",
                "snapshot_id",
                "raw_path",
                "raw_hash",
            )
        ),
        assessment_method="rule",
        assessor_version="lexical-v0.1",
        confidence=overlap,
    )


def oracle_label(case: BenchmarkCase, evidence_key: str) -> tuple[str, str]:
    if evidence_key in {x.evidence_key for x in case.gold_evidence}:
        return "direct", "direct_support"
    if evidence_key in {x.evidence_key for x in case.supporting_evidence}:
        return "supporting", "supporting"
    return "none", "none"


def score_assessments(
    case: BenchmarkCase,
    predictions: Iterable[tuple[str, EvidenceAssessment]],
) -> dict[str, float]:
    rows = list(predictions)
    if not rows:
        return {
            "task_fit_accuracy": 0.0,
            "worthiness_role_accuracy": 0.0,
            "worthiness_precision": 0.0,
            "worthiness_recall": 0.0,
        }

    task_correct = 0
    role_correct = 0
    tp = fp = fn = 0

    gold_positive = {
        x.evidence_key for x in case.gold_evidence + case.supporting_evidence
    }

    for evidence_key, assessment in rows:
        gold_fit, gold_role = oracle_label(case, evidence_key)
        task_correct += assessment.task_fit == gold_fit
        role_correct += assessment.worthiness_role == gold_role

        predicted_positive = assessment.worthiness_role != "none"
        actual_positive = evidence_key in gold_positive

        if predicted_positive and actual_positive:
            tp += 1
        elif predicted_positive and not actual_positive:
            fp += 1
        elif not predicted_positive and actual_positive:
            fn += 1

    total = len(rows)
    return {
        "task_fit_accuracy": task_correct / total,
        "worthiness_role_accuracy": role_correct / total,
        "worthiness_precision": tp / max(1, tp + fp),
        "worthiness_recall": tp / max(1, tp + fn),
    }
