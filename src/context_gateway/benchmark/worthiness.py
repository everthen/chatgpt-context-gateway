from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


TASK_FIT = {"direct", "supporting", "contextual", "none"}
WORTHINESS_ROLE = {"direct_support", "supporting", "contradiction", "contextual", "none"}
TEMPORAL_STATE = {"current", "obsolete", "proposed", "unknown"}
ASSESSMENT_METHOD = {"rule", "model", "human", "oracle"}


@dataclass(frozen=True)
class EvidenceAssessment:
    evidence_id: str
    evidence_hash: str
    task_fit: str
    worthiness_role: str
    claim_ids: tuple[str, ...]
    temporal_state: str
    conflict_group: str | None = None
    redundancy_group: str | None = None
    provenance_complete: bool = True
    assessment_method: str = "rule"
    assessor_version: str = "v0.1"
    confidence: float | None = None

    def validate(self) -> None:
        if not self.evidence_id:
            raise ValueError("evidence_id must not be empty")
        if not self.evidence_hash:
            raise ValueError("evidence_hash must not be empty")
        if self.task_fit not in TASK_FIT:
            raise ValueError(f"invalid task_fit: {self.task_fit}")
        if self.worthiness_role not in WORTHINESS_ROLE:
            raise ValueError(f"invalid worthiness_role: {self.worthiness_role}")
        if self.temporal_state not in TEMPORAL_STATE:
            raise ValueError(f"invalid temporal_state: {self.temporal_state}")
        if self.assessment_method not in ASSESSMENT_METHOD:
            raise ValueError(f"invalid assessment_method: {self.assessment_method}")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if len(set(self.claim_ids)) != len(self.claim_ids):
            raise ValueError("claim_ids must be unique")

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


def apply_assessment(
    evidence: dict[str, Any],
    assessment: EvidenceAssessment,
) -> dict[str, Any]:
    """Bind a worthiness assessment to the exact retrieved evidence item.

    The evidence hash must be supplied by the retrieval/archive layer and must
    match the hash used when the assessment was produced.
    """
    assessment.validate()

    if str(evidence.get("evidence_id")) != assessment.evidence_id:
        raise ValueError("assessment evidence_id does not match retrieved evidence")

    actual_hash = str(evidence.get("raw_hash") or evidence.get("content_hash") or "")
    if actual_hash != assessment.evidence_hash:
        raise ValueError("assessment evidence_hash does not match retrieved evidence")

    output = dict(evidence)
    output.update(
        {
            "task_fit": assessment.task_fit,
            "worthiness_role": assessment.worthiness_role,
            "claim_ids": list(assessment.claim_ids),
            "temporal_state": assessment.temporal_state,
            "provenance_complete": assessment.provenance_complete,
            "assessment_method": assessment.assessment_method,
            "assessor_version": assessment.assessor_version,
        }
    )

    if assessment.conflict_group:
        output["conflict_group"] = assessment.conflict_group
    if assessment.redundancy_group:
        output["redundancy_group"] = assessment.redundancy_group

    output["worthiness_assessment"] = assessment.as_dict()
    return output
