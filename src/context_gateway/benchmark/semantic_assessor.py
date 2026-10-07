from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any


TASK_FIT = {"direct", "supporting", "contextual", "none"}
WORTHINESS_ROLE = {"direct_support", "supporting", "contradiction", "contextual", "none"}
TEMPORAL_STATE = {"current", "obsolete", "proposed", "unknown"}


@dataclass(frozen=True)
class BlindCandidate:
    candidate_id: str
    text: str
    provider: str
    account_id: str
    conversation_id: str
    message_id: str
    observed_at: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "text": self.text,
            "provider": self.provider,
            "account_id": self.account_id,
            "conversation_id": self.conversation_id,
            "message_id": self.message_id,
            "observed_at": self.observed_at,
        }


@dataclass(frozen=True)
class SemanticAssessment:
    candidate_id: str
    task_fit: str
    worthiness_role: str
    temporal_state: str
    claim_ids: tuple[str, ...]
    conflict_group: str | None
    redundancy_group: str | None
    provenance_complete: bool
    confidence: float

    def validate(self, candidate_ids: set[str]) -> None:
        if self.candidate_id not in candidate_ids:
            raise ValueError(f"unknown candidate_id: {self.candidate_id}")
        if self.task_fit not in TASK_FIT:
            raise ValueError(f"invalid task_fit: {self.task_fit}")
        if self.worthiness_role not in WORTHINESS_ROLE:
            raise ValueError(f"invalid worthiness_role: {self.worthiness_role}")
        if self.temporal_state not in TEMPORAL_STATE:
            raise ValueError(f"invalid temporal_state: {self.temporal_state}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if len(set(self.claim_ids)) != len(self.claim_ids):
            raise ValueError("claim_ids must be unique")


@dataclass(frozen=True)
class SemanticAssessmentRequest:
    query: str
    candidates: tuple[BlindCandidate, ...]
    prompt: str
    prompt_hash: str

    @property
    def candidate_ids(self) -> set[str]:
        return {candidate.candidate_id for candidate in self.candidates}


def blind_candidates(items: list[dict[str, Any]]) -> tuple[BlindCandidate, ...]:
    """Remove benchmark role labels and expose candidates under local IDs."""
    candidates: list[BlindCandidate] = []
    for index, item in enumerate(items, start=1):
        candidates.append(
            BlindCandidate(
                candidate_id=f"C{index}",
                text=str(item.get("excerpt") or item.get("content") or item.get("text") or ""),
                provider=str(item.get("provider") or ""),
                account_id=str(item.get("account_id") or ""),
                conversation_id=str(item.get("conversation_id") or item.get("id") or ""),
                message_id=str(item.get("message_id") or ""),
                observed_at=item.get("observed_at"),
            )
        )
    return tuple(candidates)


def build_semantic_assessment_prompt(
    query: str,
    candidates: tuple[BlindCandidate, ...],
) -> SemanticAssessmentRequest:
    candidate_block = json.dumps(
        [candidate.as_dict() for candidate in candidates],
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    prompt = f"""You are assessing whether retrieved evidence is worth sending to an LLM.

Do not assume that lexical similarity means usefulness.
Do not invent facts that are absent from the candidates.
Do not use benchmark labels because none are supplied.

Task:
1. Determine which candidates directly support, indirectly support, merely contextualize, contradict, or do not materially help answer the query.
2. Determine temporal state from the evidence and candidate metadata. Use "proposed" for plans/consideration that are not yet decisions.
3. Group candidates that express the same claim or the same unresolved conflict.
4. Preserve contradictory evidence when the conflict is unresolved.
5. Assess provenance completeness from the supplied identity fields.
6. Return one assessment for every candidate.

Allowed task_fit: direct, supporting, contextual, none.
Allowed worthiness_role: direct_support, supporting, contradiction, contextual, none.
Allowed temporal_state: current, obsolete, proposed, unknown.
confidence must be between 0 and 1.

Return JSON only with this schema:
{{
  "assessments": [
    {{
      "candidate_id": "C1",
      "task_fit": "direct",
      "worthiness_role": "direct_support",
      "temporal_state": "current",
      "claim_ids": ["claim-1"],
      "conflict_group": null,
      "redundancy_group": null,
      "provenance_complete": true,
      "confidence": 0.0
    }}
  ]
}}

QUERY:
{query}

CANDIDATES:
{candidate_block}
"""
    return SemanticAssessmentRequest(
        query=query,
        candidates=candidates,
        prompt=prompt,
        prompt_hash=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
    )


def parse_semantic_assessment(
    request: SemanticAssessmentRequest,
    raw_text: str,
) -> tuple[SemanticAssessment, ...]:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError("semantic assessor did not return valid JSON") from exc

    rows = payload.get("assessments")
    if not isinstance(rows, list):
        raise ValueError("semantic assessor JSON must contain assessments[]")

    expected_ids = request.candidate_ids
    seen: set[str] = set()
    results: list[SemanticAssessment] = []

    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("assessment entry must be an object")
        result = SemanticAssessment(
            candidate_id=str(row.get("candidate_id", "")),
            task_fit=str(row.get("task_fit", "")),
            worthiness_role=str(row.get("worthiness_role", "")),
            temporal_state=str(row.get("temporal_state", "")),
            claim_ids=tuple(str(value) for value in row.get("claim_ids", [])),
            conflict_group=(
                str(row["conflict_group"]) if row.get("conflict_group") is not None else None
            ),
            redundancy_group=(
                str(row["redundancy_group"])
                if row.get("redundancy_group") is not None
                else None
            ),
            provenance_complete=bool(row.get("provenance_complete", False)),
            confidence=float(row.get("confidence", -1)),
        )
        result.validate(expected_ids)
        if result.candidate_id in seen:
            raise ValueError(f"duplicate assessment for {result.candidate_id}")
        seen.add(result.candidate_id)
        results.append(result)

    if seen != expected_ids:
        missing = sorted(expected_ids - seen)
        extra = sorted(seen - expected_ids)
        raise ValueError(f"assessment coverage mismatch; missing={missing}, extra={extra}")

    return tuple(results)


def normalize_semantic_response(
    raw_text: str,
    request: SemanticAssessmentRequest,
) -> tuple[tuple[SemanticAssessment, ...], bool]:
    """Normalize semantically valid model variants for research scoring.

    Returns (assessments, protocol_compliant). The production contract remains
    strict via parse_semantic_assessment(); this helper only prevents a model's
    richer-but-equivalent JSON shape from becoming a semantic-quality score of
    zero. Extra fields are ignored, and a top-level candidates collection is
    accepted as a benchmark variant.
    """
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError("semantic assessor did not return valid JSON") from exc

    rows = payload.get("assessments")
    protocol_compliant = isinstance(rows, list)

    if rows is None:
        rows = payload.get("candidates")
    if not isinstance(rows, list):
        raise ValueError("semantic response must contain assessments[] or candidates[]")

    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("assessment entry must be an object")
        normalized.append(
            {
                "candidate_id": str(row.get("candidate_id", "")),
                "task_fit": str(row.get("task_fit", "")),
                "worthiness_role": str(row.get("worthiness_role", "")),
                "temporal_state": str(row.get("temporal_state", "")),
                "claim_ids": tuple(str(value) for value in row.get("claim_ids", [])),
                "conflict_group": (
                    str(row["conflict_group"])
                    if row.get("conflict_group") is not None
                    else None
                ),
                "redundancy_group": (
                    str(row["redundancy_group"])
                    if row.get("redundancy_group") is not None
                    else None
                ),
                "provenance_complete": bool(row.get("provenance_complete", False)),
                "confidence": float(row.get("confidence", -1)),
            }
        )

    try:
        canonical = tuple(
            parse_semantic_assessment(
                request,
                json.dumps({"assessments": normalized}),
            )
        )
        return canonical, protocol_compliant
    except ValueError as strict_exc:
        expected_ids = request.candidate_ids
        seen: set[str] = set()
        results: list[SemanticAssessment] = []
        for row in normalized:
            result = SemanticAssessment(
                candidate_id=row["candidate_id"],
                task_fit=row["task_fit"],
                worthiness_role=row["worthiness_role"],
                temporal_state=row["temporal_state"],
                claim_ids=row["claim_ids"],
                conflict_group=row["conflict_group"],
                redundancy_group=row["redundancy_group"],
                provenance_complete=row["provenance_complete"],
                confidence=row["confidence"],
            )
            result.validate(expected_ids)
            if result.candidate_id in seen:
                raise ValueError(f"duplicate assessment for {result.candidate_id}") from strict_exc
            seen.add(result.candidate_id)
            results.append(result)
        if seen != expected_ids:
            raise ValueError("assessment coverage mismatch") from strict_exc
        return tuple(results), False


class UnavailableSemanticAssessor:
    name = "unavailable"

    def assess(
        self,
        *,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> tuple[SemanticAssessment, ...]:
        raise RuntimeError(
            "semantic model assessor unavailable; no model result may be fabricated"
        )
