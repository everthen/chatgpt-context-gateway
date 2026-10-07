from context_gateway.benchmark.semantic_assessor import (
    blind_candidates,
    build_semantic_assessment_prompt,
)
from context_gateway.benchmark.semantic_model_adapter import (
    OpenAICompatibleSemanticAssessor,
    SemanticModelConfig,
)


def request():
    candidates = blind_candidates(
        [
            {
                "excerpt": "The production region is Singapore.",
                "provider": "chatgpt",
                "account_id": "main",
                "id": "c1",
                "message_id": "m1",
            }
        ]
    )
    return build_semantic_assessment_prompt("production region", candidates)


def test_endpoint_resolution():
    assessor = OpenAICompatibleSemanticAssessor(
        SemanticModelConfig(
            base_url="http://127.0.0.1:20127/api",
            api_key=None,
            model="test-model",
        )
    )
    assert assessor._endpoint() == (
        "http://127.0.0.1:20127/api/v1/chat/completions"
    )


def test_v1_base_endpoint_resolution():
    assessor = OpenAICompatibleSemanticAssessor(
        SemanticModelConfig(
            base_url="https://example.test/v1",
            api_key=None,
            model="test-model",
        )
    )
    assert assessor._endpoint() == "https://example.test/v1/chat/completions"


def test_payload_is_deterministic_and_contains_no_gold_labels():
    req = request()
    assessor = OpenAICompatibleSemanticAssessor(
        SemanticModelConfig(
            base_url="https://example.test",
            api_key=None,
            model="model-x",
        )
    )
    payload = assessor.build_payload(req)
    assert payload["model"] == "model-x"
    assert payload["temperature"] == 0.0
    assert payload["stream"] is False
    assert req.prompt_hash


def test_env_config_fails_closed_when_missing(monkeypatch):
    monkeypatch.delenv("UCG_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("UCG_SEMANTIC_MODEL", raising=False)

    try:
        SemanticModelConfig.from_env()
    except RuntimeError as exc:
        assert "UCG_MODEL_BASE_URL" in str(exc)
    else:
        raise AssertionError("expected missing config to fail")
