from pathlib import Path

import pytest

from context_gateway.benchmark.traceability import TraceRecord, sha256_file


def make_record(**overrides):
    data = {
        "experiment_id": "EXP-2E",
        "step_id": "STEP-001",
        "objective": "Validate traceability contract",
        "parent_step": None,
        "repository": "everthen/chatgpt-context-gateway",
        "branch": "experiment/evidence-admission-v0.1",
        "code_commit": "abc123",
        "dataset_version": "seed_v0.1",
        "dataset_hash": "a" * 64,
        "assessor": "lexical",
        "assessor_version": "lexical-v0.1",
        "configuration": {"limit": 8},
        "artifact_paths": ("run.json",),
        "status": "pass",
        "finding": "Contract validates.",
        "decision": "keep",
        "next_step": "Continue",
        "recorded_at": "2026-10-07T00:00:00Z",
    }
    data.update(overrides)
    return TraceRecord(**data)


def test_trace_record_validates():
    record = make_record()
    payload = record.as_dict()
    assert payload["schema_version"] == "ucg-traceability.v0.1"
    assert payload["dataset_version"] == "seed_v0.1"


def test_missing_identity_is_rejected():
    with pytest.raises(ValueError):
        make_record(code_commit="").validate()


def test_invalid_status_is_rejected():
    with pytest.raises(ValueError):
        make_record(status="maybe").validate()


def test_dataset_hash_is_real_sha256(tmp_path: Path):
    path = tmp_path / "dataset.txt"
    path.write_text("hello", encoding="utf-8")
    assert sha256_file(path) == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29c1d94e5f4"
        "6a7a845e7f8f5c5fbd1c8b5e4b8f9f5d4e8f5e9"
    )
