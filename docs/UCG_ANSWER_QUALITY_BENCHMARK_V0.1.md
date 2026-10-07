# UCG Answer Quality Benchmark v0.1

## Objective

Measure whether a retrieved ContextBundle improves downstream answer quality, not merely retrieval metrics.

## Frozen setup

- Repository: `everthen/chatgpt-context-gateway`
- Branch: `experiment/evidence-admission-v0.1`
- Code commit at experiment start: `3efee11f2303a46c3818a3490da70c0405407a4c`
- Dataset: `seed_v0.1`
- Dataset SHA-256: `977d081d4b0221d89c04bcd6ebe513c23304bbb2e94973b4fb9dbf25c5c34141`
- Cases: 16
- Answer model: `ag/gemini-3.8-flash`
- Judge model: `ag/claude-sonnet-4-6`
- Temperature: 0
- Answer max output: 256 tokens
- Native-only definition: no UCG evidence injection
- Bundle arms: Native-only, Oracle admission, Gemini semantic bundle, Sonnet semantic bundle, Opus semantic bundle

The same answer model was used for every arm. The judge evaluated each arm without being told which semantic assessor produced its bundle.

## Scoring

Answer quality:

`0.25 * claim_coverage + 0.40 * factual_correctness + 0.25 * groundedness + 0.10 * deterministic_abstention_correctness`

Abstention correctness was made deterministic after the first judge pass: a case is expected to abstain when the frozen minimal-sufficient evidence set is absent; otherwise an answer is expected.

Citation validity is deterministic key membership against the supplied bundle.

## Result

| Arm | Mean answer quality | Δ vs Native-only | Claim coverage | Factual correctness | Groundedness |
|---|---:|---:|---:|---:|---:|
| Native-only | 0.2875 | — | 0.0000 | 0.0000 | 1.0000 |
| Oracle | 0.9797 | +0.6922 | 0.9688 | 0.9688 | 1.0000 |
| UCG Gemini-bundle | 0.9797 | +0.6922 | 0.9688 | 0.9688 | 1.0000 |
| UCG Opus-bundle | 0.9797 | +0.6922 | 0.9688 | 0.9688 | 1.0000 |
| UCG Sonnet-bundle | 0.9250 | +0.6375 | 0.8750 | 0.9062 | 1.0000 |

All 80 answer calls completed successfully (16 cases × 5 arms). All citation keys were valid.

## Findings

### 1. The downstream seam is positive on the frozen seed

Native-only averaged 0.2875. Every evidence-bearing arm materially improved answer quality. Oracle, Gemini-bundle, and Opus-bundle reached 0.9797.

This is the first direct evidence in this benchmark that UCG-style evidence admission can improve end-to-end answer quality rather than only retrieval statistics.

### 2. Gemini semantic admission reached the Oracle ceiling in this run

The Gemini bundle matched Oracle mean answer quality (0.9797).

The earlier deterministic bundle simulation measured:

- Oracle mean bundle size: 1.6875
- Gemini mean bundle size: 1.625
- Gemini semantic noise: 0%

That is a strong seed-level result: the selected Gemini bundle was smaller than Oracle while preserving answer quality.

### 3. Sonnet bundle has a real failure seam

Sonnet-bundle scored 0.925. The clearest failure is TU-04:

> Automatic recall remains a hypothesis until benchmarked against native-only and explicit-trigger UCG.

The frozen Sonnet semantic assessor produced an empty bundle for TU-04, so the answer model correctly abstained. This is a semantic-admission failure, not an answer-model failure.

### 4. XP-03 remains the conflict seam

XP-03 contains both:

- the intended boundary that native memory + UCG can coexist and the model retains final judgment;
- a conflicting draft proposing that the gateway itself make the final decision.

The answer model surfaced the contradiction instead of silently collapsing it. The case scored 0.675 for evidence-bearing arms. That is a useful failure signal: the system preserves provenance/conflict, but the answer-quality evaluator treats unresolved design conflict as partial task satisfaction.

### 5. Cross-provider and temporal cases are the sensitive families

Family-level answer quality:

| Family | Native-only | Oracle | Gemini-bundle | Sonnet-bundle | Opus-bundle |
|---|---:|---:|---:|---:|---:|
| long_session | 0.3000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| new_session | 0.2500 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| cross_provider | 0.2750 | 0.9187 | 0.9187 | 0.8875 | 0.9187 |
| temporal_update | 0.3250 | 1.0000 | 1.0000 | 0.8125 | 1.0000 |

The Sonnet bundle’s temporal drop is driven by TU-04; its cross-provider drop includes XP-03/XP-04 semantics.

## Caveats

This is a 16-case diagnostic seed, not a CORE GATE.

Native-only here means no UCG evidence injection. It does not instrument hidden provider-native memory, so it is not a perfect measurement of production native-memory behavior.

The answer model was fixed to Gemini 3.8 Flash. This makes the arm comparison fair, but Gemini-bundle has potential model-family compatibility that must be tested with another fixed answer model.

The judge is one LLM evaluator (Sonnet 4.6), not an independent human panel. Human audit is still required for high-impact/adversarial disagreements.

## Decision

**PASS — diagnostic answer-quality seam.**

Do not promote this to the UCG CORE GATE yet.

## Next step

Repeat the exact frozen bundles with a different fixed answer model, then expand the P1/P2 evaluation harness and add human audit. The key decision remains whether UCG improves relevant recall with less noise than native context while preserving downstream correctness at acceptable token/latency cost.

## Traceability

- Result artifact: `benchmarks/runs/seed_v0.1/2026-10-07_answer_quality_result_v0.1.json`
- Experiment ID: `UCG-EVAL-AQ-20261007-v0.1`
- Compact result SHA-256: `818d8e34456dd765c49a125451f90b0786d78b23f9f1c244eb4a0841a789a295`
- Raw judged artifact SHA-256: `f0a2b76fa4aafb940ff87896d1bf4e54e5523d02bac7e98bf397bda7aafa7cd0`
- Raw answer artifact SHA-256: `b418d214583dd1e358fce58934dd912789631957bdd560b10484ff629264cf79`
- Rerun judge artifact SHA-256: `ed939a75f9da644e8c971f8fa37bb0662db2d85e895a92f10b891ba6fd7760d0`
- Router runtime fix used during inference: `c477314d`
- Temporary benchmark route was dev-only and is not part of the UCG repository.
