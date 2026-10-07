from pathlib import Path

from benchmarks.contrastive_retention_v0_1 import load_suite, run_suite

ROOT = Path(__file__).resolve().parents[1]
SUITE = load_suite(
    ROOT / "benchmarks" / "attack_suites" / "contrastive_retention_v0_1.json"
)


def test_contrastive_aware_is_clean():
    result = run_suite(SUITE, "contrastive_aware")
    assert result["pass_rate"] == 1.0
    assert result["mean_required_recall"] == 1.0
    assert result["mean_contrastive_retention"] == 1.0
    assert result["mean_distractor_rejection"] == 1.0


def test_gold_only_falsifies_contrastive_cases():
    result = run_suite(SUITE, "gold_only")
    assert result["pass_rate"] < 1.0
    assert {
        r["case_id"] for r in result["results"] if r["passed"] is False
    } >= {"NS-04", "XP-02", "XP-04"}


def test_score_greedy_fails_required_contrastive_retention():
    result = run_suite(SUITE, "score_greedy_2")
    by_case = {r["case_id"]: r for r in result["results"]}
    assert by_case["NS-04"]["contrastive_retention"] == 0.0
    assert by_case["XP-02"]["contrastive_retention"] == 0.0
    assert by_case["XP-04"]["contrastive_retention"] == 0.0


def test_reference_selector_passes_contrastive_attack_suite():
    result = run_suite(SUITE, "reference_selector")
    assert result["pass_rate"] == 1.0
    assert result["mean_required_recall"] == 1.0
    assert result["mean_contrastive_retention"] == 1.0
    assert result["mean_distractor_rejection"] == 1.0


def test_all_admitted_preserves_contrastive_but_pays_noise():
    result = run_suite(SUITE, "all_admitted")
    assert result["mean_required_recall"] == 1.0
    assert result["mean_contrastive_retention"] == 1.0
    assert result["mean_distractor_rejection"] < 1.0


def test_tu04_empty_admission_is_attributed_upstream():
    result = run_suite(SUITE, "empty_admission_tu04")
    applicable = [r for r in result["results"] if r["passed"] is not None]
    assert len(applicable) == 1

    tu04 = applicable[0]
    assert tu04["case_id"] == "TU-04"
    assert tu04["status"] == "UPSTREAM_ADMISSION_FAILURE"
    assert tu04["selection_evaluable"] is False
    assert tu04["failure_owner"] == "admission"
    assert result["pass_rate"] == 1.0


def test_suite_json_is_self_consistent():
    case_ids = [c["case_id"] for c in SUITE["cases"]]
    assert len(case_ids) == len(set(case_ids))

    for case in SUITE["cases"]:
        keys = {item["key"] for item in case["candidates"]}
        assert set(case["minimal_sufficient_keys"]) <= keys
        assert set(case.get("must_drop_keys", [])) <= keys
