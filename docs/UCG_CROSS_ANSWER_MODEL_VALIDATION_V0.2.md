# UCG Cross-Answer-Model Validation v0.2

## Experiment

- Experiment ID: `UCG-EVAL-AQ-SONNET-20261007-v0.2`
- Repository: `everthen/chatgpt-context-gateway`
- Branch: `experiment/evidence-admission-v0.1`
- Dataset: `seed_v0.1`
- Dataset SHA-256: `977d081d4b0221d89c04bcd6ebe513c23304bbb2e94973b4fb9dbf25c5c34141`
- Answer model: `ag/claude-sonnet-4-6`
- Judge model: `ag/gemini-3.8-flash`
- Temperature: 0
- Cases: 16
- Arms: Native-only, Oracle gold-admission, UCG Gemini-bundle, UCG Sonnet-bundle, UCG Opus-bundle

The frozen ContextBundles were identical to the prior answer-quality experiment. Only the fixed answer model changed.

## Result

| Arm | Task completion | Claim coverage | Factual correctness | Groundedness | Mean answer latency |
|---|---:|---:|---:|---:|---:|
| Native-only | 0.0000 | 0.0000 | 1.0000 | 1.0000 | 3.7937s |
| Oracle gold-admission | 0.9406 | 0.9688 | 0.9062 | 0.9062 | 2.9728s |
| UCG Gemini-bundle | 0.9859 | 1.0000 | 0.9688 | 0.9688 | 3.1952s |
| UCG Sonnet-bundle | 0.9062 | 0.9062 | 0.9688 | 0.9688 | 3.3388s |
| UCG Opus-bundle | **1.0000** | 1.0000 | 1.0000 | 1.0000 | 3.3666s |

### Family results

| Family | Native-only | Oracle | UCG Gemini | UCG Sonnet | UCG Opus |
|---|---:|---:|---:|---:|---:|
| long_session | 0.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| new_session | 0.0000 | 0.9437 | 1.0000 | 0.9437 | 1.0000 |
| cross_provider | 0.0000 | 0.8187 | 0.9437 | 0.9313 | 1.0000 |
| temporal_update | 0.0000 | 1.0000 | 1.0000 | 0.7500 | 1.0000 |

Bundle mean sizes from the earlier deterministic simulation:

- Oracle: 1.6875
- UCG Gemini: 1.625
- UCG Sonnet: 1.9333
- UCG Opus: 2.0625

## Key findings

### 1. UCG benefit generalizes beyond Gemini as the answer model

With Sonnet as the fixed answer model, every evidence-bearing arm materially outperformed Native-only. The strongest arm was UCG Opus-bundle at 1.0000 task completion, followed by UCG Gemini-bundle at 0.9859.

This rules out the weaker hypothesis that the prior result was merely Gemini answer-model compatibility.

### 2. The strongest bundle is not necessarily the smallest bundle

Opus-bundle is largest on the prior bundle simulation, yet produces the best downstream result in this Sonnet-answer run.

So the optimization target is not minimum bundle size. It is **minimum sufficient context under downstream usefulness**.

### 3. “Gold-admission Oracle” is not a downstream-optimal oracle

Oracle gold-admission scored 0.9406, below UCG Gemini 0.9859 and UCG Opus 1.0000.

This is not evidence that UCG “beats a perfect oracle.” The Oracle arm admits every evidence item marked non-reject by the semantic gold taxonomy, which can include distractors, complementary context, and unresolved conflict. It is therefore an **admission reference**, not a downstream-optimal context selector.

This is an important architecture finding: **selection/worthiness remains useful even when admission labels are perfect**.

### 4. New selective-admission seams

- **NS-04:** Sonnet-bundle only retained `ns04.gold` and scored 0.775, while Opus/Gemini bundles retained additional conflict context and scored 1.0. This suggests over-aggressive pruning can remove context needed to reason about conflicting goals.
- **XP-02:** Gemini-bundle scored 0.775 because it omitted `xp02.dist`; Opus/Sonnet bundles included the distractor and scored 1.0. This is a cross-provider design case where the “distractor” is useful for contrastive reasoning.
- **XP-04:** Sonnet-bundle retained only `xp04.gold` and scored 0.725; Opus/Gemini/Oracle retained both the valid and wrong-account evidence and scored 1.0. This is a strong account-isolation / contrastive-evidence seam.
- **TU-04:** Sonnet semantic admission produced an empty bundle and scored 0.0. The answer model abstained correctly; the failure is upstream admission.

### 5. XP-03 is no longer a downstream failure for Sonnet

Unlike the earlier Gemini-answer run, Sonnet with the evidence-bearing bundles handled XP-03 at full task completion. This shows that some apparent “context conflict” failures are answer-model dependent.

## Important comparison rule

Do **not** compare absolute task-completion scores from this run directly to the earlier Gemini-answer run because the judge model changed.

Within this run, arm ranking and deltas are valid. Across runs, the stronger conclusion is qualitative:

> The benefit of UCG evidence bundles persists when the answer model changes from Gemini Flash to Claude Sonnet.

## Decision

**PASS — cross-answer-model validation seam.**

**NOT CORE GATE.**

## Next step

Expand P1/P2, add independent human audit, and specifically attack:

1. contrastive evidence retention vs over-pruning;
2. account-isolation cases;
3. temporal/latest-decision cases;
4. selective bundle construction against a larger gold set.

## Traceability

- Branch head used for experiment setup: `5ab48d1e7c3febebeecc66e469f217fa5a677d9f`
- Router runtime fix: `c477314d`
- Raw Sonnet answer artifact SHA-256: `4ebcdb6eeba5dae86d5440c3f5fa2fbd8f458f56543157e00851276bac0bd24c`
- Raw Sonnet judge artifact SHA-256: `1d1bdd270723323fec391388b1046da798e010e4c6a95921a53cb6fe10f66ceb`
- Full Sonnet result SHA-256: `c801b2a8d4c5bf278e9afca82c7a25ba840dd7ce6bda9ccf76bc0ef6385049d3`
- Runtime note: temporary dev-only benchmark route; no UCG production source change.
