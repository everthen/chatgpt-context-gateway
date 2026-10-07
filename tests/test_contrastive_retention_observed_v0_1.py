import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OBSERVED = json.loads(
    (
        ROOT
        / "benchmarks"
        / "runs"
        / "seed_v0.1"
        / "2026-10-07_contrastive_retention_observed_seams_v0.1.json"
    ).read_text(encoding="utf-8")
)


def _case(case_id):
    return next(item for item in OBSERVED["cases"] if item["case_id"] == case_id)


def test_ns04_freezes_over_pruning_regression():
    case = _case("NS-04")
    by_arm = {item["arm"]: item for item in case["observed"]}
    assert "ns04.dist1" not in by_arm["ucg_sonnet"]["bundle_keys"]
    assert "ns04.dist1" in by_arm["ucg_opus"]["bundle_keys"]
    assert by_arm["ucg_opus"]["task_completion_score"] > by_arm["ucg_sonnet"]["task_completion_score"]


def test_xp02_freezes_provider_contrast_regression():
    case = _case("XP-02")
    by_arm = {item["arm"]: item for item in case["observed"]}
    assert "xp02.dist" not in by_arm["ucg_gemini"]["bundle_keys"]
    assert "xp02.dist" in by_arm["ucg_sonnet"]["bundle_keys"]
    assert by_arm["ucg_sonnet"]["task_completion_score"] > by_arm["ucg_gemini"]["task_completion_score"]


def test_xp04_freezes_account_isolation_regression():
    case = _case("XP-04")
    by_arm = {item["arm"]: item for item in case["observed"]}
    assert "xp04.dist" not in by_arm["ucg_sonnet"]["bundle_keys"]
    assert "xp04.dist" in by_arm["ucg_opus"]["bundle_keys"]
    assert by_arm["ucg_opus"]["task_completion_score"] > by_arm["ucg_sonnet"]["task_completion_score"]


def test_tu04_is_attributed_to_admission():
    case = _case("TU-04")
    by_arm = {item["arm"]: item for item in case["observed"]}
    assert by_arm["ucg_sonnet"]["bundle_keys"] == []
    assert by_arm["ucg_sonnet"]["task_completion_score"] == 0.0
    assert case["regression_assertion"]["failure_owner"] == "admission"


def test_source_traceability_is_explicit():
    assert OBSERVED["source_experiment"] == "UCG-EVAL-AQ-SONNET-20261007-v0.2"
    assert OBSERVED["source_branch"] == "experiment/evidence-admission-v0.1"
    assert OBSERVED["source_result_path"].endswith(
        "2026-10-07_answer_quality_sonnet_result_v0.2.json"
    )
