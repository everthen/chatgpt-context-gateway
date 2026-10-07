# UCG Real Selection → Lane → Answer-Quality Gate v0.1

## Scope

This gate validates the live integration:

```text
real semantic assessment
  ↓
real selection assessment
  ↓
canonical selection protocol
  ↓
lane materialization
  ↓
serialized ContextBundle
  ↓
relation-aware answer consumer
  ↓
broader answer-quality evaluation
```

It is a benchmark/contract integration gate. The production retrieval path remains untouched.

## Source models

- Semantic assessment: `ag/claude-sonnet-4-6`
- Selection assessment: `ag/gemini-3.8-flash`
- Answer model: `ag/gemini-3.8-flash`
- Blind judge: `ag/claude-sonnet-4-6`
- Transport: live 9Router OpenAI-compatible `/v1/chat/completions`

## Evaluability

The seed corpus contains 16 cases.

15 cases had usable Sonnet semantic assessments.

TU-04 remained an upstream semantic parse/runtime failure and was not fabricated into a selection result.

## Real selection materialization

Initial live selection assessment completed for all 15 evaluable cases.

Two cases exposed protocol seams:

### XP-02

The selection model emitted:

```text
required_complement
```

This is now a canonical relation type. The adapter also normalizes the observed alias:

```text
complementary → required_complement
```

Complementary provider evidence maps to `answer_support`, not `answer_contrast`.

### XP-03

The selection model emitted:

```text
complementary
```

The protocol adapter normalizes it to `required_complement`.

### Fail-closed shape validation

A later XP-04 probe emitted a non-canonical shape using `selected_candidates[]` instead of `selected_candidate_ids[]`.

The adapter now rejects that response rather than silently materializing an empty selection.

This is a security/property-preservation requirement: malformed selection output must never become an apparently valid empty ContextBundle.

## Lane materialization

Every serialized bundle uses:

```text
ContextBundle
├── answer_context[]
├── control_context[]
└── epistemic_relations[]
```

Lane rules:

- `answer_support` → positive answer authority
- `answer_contrast` → answer-visible alternative/rejected position
- `control_boundary` → retained control evidence, not answer-visible
- `control_conflict` → control-only conflict
- `control_state` → control-only state contrast
- `control_rejection` → control-only rejection

The materializer converts candidate-ID relations into evidence-key relations.

## XP-04 boundary seam

The generic selection pass initially chose only:

```text
C1 → xp04.gold
```

That was insufficient for the account-isolation boundary.

A refined real selection assessment retained:

```text
C1 → xp04.gold
C2 → xp04.dist

C1 --required_boundary_contrast--> C2
```

Materialized result:

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
```

The relation now carries deterministic semantic guidance:

```text
do not merge target evidence into the source scope;
answer from the source scope only
```

This is semantic control-plane metadata, not evidence text and not a citation.

## Broader answer-quality gate

15 evaluable cases were run through the lane-aware consumer.

Results:

| Metric | Result |
|---|---:|
| Answer generations | 15/15 |
| Invalid citations | 0 |
| Blind judges | 15/15 |
| Lane-aware mean weighted score | **1.0000** |
| Oracle mean weighted score | **0.9368** |

Weighted score:

```text
0.25*claim_coverage
+ 0.40*factual_correctness
+ 0.25*groundedness
+ 0.10*abstention_correctness
```

The lane-aware judge contract treats epistemic relations as deterministic semantic facts that may guide interpretation, while control raw text remains non-authoritative and non-citable.

Relation-bearing cases that were rechecked after the semantic-guidance change:

- LS-02 — required contrast
- XP-02 — required complement + account boundary
- XP-03 — required complement
- XP-04 — required account boundary

All four remained fully correct under the relation-aware downstream contract.

## Security result

The explicit control-to-answer leakage attack still fails closed.

A tampered bundle that puts the same control item into both lanes is rejected with:

```text
evidence cannot inhabit both lanes
```

No invalid citation to control evidence was observed in the broader suite.

## Important remaining seam

NS-04 remains non-discriminative under the current Gemini answer prompt.

The real selector retained only its direct anchor, while the answer still scored correctly. This does not prove that contrastive retention is unnecessary; it means the current answer task does not expose the value of that contrast.

The contrastive attack suite remains the appropriate test for that structural property.

## Decision

**PASS for the real-selection → lane-materializer → serialized-ContextBundle → relation-aware broader answer-quality gate.**

The gate does not authorize production wiring yet.

Before production integration, the remaining work is:

1. connect the real selection-assessment result into the production admission/selection path;
2. persist the serialized lane contract without flattening lanes;
3. keep relation semantic guidance separate from evidence text and citations;
4. rerun the full production-shaped admission → selection → lane → answer path;
5. preserve TU-04 as an upstream-failure ownership test.

