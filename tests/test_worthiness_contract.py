from context_gateway.benchmark.worthiness import EvidenceAssessment, apply_assessment


def assessment(**overrides):
    data = {
        "evidence_id": "e1",
        "evidence_hash": "hash-1",
        "task_fit": "direct",
        "worthiness_role": "direct_support",
        "claim_ids": ("claim-1",),
        "temporal_state": "current",
        "assessment_method": "rule",
        "assessor_version": "v0.1",
        "confidence": 0.9,
    }
    data.update(overrides)
    return EvidenceAssessment(**data)


def test_assessment_binds_to_exact_evidence():
    evidence = {
        "evidence_id": "e1",
        "raw_hash": "hash-1",
    }
    out = apply_assessment(evidence, assessment())
    assert out["claim_ids"] == ["claim-1"]
    assert out["worthiness_assessment"]["evidence_hash"] == "hash-1"


def test_mismatched_evidence_id_is_rejected():
    evidence = {"evidence_id": "other", "raw_hash": "hash-1"}
    try:
        apply_assessment(evidence, assessment())
    except ValueError as exc:
        assert "evidence_id" in str(exc)
    else:
        raise AssertionError("expected evidence_id mismatch")


def test_mismatched_evidence_hash_is_rejected():
    evidence = {"evidence_id": "e1", "raw_hash": "hash-2"}
    try:
        apply_assessment(evidence, assessment())
    except ValueError as exc:
        assert "evidence_hash" in str(exc)
    else:
        raise AssertionError("expected evidence hash mismatch")


def test_invalid_confidence_is_rejected():
    try:
        assessment(confidence=1.5).validate()
    except ValueError as exc:
        assert "confidence" in str(exc)
    else:
        raise AssertionError("expected confidence validation failure")


def test_proposed_state_is_valid_but_not_current_by_default():
    a = assessment(
        temporal_state="proposed",
        task_fit="contextual",
        worthiness_role="contextual",
    )
    a.validate()
