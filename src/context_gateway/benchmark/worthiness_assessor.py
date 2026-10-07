from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .schema import BenchmarkCase
from .worthiness import EvidenceAssessment
from .worthiness_eval import rule_assess


class WorthinessAssessor(Protocol):
    name: str

    def assess(
        self,
        *,
        evidence: dict[str, Any],
        case: BenchmarkCase,
    ) -> EvidenceAssessment:
        ...


@dataclass(frozen=True)
class RuleWorthinessAssessor:
    name: str = "lexical-v0.1"

    def assess(
        self,
        *,
        evidence: dict[str, Any],
        case: BenchmarkCase,
    ) -> EvidenceAssessment:
        return rule_assess(
            evidence=evidence,
            query=case.query,
            temporal_state="unknown",
        )


@dataclass(frozen=True)
class UnavailableWorthinessAssessor:
    """Explicit placeholder for a real model assessor.

    It must remain unavailable until a real model/provider adapter is wired.
    The benchmark must never fabricate model assessments.
    """

    name: str = "unavailable"

    def assess(
        self,
        *,
        evidence: dict[str, Any],
        case: BenchmarkCase,
    ) -> EvidenceAssessment:
        raise RuntimeError(
            "real worthiness assessor is unavailable; do not fabricate an assessment"
        )
