from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


ADMISSION = {"admit", "admit_conflict", "reject"}
SUFFICIENCY = {"required", "complementary", "optional", "not_needed"}
TASK_FIT = {"direct", "supporting", "contextual", "none"}
WORTHINESS_ROLE = {"direct_support", "supporting", "contradiction", "contextual", "none"}
TEMPORAL_STATE = {"current", "obsolete", "proposed", "unknown"}


@dataclass(frozen=True)
class SemanticGoldLabel:
    evidence_key: str
    task_fit: str
    worthiness_role: str
    temporal_state: str
    admission: str
    sufficiency_role: str
    claim_ids: tuple[str, ...] = ()
    conflict_group: str | None = None
    rationale: str = ""

    def validate(self) -> None:
        if not self.evidence_key:
            raise ValueError("evidence_key must not be empty")
        if self.task_fit not in TASK_FIT:
            raise ValueError(f"invalid task_fit: {self.task_fit}")
        if self.worthiness_role not in WORTHINESS_ROLE:
            raise ValueError(f"invalid worthiness_role: {self.worthiness_role}")
        if self.temporal_state not in TEMPORAL_STATE:
            raise ValueError(f"invalid temporal_state: {self.temporal_state}")
        if self.admission not in ADMISSION:
            raise ValueError(f"invalid admission: {self.admission}")
        if self.sufficiency_role not in SUFFICIENCY:
            raise ValueError(f"invalid sufficiency_role: {self.sufficiency_role}")
        if len(set(self.claim_ids)) != len(self.claim_ids):
            raise ValueError("claim_ids must be unique")

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class SemanticCaseGold:
    case_id: str
    query_mode: str
    labels: tuple[SemanticGoldLabel, ...]
    minimal_sufficient_set: tuple[str, ...]
    conflict_complete_set: tuple[str, ...]
    audit_rationale: str

    def validate(self) -> None:
        if not self.case_id:
            raise ValueError("case_id must not be empty")
        if not self.query_mode:
            raise ValueError("query_mode must not be empty")

        seen: set[str] = set()
        for label in self.labels:
            label.validate()
            if label.evidence_key in seen:
                raise ValueError(f"duplicate gold label: {label.evidence_key}")
            seen.add(label.evidence_key)

        if not set(self.minimal_sufficient_set).issubset(seen):
            raise ValueError("minimal_sufficient_set references unknown evidence")
        if not set(self.conflict_complete_set).issubset(seen):
            raise ValueError("conflict_complete_set references unknown evidence")

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "case_id": self.case_id,
            "query_mode": self.query_mode,
            "labels": [label.as_dict() for label in self.labels],
            "minimal_sufficient_set": list(self.minimal_sufficient_set),
            "conflict_complete_set": list(self.conflict_complete_set),
            "audit_rationale": self.audit_rationale,
        }


def derive_admission(
    *,
    task_fit: str,
    worthiness_role: str,
    temporal_state: str,
    query_mode: str,
) -> str:
    """Derive an expected gate action from a semantic assessment.

    This is intentionally a scoring/control rule, not a truth oracle. The
    semantic assessor predicts relationship; the gate policy decides whether
    that relationship is worth carrying into the current context mode.
    """
    if task_fit == "none":
        return "reject"
    if query_mode in {"current_fact", "latest_current_decision"} and temporal_state == "obsolete":
        return "reject"
    if worthiness_role == "contradiction":
        return "admit_conflict"
    if worthiness_role in {"direct_support", "supporting"}:
        return "admit"
    return "reject"
