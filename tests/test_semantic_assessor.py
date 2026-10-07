from context_gateway.benchmark.semantic_assessor import (
    normalize_semantic_response,
    UnavailableSemanticAssessor,
    blind_candidates,
    build_semantic_assessment_prompt,
    parse_semantic_assessment,
)


def items():
    return [
        {
            "evidence_key": "gold-hidden",
            "task_fit": "direct",
            "excerpt": "The production region is Singapore.",
            "provider": "chatgpt",
            "account_id": "main",
            "id": "c1",
            "message_id": "m1",
            "observed_at": 1800000000,
        },
        {
            "evidence_key": "dist-hidden",
            "task_fit": "none",
            "excerpt": "A previous proposal considered Frankfurt.",
            "provider": "chatgpt",
            "account_id": "main",
            "id": "c2",
            "message_id": "m2",
            "observed_at": 1700000000,
        },
    ]


def test_blind_candidates_strip_benchmark_labels():
    candidates = blind_candidates(items())
    assert [c.candidate_id for c in candidates] == ["C1", "C2"]
    assert "gold-hidden" not in candidates[0].as_dict().values()
    assert "task_fit" not in candidates[0].as_dict()


def test_prompt_hash_is_deterministic_and_prompt_is_blind():
    candidates = blind_candidates(items())
    request = build_semantic_assessment_prompt(
        "current production region",
        candidates,
    )
    assert len(request.prompt_hash) == 64
    assert "gold-hidden" not in request.prompt
    assert "dist-hidden" not in request.prompt
    assert "task_fit" in request.prompt
    assert "C1" in request.prompt


def test_semantic_response_parser_requires_complete_coverage():
    candidates = blind_candidates(items())
    request = build_semantic_assessment_prompt("production region", candidates)
    raw = """{
      "assessments": [
        {
          "candidate_id": "C1",
          "task_fit": "direct",
          "worthiness_role": "direct_support",
          "temporal_state": "current",
          "claim_ids": ["claim-1"],
          "conflict_group": null,
          "redundancy_group": null,
          "provenance_complete": true,
          "confidence": 0.9
        },
        {
          "candidate_id": "C2",
          "task_fit": "contextual",
          "worthiness_role": "contextual",
          "temporal_state": "obsolete",
          "claim_ids": ["claim-2"],
          "conflict_group": null,
          "redundancy_group": null,
          "provenance_complete": true,
          "confidence": 0.7
        }
      ]
    }"""
    results = parse_semantic_assessment(request, raw)
    assert len(results) == 2
    assert results[0].candidate_id == "C1"


def test_semantic_response_parser_rejects_unknown_candidate():
    candidates = blind_candidates(items())
    request = build_semantic_assessment_prompt("production region", candidates)
    raw = """{"assessments":[{
      "candidate_id":"C9",
      "task_fit":"direct",
      "worthiness_role":"direct_support",
      "temporal_state":"current",
      "claim_ids":[],
      "conflict_group":null,
      "redundancy_group":null,
      "provenance_complete":true,
      "confidence":0.8
    }]}"""
    try:
        parse_semantic_assessment(request, raw)
    except ValueError as exc:
        assert "unknown candidate_id" in str(exc)
    else:
        raise AssertionError("expected unknown candidate rejection")


def test_unavailable_semantic_assessor_fails_closed():
    try:
        UnavailableSemanticAssessor().assess(
            query="production region",
            candidates=items(),
        )
    except RuntimeError as exc:
        assert "unavailable" in str(exc)
    else:
        raise AssertionError("expected unavailable assessor failure")


def test_normalize_richer_candidate_response():
    candidates = blind_candidates(items())
    request = build_semantic_assessment_prompt("production region", candidates)
    raw = """{
      "candidates": [
        {"candidate_id":"C1","task_fit":"direct","worthiness_role":"direct_support","temporal_state":"current","provenance_complete":true,"confidence":0.9,"assessment":"direct"},
        {"candidate_id":"C2","task_fit":"contextual","worthiness_role":"contextual","temporal_state":"obsolete","provenance_complete":true,"confidence":0.8,"assessment":"historical"}
      ],
      "claim_groupings": []
    }"""
    results, compliant = normalize_semantic_response(raw, request)
    assert not compliant
    assert len(results) == 2
    assert results[0].candidate_id == "C1"
    assert results[1].worthiness_role == "contextual"
