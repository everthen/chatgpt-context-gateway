# UCG ContextBundle Lanes v0.1

## Problem

A flat evidence list conflates two different semantics:

- evidence that may be used and cited by the answer model;
- evidence retained to enforce or audit a boundary, rejection, contradiction, or other selection constraint.

The fresh XP-04 downstream gate demonstrated this seam. Wrong-account evidence is epistemically important for isolation, but exposing it as ordinary answer evidence allows a downstream model to cite it as positive authority.

## Proposed contract

```text
ContextBundle
├── answer_context[]
├── control_context[]
└── epistemic_relations[]
```

### answer_context

Evidence the answer model is permitted to use as substantive support.

Each item retains:

- `key`
- `text`
- `provenance`
- `role`
- `lane`
- `answer_visible`
- `citation_eligible`

### control_context

Evidence retained for selection, rejection, boundary, conflict, state, audit, or governance semantics.

Control evidence is never ordinary positive answer authority:

```text
answer_visible = false
citation_eligible = false
```

Examples:

- wrong-account evidence;
- security-boundary evidence;
- rejected or superseded state;
- conflict/rejection evidence that must remain available for governance or audit.

The answer consumer may receive control metadata, but the raw control text must not silently become citable answer evidence.

### epistemic_relations

Deterministic relations connecting retained evidence across lanes.

Examples:

```text
xp04.gold
  --required_boundary_contrast-->
xp04.dist
```

```text
xp02.openai
  --required_contrast-->
xp02.dist
```

## Role and lane taxonomy

Minimum supported lanes:

- `answer_support`
- `answer_contrast`
- `control_boundary`
- `control_conflict`
- `control_state`
- `control_rejection`

Default relation mapping:

| Selection relation | Target lane | Answer-visible |
|---|---|---|
| `required_contrast` | `answer_contrast` | yes |
| `required_complement` | `answer_support` | yes |
| `required_boundary_contrast` | `control_boundary` | no |
| `required_conflict` | `control_conflict` | no |
| `required_state_contrast` | `control_state` | no |

`answer_contrast` is answer-visible because the contrast itself may be part of the reasoning, but downstream policy must treat it as a rejected/alternative position, not as positive support.

Each `epistemic_relations[]` record also carries deterministic `answer_guidance`. This is semantic control-plane metadata, not evidence text and not a citation. For `required_boundary_contrast`, the guidance states: `for the requested source scope, explicitly state that target evidence must not be merged into the source scope; answer from the source scope only`.

This taxonomy is downstream of semantic assessment:

- semantic assessment describes what evidence is;
- selection assessment describes why evidence must be retained and which lane it belongs to;
- deterministic selection enforces the plan;
- the lane materializer produces the governed downstream view.

## Fail-closed invariants

The lane materializer rejects:

- unknown selected evidence keys;
- missing required relation targets;
- evidence occupying both lanes;
- control evidence marked answer-visible;
- control evidence marked citation-eligible;
- supporting evidence explicitly demoted into a control lane;
- relations pointing outside the materialized bundle.

Core invariant:

> **Control evidence MUST NOT silently become positive answer authority.**

For account isolation:

```text
answer_context:
  xp04.gold
  lane = answer_support
  answer_visible = true
  citation_eligible = true

control_context:
  xp04.dist
  lane = control_boundary
  answer_visible = false
  citation_eligible = false

epistemic_relations:
  xp04.gold
    --required_boundary_contrast-->
  xp04.dist
```

## Downstream answer policy

The lane-aware answer consumer SHOULD enforce:

1. Every factual claim is grounded in `answer_context`.
2. `answer_support` may support positive claims.
3. `answer_contrast` may be cited only when explicitly describing the rejected/alternative position.
4. `control_context` is not citable and its raw text is not answer-visible.
5. The direction of the user query must be preserved.

For XP-04 specifically, the answer must address the requested direction: evidence from another account must not be merged into the main account's retrieval. The answer may ground that isolation claim in valid main-account evidence without exposing the secondary-account text.

## Gate result — 2026-10-07

Fresh downstream gate:

- answer model: `ag/gemini-3.8-flash`
- blind judge: `ag/claude-sonnet-4-6`
- live endpoint: 9Router OpenAI-compatible `/v1/chat/completions`
- cases: XP-02 and XP-04

Contract tests: **6/6 PASS** (including an explicit control-to-answer leak attack).

Live answer generation: **2/2 PASS**.

Blind judge:

| Case | Claim coverage | Factual correctness | Groundedness | Abstention | Weighted |
|---|---:|---:|---:|---:|---:|
| XP-02 | 1.0 | 1.0 | 1.0 | 1.0 | 1.000 |
| XP-04 | 1.0 | 1.0 | 1.0 | 1.0 | 1.000 |

Observed behavior:

- XP-02 retained `xp02.dist` as `answer_contrast` and used it only to describe the rejected provider-specific alternative.
- XP-04 retained `xp04.dist` as `control_boundary`; its text was not answer-visible and it was not cited.
- XP-04 preserved the requested contamination direction and grounded the isolation claim in `xp04.gold`.
- No invalid citation to control evidence was observed.
- A tampered bundle placing `xp04.dist` in both lanes was rejected fail-closed with `evidence cannot inhabit both lanes`.

This passes the lane-aware downstream gate.

This remains a **benchmark/contract layer**. No production retrieval path is wired to it yet.

## Next gate

Before production wiring:

1. feed real selection-assessment output into the lane materializer;
2. preserve lane assignment through serialized `ContextBundle`;
3. add an explicit control-to-answer leakage attack;
4. rerun the broader answer-quality suite, not only XP-02/XP-04.

Do not mark lane-aware context as production-complete until those checks pass.