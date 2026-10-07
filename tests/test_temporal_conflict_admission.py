import json
from pathlib import Path

from context_gateway.benchmark.selection import (
    TemporalConflictPolicy,
    admit_temporal_conflicts,
)


ROOT = Path(__file__).resolve().parents[1]
ATTACKS = ROOT / "benchmarks" / "attacks" / "temporal_conflict_v0.1.jsonl"


def load_attacks():
    return [
        json.loads(line)
        for line in ATTACKS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def run(case):
    return admit_temporal_conflicts(
        case["candidates"],
        policy=TemporalConflictPolicy(
            final_limit=case.get("final_limit", 4),
            mode=case["mode"],
        ),
    )


def ids(items):
    return [item["evidence_id"] for item in items]


def test_temporal_conflict_attack_suite():
    for case in load_attacks():
        result = run(case)
        assert ids(result) == case["expected_ids"], case["attack_id"]

        marked = {
            item["evidence_id"]
            for item in result
            if item.get("admission_annotation", {}).get("conflict_status") == "unresolved"
        }
        assert marked == set(case.get("expected_unresolved_ids", [])), case["attack_id"]

        annotations = {
            item["evidence_id"]: item["admission_annotation"]
            for item in result
        }
        for evidence_id, expected in case.get("expected_annotations", {}).items():
            assert annotations[evidence_id] == expected, case["attack_id"]


def test_recency_alone_does_not_resolve_conflict():
    candidates = [
        {
            "evidence_id": "old",
            "query_support": [{"query_index": 0, "query": "policy", "rank": 1}],
            "temporal_state": "obsolete",
            "conflict_group": "g1",
            "observed_at": 1700000000,
        },
        {
            "evidence_id": "new",
            "query_support": [{"query_index": 0, "query": "policy", "rank": 2}],
            "temporal_state": "current",
            "conflict_group": "g1",
            "observed_at": 1800000000,
        },
    ]

    selected = admit_temporal_conflicts(
        candidates,
        policy=TemporalConflictPolicy(mode="current"),
    )

    assert ids(selected) == ["new"]
    assert selected[0]["admission_annotation"]["conflict_status"] == "unresolved"


def test_explicit_supersession_resolves_conflict():
    candidates = [
        {
            "evidence_id": "old",
            "query_support": [{"query_index": 0, "query": "policy", "rank": 1}],
            "temporal_state": "obsolete",
            "conflict_group": "g1",
        },
        {
            "evidence_id": "new",
            "query_support": [{"query_index": 0, "query": "policy", "rank": 2}],
            "temporal_state": "current",
            "temporal_relation": "supersedes",
            "conflict_group": "g1",
        },
    ]

    selected = admit_temporal_conflicts(
        candidates,
        policy=TemporalConflictPolicy(mode="current"),
    )

    assert ids(selected) == ["new"]
    assert selected[0]["admission_annotation"]["conflict_status"] == "resolved"
    assert selected[0]["admission_annotation"]["temporal_resolution"] == "supersedes_previous"
