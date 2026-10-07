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

Evidence that the answer model is permitted to use as substantive support.

Each item SHOULD retain:

- evidence key
- text
- provenance
- temporal state
- answer role
- citation eligibility

### control_context

Evidence that is retained for selection, rejection, boundary, conflict, audit, or governance semantics.

Default:

`answer_visible = false`

Examples:

- wrong-account evidence;
- rejected provider-specific alternative;
- superseded state used to explain why it was rejected;
- security boundary evidence.

Control evidence may influence the answer-model instruction layer, but its raw text SHOULD NOT automatically become citable answer evidence.

### epistemic_relations

Deterministic relations connecting the lanes.

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

## Role taxonomy

At minimum:

- `answer_support`
- `answer_contrast`
- `control_boundary`
- `control_conflict`
- `control_state`
- `control_rejection`

This taxonomy is downstream of semantic assessment.

Semantic assessment describes what evidence is.

Selection assessment describes why the evidence must be retained and which lane it belongs to.

Deterministic selection enforces the resulting plan.

## Security invariant

Control evidence MUST NOT silently become positive answer authority.

For account isolation:

```text
answer_context:
  xp04.gold

control_context:
  xp04.dist

answer model instruction:
  "Secondary-account evidence is out of scope and must not be used as support."
```

The answer model can still be told that an excluded boundary exists, without receiving the excluded text as ordinary answer evidence.

## Why this is preferable

This design preserves the epistemic value of contrastive evidence without forcing every downstream consumer to treat all retained evidence as equally citable.

It also creates a clean place for future policy:

- retrieval may keep broad evidence;
- admission may decide admissibility;
- selection may decide retention and lane;
- answer generation receives an explicitly governed view.

## Next test

Run XP-02 and XP-04 with the same answer and judge models comparing:

1. flat bundle;
2. lane-aware bundle.

Success criterion:

- XP-02 retains the contrast needed for provider-neutrality reasoning;
- XP-04 retains boundary evidence in control_context;
- answer_context excludes wrong-account evidence from positive citation;
- no regression in groundedness or claim coverage.

This is a design/test seam only. Do not treat it as production implementation until the lane-aware downstream gate passes.
