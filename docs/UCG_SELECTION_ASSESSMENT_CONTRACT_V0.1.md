# UCG Selection Assessment Contract v0.1

## Purpose

This artifact defines the selection-assessment seam between semantic assessment/admission and the deterministic context selector.

Pipeline:

`retrieval -> semantic assessment/admission -> selection assessment -> deterministic selection policy -> ContextBundle -> answer model`

The selection assessor MUST NOT answer the user task. It emits an auditable epistemic selection plan.

## Core invariant

Semantic relevance is not equivalent to contextual worthiness.

A candidate can be low-relevance, contextual, contradictory, or even semantically classified as `none`, yet still be required to justify:

- a rejected alternative;
- an unresolved conflict;
- a state transition;
- an identity/account/provider boundary.

The selector's optimization target remains:

> minimum sufficient context under downstream usefulness

not:

> highest semantic score

and not:

> smallest bundle regardless of epistemic loss.

## Canonical output contract

The model-facing selection assessment SHOULD emit JSON with:

```json
{
  "selected_candidate_ids": ["C1"],
  "relations": [
    {
      "source": "C1",
      "target": "C2",
      "type": "required_contrast",
      "when_selected": true
    }
  ],
  "coverage_groups": [
    {
      "group_id": "g1",
      "candidate_ids": ["C1", "C2"],
      "mode": "all"
    }
  ],
  "excluded_candidate_ids": ["C3"],
  "confidence": 0.0
}
```

Allowed relation types:

- `required_contrast`
- `required_complement`
- `required_boundary_contrast`
- `required_conflict`
- `required_state_contrast`

The deterministic selector remains authoritative. The LLM supplies epistemic structure; deterministic policy enforces closure, budget, admissibility, and auditability.

## Selection rules

### 1. Unresolved conflict

Retain the current/direct anchor plus the smallest contrastive subset needed to expose the competing interpretation.

Do not automatically retain every member of the same conflict group.

### 2. Complementary provider evidence

A shared redundancy group does not prove substitutability.

Candidates must remain jointly selectable when they provide materially different claims or distinct provider perspectives needed for the task. Provider-neutral architecture and provider-portability evidence are a canonical example.

### 3. Identity/account boundaries

When the task concerns isolation, ownership, scope, or wrong-account evidence, same-topic evidence from another account can be required boundary evidence even when semantic `task_fit` is `none`.

The boundary candidate should be represented as an explicit `required_boundary_contrast`, not silently promoted to an answer claim.

### 4. Noise

Unrelated evidence must not be retained merely because it has a high semantic score.

### 5. Auditability

Every selected non-anchor candidate must be justified by either:

- a coverage group, or
- an explicit relation from a selected anchor.

### 6. Upstream failure ownership

A malformed or missing semantic assessment is not a selection failure and must not be "repaired" by the selector.

## Empirical probe

Source semantic model:

`ag/claude-sonnet-4-6`

Selection model:

`ag/gemini-3.8-flash`

The probe used real Sonnet semantic outputs from the existing `seed_v0.1` corpus, not synthetic gold labels in the model prompt.

### Pass 1

| Case | Selection result | Finding |
|---|---|---|
| NS-04 | C1+C2+C3 | over-selected all conflict members |
| XP-02 | C1+C3 | dropped complementary provider/portability evidence C2 |
| XP-04 | C1 | dropped wrong-account boundary evidence C2 |
| TU-04 | not evaluated | upstream Sonnet semantic parse/runtime failure |

### Refined contract probe

The selection contract was strengthened with generic rules for conflict minimization, complementary coverage, and account boundaries.

Observed successful repairs:

- XP-02 -> C1+C2+C3, with explicit contrast/conflict relations.
- XP-04 -> C1+C2, with explicit `required_boundary_contrast`.

NS-04 was not counted as a pass because the corresponding refined call did not produce a confirmed result in the observed run.

## Protocol normalization requirement

LLM output was observed using aliases such as `from`/`to` and `from_id`/`to_id`, while the canonical contract uses `source`/`target`.

This is a protocol-adapter concern, not a selector concern.

The adapter MUST normalize only known aliases into the canonical schema or reject the response as non-compliant. Observed aliases `complementary` and `required_complement` normalize to canonical `required_complement`. Production code MUST NOT silently accept arbitrary field variants.

## Decision

**PARTIAL PASS — selection-assessment seam is empirically promising, NOT a core gate yet.**

Confirmed:

- real selection output can contain relation vocabulary that needs a narrow protocol normalization layer;
- complementary provider evidence can be represented explicitly without misclassifying it as contradiction;
- the semantic output can be insufficient for deterministic selection;
- an explicit selection contract can recover complementary-provider evidence;
- an explicit selection contract can recover wrong-account boundary evidence;
- deterministic selection remains the correct enforcement layer.

Not yet proven:

- robust minimum sufficient selection for all contrastive seams, especially NS-04;
- downstream answer-quality improvement after applying the LLM selection plan;
- production integration safety.

## Next gate

Run:

`semantic admission -> selection assessment -> deterministic selector -> ContextBundle -> downstream answer-quality`

on the observed NS-04 / XP-02 / XP-04 cases, then compare against the existing native/UCG bundles.

Do not wire the selector into the production retrieval path until that downstream gate passes.


## Fail-closed protocol shape

The protocol adapter rejects selection output that omits `selected_candidate_ids` or supplies it in a non-array shape. It must not silently coerce a non-canonical selection shape into an empty selection.
