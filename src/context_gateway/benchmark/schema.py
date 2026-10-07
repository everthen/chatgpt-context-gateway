from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable


REQUIRED_CASE_FIELDS = {
    "case_id",
    "task_family",
    "corpus",
    "query",
    "gold_evidence",
    "supporting_evidence",
    "distractors",
    "temporal_state",
    "expected_claims",
    "provenance_map",
    "difficulty",
}

TASK_FAMILIES = {
    "long_session",
    "new_session",
    "cross_provider",
    "temporal_update",
}


@dataclass(frozen=True)
class EvidenceRef:
    evidence_key: str
    provider: str
    account_id: str
    conversation_id: str
    message_id: str

    @classmethod
    def from_obj(cls, obj: dict[str, Any]) -> "EvidenceRef":
        required = {
            "evidence_key",
            "provider",
            "account_id",
            "conversation_id",
            "message_id",
        }
        missing = required - set(obj)
        if missing:
            raise ValueError(f"evidence ref missing fields: {sorted(missing)}")
        return cls(
            evidence_key=str(obj["evidence_key"]),
            provider=str(obj["provider"]),
            account_id=str(obj["account_id"]),
            conversation_id=str(obj["conversation_id"]),
            message_id=str(obj["message_id"]),
        )


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    task_family: str
    corpus: dict[str, Any]
    query: str
    gold_evidence: tuple[EvidenceRef, ...]
    supporting_evidence: tuple[EvidenceRef, ...]
    distractors: tuple[EvidenceRef, ...]
    temporal_state: dict[str, Any]
    expected_claims: tuple[str, ...]
    provenance_map: dict[str, dict[str, Any]]
    difficulty: str

    @classmethod
    def from_obj(cls, obj: dict[str, Any]) -> "BenchmarkCase":
        missing = REQUIRED_CASE_FIELDS - set(obj)
        if missing:
            raise ValueError(f"case missing fields: {sorted(missing)}")
        task_family = str(obj["task_family"])
        if task_family not in TASK_FAMILIES:
            raise ValueError(f"unsupported task_family: {task_family}")
        difficulty = str(obj["difficulty"])
        if difficulty not in {"easy", "medium", "hard", "adversarial"}:
            raise ValueError(f"unsupported difficulty: {difficulty}")
        query = str(obj["query"]).strip()
        if not query:
            raise ValueError("query must not be empty")
        case_id = str(obj["case_id"]).strip()
        if not case_id:
            raise ValueError("case_id must not be empty")

        gold = tuple(EvidenceRef.from_obj(x) for x in obj["gold_evidence"])
        supporting = tuple(EvidenceRef.from_obj(x) for x in obj["supporting_evidence"])
        distractors = tuple(EvidenceRef.from_obj(x) for x in obj["distractors"])
        if not gold:
            raise ValueError(f"{case_id}: gold_evidence must not be empty")

        keys = {x.evidence_key for x in gold + supporting + distractors}
        if len(keys) != len(gold) + len(supporting) + len(distractors):
            raise ValueError(f"{case_id}: duplicate evidence_key across evidence sets")

        provenance_map = dict(obj["provenance_map"])
        for ref in gold + supporting + distractors:
            mapped = provenance_map.get(ref.evidence_key)
            if not isinstance(mapped, dict):
                raise ValueError(
                    f"{case_id}: provenance_map missing {ref.evidence_key}"
                )

        return cls(
            case_id=case_id,
            task_family=task_family,
            corpus=dict(obj["corpus"]),
            query=query,
            gold_evidence=gold,
            supporting_evidence=supporting,
            distractors=distractors,
            temporal_state=dict(obj["temporal_state"]),
            expected_claims=tuple(str(x) for x in obj["expected_claims"]),
            provenance_map=provenance_map,
            difficulty=difficulty,
        )


def load_dataset(path: str | Path) -> list[BenchmarkCase]:
    path = Path(path)
    if path.suffix == ".jsonl":
        records: Iterable[dict[str, Any]] = (
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    elif path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload if isinstance(payload, list) else payload["cases"]
    else:
        raise ValueError(f"unsupported dataset format: {path.suffix}")

    cases = [BenchmarkCase.from_obj(record) for record in records]
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("dataset contains duplicate case_id values")
    return cases
