from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


TRACEABILITY_SCHEMA = "ucg-traceability.v0.1"


@dataclass(frozen=True)
class TraceRecord:
    experiment_id: str
    step_id: str
    objective: str
    parent_step: str | None
    repository: str
    branch: str
    code_commit: str
    dataset_version: str
    dataset_hash: str
    assessor: str
    assessor_version: str
    configuration: dict[str, Any]
    artifact_paths: tuple[str, ...]
    status: str
    finding: str
    decision: str
    next_step: str
    recorded_at: str

    def validate(self) -> None:
        required = {
            "experiment_id": self.experiment_id,
            "step_id": self.step_id,
            "objective": self.objective,
            "repository": self.repository,
            "branch": self.branch,
            "code_commit": self.code_commit,
            "dataset_version": self.dataset_version,
            "dataset_hash": self.dataset_hash,
            "assessor": self.assessor,
            "assessor_version": self.assessor_version,
            "status": self.status,
            "finding": self.finding,
            "decision": self.decision,
            "next_step": self.next_step,
            "recorded_at": self.recorded_at,
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise ValueError(f"trace record missing fields: {missing}")

        try:
            datetime.fromisoformat(self.recorded_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("recorded_at must be ISO-8601") from exc

        if len(self.dataset_hash) != 64:
            raise ValueError("dataset_hash must be a SHA-256 hex digest")

        if self.status not in {"pass", "fail", "inconclusive", "blocked"}:
            raise ValueError(f"invalid status: {self.status}")

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return {"schema_version": TRACEABILITY_SCHEMA, **asdict(self)}


def sha256_file(path: str | Path) -> str:
    data = Path(path).read_bytes()
    return hashlib.sha256(data).hexdigest()


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_trace_record(path: str | Path, record: TraceRecord) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(record.as_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
