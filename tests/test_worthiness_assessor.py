from context_gateway.benchmark.worthiness_assessor import (
    RuleWorthinessAssessor,
    UnavailableWorthinessAssessor,
)


def test_rule_assessor_is_explicit_lower_bound():
    assessor = RuleWorthinessAssessor()
    evidence = {
        "evidence_id": "e1",
        "raw_hash": "h1",
        "excerpt": "The production region is Singapore.",
        "provider": "chatgpt",
        "account_id": "main",
        "id": "c1",
        "message_id": "m1",
        "snapshot_id": "s1",
        "raw_path": "raw",
    }

    class Case:
        query = "production region Singapore"

    result = assessor.assess(evidence=evidence, case=Case())
    assert result.assessment_method == "rule"
    assert result.assessor_version == "lexical-v0.1"


def test_unavailable_model_assessor_never_fakes_results():
    assessor = UnavailableWorthinessAssessor()

    class Case:
        query = "anything"

    try:
        assessor.assess(
            evidence={"evidence_id": "e1", "raw_hash": "h1"},
            case=Case(),
        )
    except RuntimeError as exc:
        assert "unavailable" in str(exc)
    else:
        raise AssertionError("expected unavailable assessor to fail closed")
