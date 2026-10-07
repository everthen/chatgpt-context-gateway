from pathlib import Path

from context_gateway.benchmark import load_dataset, run_ucg_retrieval_benchmark
from context_gateway.benchmark.metrics import score_context_quality, score_retrieval


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "benchmarks" / "data" / "seed_v0.1.jsonl"


def test_seed_dataset_is_diagnostic_and_balanced():
    cases = load_dataset(DATASET)
    assert len(cases) == 16
    counts = {}
    for case in cases:
        counts[case.task_family] = counts.get(case.task_family, 0) + 1
        assert case.gold_evidence
        assert case.provenance_map
    assert counts == {
        "long_session": 4,
        "new_session": 4,
        "cross_provider": 4,
        "temporal_update": 4,
    }


def test_retrieval_metrics_known_values():
    returned = [
        {"evidence_key": "gold-a"},
        {"evidence_key": "distractor"},
        {"evidence_key": "gold-b"},
    ]
    score = score_retrieval(returned, {"gold-a", "gold-b"}, k=3)
    assert score["precision"] == 2 / 3
    assert score["recall"] == 1.0
    assert score["mrr"] == 1.0
    assert 0.0 < score["ndcg"] < 1.0

    quality = score_context_quality(
        [
            {"evidence_key": "gold-a", "provider": "chatgpt", "account_id": "main",
             "id": "c", "conversation_uid": "cu", "snapshot_id": "s", "message_id": "m",
             "raw_path": "raw", "raw_hash": "hash"},
            {"evidence_key": "distractor", "provider": "chatgpt", "account_id": "main",
             "id": "c2", "conversation_uid": "cu2", "snapshot_id": "s2", "message_id": "m2",
             "raw_path": "raw2", "raw_hash": "hash2"},
        ],
        allowed_keys={"gold-a"},
    )
    assert quality["context_noise_ratio"] == 0.5
    assert quality["provenance_completeness"] == 1.0


def test_ucg_retrieval_benchmark_runs_end_to_end(tmp_path: Path):
    cases = load_dataset(DATASET)
    result = run_ucg_retrieval_benchmark(cases, limit=8, output_dir=tmp_path)
    assert result["schema_version"] == "ucg-benchmark-run.v0.1"
    assert result["dataset_cases"] == 16
    assert result["runnable_arms"] == ["ucg"]
    assert len(result["case_results"]) == 16
    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "results.json").exists()
    for case_result in result["case_results"]:
        assert case_result["latency_ms"] >= 0
        assert case_result["context"]["provenance_completeness"] == 1.0
