from pathlib import Path
import json

from benchmarks.selection_policy_v0_1 import select_context

ROOT = Path(__file__).resolve().parents[1]
SUITE = json.loads(
    (
        ROOT
        / "benchmarks"
        / "attack_suites"
        / "contrastive_retention_v0_1.json"
    ).read_text(encoding="utf-8")
)


def _case(case_id):
    return next(c for c in SUITE["cases"] if c["case_id"] == case_id)


def test_ns04_closes_required_contrast():
    result = select_context(_case("NS-04")["candidates"])
    assert set(result.selected_keys) == {"ns04.gold", "ns04.conflict"}
    assert result.closure_added_keys == ("ns04.conflict",)


def test_xp02_closes_provider_contrast():
    result = select_context(_case("XP-02")["candidates"])
    assert set(result.selected_keys) == {
        "xp02.openai",
        "xp02.claude",
        "xp02.dist",
    }
    assert result.closure_added_keys == ("xp02.dist",)


def test_xp04_closes_wrong_account_boundary():
    result = select_context(_case("XP-04")["candidates"])
    assert set(result.selected_keys) == {"xp04.gold", "xp04.dist"}
    assert result.closure_added_keys == ("xp04.dist",)


def test_tu04_keeps_latest_support_only():
    result = select_context(_case("TU-04")["candidates"])
    assert result.selected_keys == ("tu04.gold",)
    assert not result.closure_added_keys


def test_selector_does_not_choose_higher_scored_noise():
    case = _case("NS-04")
    result = select_context(case["candidates"])
    assert "ns04.unrelated" not in result.selected_keys


def test_selector_rejects_unadmitted_candidates():
    candidates = [
        {
            "key": "accepted",
            "semantic_score": 0.9,
            "admission": "accepted",
            "selection": {
                "primary": True,
                "claim_ids": ["claim"],
                "relations": [],
            },
        },
        {
            "key": "rejected_high_score",
            "semantic_score": 0.99,
            "admission": "rejected",
            "selection": {
                "primary": True,
                "claim_ids": ["claim"],
                "relations": [],
            },
        },
    ]
    result = select_context(candidates)
    assert result.selected_keys == ("accepted",)
    assert "rejected_high_score" in result.excluded_keys
