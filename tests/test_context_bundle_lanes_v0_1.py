from benchmarks.context_bundle_lanes_v0_1 import (
    ContextBundleValidationError,
    build_context_bundle,
)


def candidate(key, role, account, relations=None, text=None):
    return {
        "key": key,
        "role": role,
        "text": text or key,
        "admission": "required",
        "provenance": {"account": account},
        "selection": {
            "primary": role == "supporting",
            "relations": relations or [],
        },
    }


def test_xp02_contrast_is_answer_visible_but_not_positive_support():
    candidates = [
        candidate(
            "xp02.openai",
            "supporting",
            "primary",
            [
                {
                    "target": "xp02.dist",
                    "type": "required_contrast",
                    "when_selected": True,
                }
            ],
        ),
        candidate("xp02.claude", "supporting", "primary"),
        candidate("xp02.dist", "contrastive", "primary"),
    ]

    bundle = build_context_bundle(
        candidates,
        ["xp02.openai", "xp02.claude", "xp02.dist"],
    )

    assert {x["key"] for x in bundle.answer_context} == {
        "xp02.openai",
        "xp02.claude",
        "xp02.dist",
    }
    dist = next(x for x in bundle.answer_context if x["key"] == "xp02.dist")
    assert dist["lane"] == "answer_contrast"
    assert dist["citation_eligible"] is True
    assert bundle.control_context == ()


def test_xp04_wrong_account_is_control_only():
    candidates = [
        candidate(
            "xp04.gold",
            "supporting",
            "account-A",
            [
                {
                    "target": "xp04.dist",
                    "type": "required_boundary_contrast",
                    "when_selected": True,
                }
            ],
        ),
        candidate("xp04.dist", "contrastive", "account-B"),
    ]

    bundle = build_context_bundle(candidates, ["xp04.gold", "xp04.dist"])

    assert [x["key"] for x in bundle.answer_context] == ["xp04.gold"]
    assert [x["key"] for x in bundle.control_context] == ["xp04.dist"]
    assert bundle.control_context[0]["answer_visible"] is False
    assert bundle.control_context[0]["citation_eligible"] is False
    assert bundle.epistemic_relations == (
        {
            "from": "xp04.gold",
            "to": "xp04.dist",
            "relation_type": "required_boundary_contrast",
            "answer_guidance": "for the requested source scope, explicitly state that target evidence must not be merged into the source scope; answer from the source scope only",
        },
    )


def test_control_evidence_cannot_be_positive_answer_authority():
    candidates = [
        candidate(
            "gold",
            "supporting",
            "account-A",
            [
                {
                    "target": "wrong",
                    "type": "required_boundary_contrast",
                    "when_selected": True,
                }
            ],
        ),
        candidate("wrong", "contrastive", "account-B"),
    ]
    bundle = build_context_bundle(candidates, ["gold", "wrong"])

    assert all(x["key"] != "wrong" for x in bundle.answer_context)
    assert not any(x["citation_eligible"] for x in bundle.control_context)


def test_required_relation_target_cannot_disappear():
    candidates = [
        candidate(
            "gold",
            "supporting",
            "account-A",
            [
                {
                    "target": "wrong",
                    "type": "required_boundary_contrast",
                    "when_selected": True,
                }
            ],
        ),
        candidate("wrong", "contrastive", "account-B"),
    ]

    try:
        build_context_bundle(candidates, ["gold"])
    except ContextBundleValidationError as exc:
        assert "missing from selected bundle" in str(exc)
    else:
        raise AssertionError("missing required relation target must fail closed")


def test_answer_context_rejects_control_lane_metadata():
    candidates = [
        candidate("gold", "supporting", "account-A"),
    ]
    candidates[0]["selection"]["lane"] = "control_boundary"

    try:
        build_context_bundle(candidates, ["gold"])
    except ContextBundleValidationError as exc:
        assert "supporting evidence cannot" in str(exc)
    else:
        raise AssertionError("supporting evidence cannot silently become control")

from benchmarks.context_bundle_lanes_v0_1 import ContextBundle, validate_context_bundle


def test_control_to_answer_leak_attack_fails_closed():
    candidates = [
        candidate(
            "gold",
            "supporting",
            "account-A",
            [
                {
                    "target": "wrong",
                    "type": "required_boundary_contrast",
                    "when_selected": True,
                }
            ],
        ),
        candidate("wrong", "contrastive", "account-B"),
    ]
    bundle = build_context_bundle(candidates, ["gold", "wrong"])

    leaked = dict(bundle.control_context[0])
    tampered = ContextBundle(
        answer_context=bundle.answer_context + (leaked,),
        control_context=bundle.control_context,
        epistemic_relations=bundle.epistemic_relations,
    )

    try:
        validate_context_bundle(tampered)
    except ContextBundleValidationError as exc:
        assert ("both lanes" in str(exc)) or ("answer-visible" in str(exc))
    else:
        raise AssertionError("control-to-answer leakage must fail closed")

def test_required_boundary_relation_carries_non_citable_guidance():
    candidates = [
        candidate(
            "gold",
            "supporting",
            "account-A",
            [{"target":"wrong","type":"required_boundary_contrast","when_selected":True}],
        ),
        candidate("wrong", "contrastive", "account-B"),
    ]
    bundle = build_context_bundle(candidates, ["gold", "wrong"])
    rel = bundle.epistemic_relations[0]
    assert rel["answer_guidance"] == "for the requested source scope, explicitly state that target evidence must not be merged into the source scope; answer from the source scope only"
    assert all(x["citation_eligible"] is False for x in bundle.control_context)
