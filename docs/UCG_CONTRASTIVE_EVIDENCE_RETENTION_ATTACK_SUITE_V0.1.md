# UCG Contrastive Evidence Retention Attack Suite v0.1

## Decision target

This suite attacks the next UCG seam identified by the cross-answer-model validation:

**contrastive evidence retention vs over-pruning.**

The target is not to maximize context size. The target is:

> retain the minimum sufficient context required for safe downstream reasoning, including evidence whose primary value is contrastive rather than directly answer-bearing.

## Why a separate attack suite

The prior answer-quality benchmark exposed four different failure classes:

| Case | Observed failure | Owner |
|---|---|---|
| NS-04 | conflict evidence pruned | selection |
| XP-02 | provider contrast pruned | selection |
| XP-04 | wrong-account contrast pruned | selection |
| TU-04 | semantic admission produced empty bundle | admission |

These are deliberately separated. A selector cannot repair evidence that never survives admission.

## Attack model

Every candidate carries both a semantic score and a semantic role.

The core attack property is that required contrastive items have a **lower relevance score than an optional distractor**. A relevance-only top-k selector should therefore fail.

### Cases

- **NS-04 — goal conflict:** current support + earlier conflicting goal must both survive.
- **XP-02 — provider contrast:** both provider evidence and the rejected alternative must survive.
- **XP-04 — account isolation:** valid-account evidence and wrong-account evidence must both survive; provenance makes the second item useful rejection context, not authority.
- **TU-04 — admission failure:** an empty admission result is attributed to semantic admission, not selection.

## Attack vectors

| Vector | What it simulates | Expected |
|---|---|---|
| gold_only | aggressive “gold-only” pruning | FAIL on NS-04 / XP-02 / XP-04 |
| score_greedy_2 | semantic top-k without contrastive awareness | FAIL on required contrastive retention |
| all_admitted | admission without selective context construction | retains contrastive evidence but leaks noise |
| contrastive_aware | minimal-sufficient selector | PASS |
| empty_admission_tu04 | upstream semantic-admission failure | UPSTREAM_ADMISSION_FAILURE |

## Metrics

The benchmark reports:

- required_recall
- contrastive_retention
- distractor_rejection
- selected_required_precision
- explicit failure_owner (selection vs admission)

A selector fails a case when it drops any declared minimal-sufficient key or retains any declared must-drop key.

## Falsification criterion

The important falsification is not “can a model include the extra item?”

It is:

> Can a selector preserve required contrastive evidence when that evidence is semantically weaker than an optional distractor, while still rejecting unrelated noise?

A passing implementation therefore needs to beat score_greedy_2 without degenerating into all_admitted.

## Deterministic validation result

The harness self-test passed with 6/6 tests.

On the synthetic suite:

| Vector | Pass rate | Required recall | Contrastive retention | Distractor rejection |
|---|---:|---:|---:|---:|
| gold_only | 0.25 | 0.6667 | 0.25 | 1.00 |
| score_greedy_2 | 0.25 | 0.6667 | 0.25 | 0.50 |
| all_admitted | 0.25 | 1.00 | 1.00 | 0.25 |
| contrastive_aware | 1.00 | 1.00 | 1.00 | 1.00 |

TU-04 with an empty admission is explicitly classified as UPSTREAM_ADMISSION_FAILURE and is not selection-evaluable.

## Scope and non-claims

This fixture is intentionally deterministic and synthetic at the selection layer. It is **not** a replacement for the frozen seed_v0.1 answer-quality experiment.

The contrastive_aware vector represents the intended minimal-sufficient target; it is not evidence that the production selector already implements that behavior.

The next integration step is to feed real ContextBundle candidate/admission outputs from UCG into the same evaluator, preserving case IDs and provenance fields, then rerun downstream answer-quality evaluation with the selected bundles.

## Decision

**PASS — benchmark harness self-test.**

**NOT CORE GATE.**

This branch establishes the falsification and attribution contract for the next UCG selection seam.


## Reference selector result

The deterministic reference selector now consumes the explicit semantic selection signals in the fixture:

- coverage_mode=best for winner-takes-best claims;
- coverage_mode=all for complementary evidence groups;
- required epistemic relations for contrast/boundary closure;
- optional-noise markers for rejection.

Against the four-case synthetic suite, the reference selector achieved:

| Metric | Result |
|---|---:|
| Pass rate | **1.00** |
| Required recall | **1.00** |
| Contrastive retention | **1.00** |
| Distractor rejection | **1.00** |

The same branch passes 18 automated tests covering the attack suite, observed Sonnet regressions, and selector semantics.

This is a **reference-policy result**, not a claim that the production UCG selector is already correct. The production integration seam remains:

retrieval -> semantic assessment/admission -> reference selector -> ContextBundle -> downstream answer evaluation.
