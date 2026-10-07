# UCG Answer Quality Cross-Model Validation v0.1

## Objective

Test whether the downstream benefit of UCG ContextBundles survives when the fixed answer model changes.

The frozen 16-case seed was reused. Bundle contents were not regenerated between runs.

## Run A — Gemini answer model

- Answer model: `ag/gemini-3.8-flash`
- Judge: `ag/claude-sonnet-4-6`
- Temperature: 0
- 16 cases × 5 arms = 80 answer calls
- Claim-gated task-completion metric:
  - 0 when judge claim coverage = 0
  - otherwise `0.55*claim_coverage + 0.30*factual_correctness + 0.15*groundedness`

| Arm | Task completion |
|---|---:|
| Native-only | 0.0000 |
| Oracle | 0.9734 |
| UCG Gemini-bundle | 0.9734 |
| UCG Sonnet-bundle | 0.8938 |
| UCG Opus-bundle | 0.9734 |

## Run B — Sonnet answer model

- Answer model: `ag/claude-sonnet-4-6`
- Judge: `ag/gemini-3.8-flash`
- Temperature: 0
- 16 cases × 5 arms = 80 answer calls
- Same frozen bundle inputs as Run A

| Arm | Task completion | Δ vs Native-only |
|---|---:|---:|
| Native-only | 0.0000 | — |
| Oracle | 0.9406 | +0.9406 |
| UCG Gemini-bundle | 0.9859 | +0.9859 |
| UCG Sonnet-bundle | 0.9062 | +0.9062 |
| UCG Opus-bundle | **1.0000** | **+1.0000** |

All 80 Sonnet-answer calls completed successfully. Citation validity was 100% across arms.

## Findings

### 1. The UCG downstream benefit survives an answer-model change

Both fixed answer models show a large separation between native-only and evidence-bearing arms.

This is the important result: the improvement is not dependent on using Gemini as both the semantic assessor family and the answer model.

### 2. Opus and Gemini semantic bundles generalize best

- With Gemini answering: Gemini and Opus bundles tied at 0.9734.
- With Sonnet answering: Opus reached 1.0000 and Gemini 0.9859.

The strongest bundle family is therefore not simply “same model as answerer.”

### 3. Sonnet semantic admission remains the weak seam

Sonnet-bundle:
- Gemini answer: 0.8938
- Sonnet answer: 0.9062

The main recurring failure is TU-04, where the frozen Sonnet semantic assessor produced an empty bundle. The answer model then cannot recover the required current decision from context that was never admitted.

XP-04 is a secondary seam: Sonnet admission selected the gold isolation statement but omitted the complementary secondary-account evidence.

### 4. Selective UCG bundles can beat the gold-admission bundle downstream

The Oracle arm here means the deterministic gold-admission set, not a perfect answer-quality oracle.

It can contain conflict/contextual evidence that is allowed by semantic gold but not necessary for the specific answer.

That explains why selective UCG bundles can outperform the Oracle arm downstream:

- Run A: Oracle = 0.9734, UCG Gemini/Opus = 0.9734
- Run B: Oracle = 0.9406, UCG Gemini = 0.9859, UCG Opus = 1.0000

This is not evidence that UCG “beats a perfect oracle.” It is evidence that **admission selectivity itself is part of downstream context quality**.

### 5. Bundle-size tradeoff remains favorable

From the frozen deterministic bundle simulation:

| Bundle | Mean bundle size |
|---|---:|
| Oracle | 1.6875 |
| UCG Gemini | 1.625 |
| UCG Sonnet | 1.9333 |
| UCG Opus | 2.0625 |

Gemini had the smallest UCG bundle while staying at or near the downstream ceiling. Opus used a somewhat larger bundle but produced the best Sonnet-answer result in this seed.

## Caveat: judge-model comparability

Do not compare absolute task-completion numbers across Run A and Run B as though they were measured by the same evaluator:

- Run A judge = Sonnet
- Run B judge = Gemini

The valid comparison within each run is **Native vs Oracle vs each UCG bundle**.

The cross-run conclusion is therefore about **ranking/stability of the UCG effect**, not absolute score equality.

## Decision

**PASS — cross-answer-model validation seam.**

The UCG benefit survives a change from Gemini answering to Sonnet answering.

Still **NOT CORE GATE**.

## Next step

Expand the P1/P2 dataset and add an independent human audit, with targeted adversarial cases for:

1. latest/current decision supersession;
2. account isolation and wrong-account evidence;
3. unresolved design conflicts;
4. empty/over-pruned admission;
5. irrelevant-but-semantically-related evidence.

## Traceability

- Dataset: `seed_v0.1`
- Dataset SHA-256: `977d081d4b0221d89c04bcd6ebe513c23304bbb2e94973b4fb9dbf25c5c34141`
- Branch: `experiment/evidence-admission-v0.1`
- Branch code baseline: `3efee11f2303a46c3818a3490da70c0405407a4c`
- Router runtime fix: `c477314d`
- Sonnet-answer compact result:
  `benchmarks/runs/seed_v0.1/2026-10-07_answer_quality_sonnet_result_v0.2.json`
- Compact result SHA-256: `c801b2a8d4c5bf278e9afca82c7a25ba840dd7ce6bda9ccf76bc0ef6385049d3`
- Raw answer artifact SHA-256: `4ebcdb6eeba5dae86d5440c3f5fa2fbd8f458f56543157e00851276bac0bd24c`
- Raw judge artifact SHA-256: `1d1bdd270723323fec391388b1046da798e010e4c6a95921a53cb6fe10f66ceb`
- Temporary benchmark route: dev-only, removed after run
- Temporary benchmark API key: removed after run
