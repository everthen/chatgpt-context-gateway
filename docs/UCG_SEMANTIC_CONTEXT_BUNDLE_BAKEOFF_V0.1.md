# UCG Semantic Context Bundle Simulation v0.1

## Objective

Measure the downstream effect of the semantic assessor after deterministic admission policy, without claiming that the current benchmark branch is already the production ContextBundle implementation.

Pipeline under test:

retrieved candidates
→ model semantic assessment
→ deterministic admission policy
→ simulated final bundle
→ bundle recall / noise / conflict preservation

Dataset: seed_v0.1  
Dataset SHA-256: 977d081d4b0221d89c04bcd6ebe513c23304bbb2e94973b4fb9dbf25c5c34141

## Frozen treatment

Models:
- Gemini 3.8 Flash
- Claude Sonnet 4.6
- Claude Opus 4.6-thinking

All use the frozen 16-case rich semantic gold and 1024 output cap.

The simulation applies the same admission control rule used by the gold scorer:
- none → reject
- current_fact/latest_current_decision + obsolete → reject
- contradiction → admit_conflict
- direct_support/supporting → admit
- otherwise → reject

## Results

| Metric | Gemini | Sonnet* | Opus |
|---|---:|---:|---:|
| Cases scored | 16 | 15 | 16 |
| Bundle required-evidence recall | 100% | 100% | 100% |
| Semantic noise ratio | **0.00%** | 20.69% | 21.21% |
| Minimal-set noise ratio | 17.71% | 28.89% | 34.38% |
| Conflict preservation | 80.00% micro | 60.00% micro | 80.00% micro |
| Mean bundle size | 1.63 | 1.93 | 2.06 |

* Sonnet TU-04 remained malformed at the frozen 1024 output cap and is not silently retried.

Gold admission ceiling:
- required recall: 100%
- semantic noise: 0%
- minimal-set noise: 19.79%
- conflict preservation: 100%
- mean bundle size: 1.69

## Interpretation

The important distinction is between **semantic noise** and **conflict/context value**.

Gemini's simulated bundle has zero evidence whose gold admission is reject, so it is the cleanest final bundle under the frozen admission policy. Its weaker contradiction recall means some conflict evidence is omitted rather than admitted incorrectly.

Sonnet and Opus retain more conflict/context evidence, but also admit evidence whose gold admission is reject. Their larger bundles are therefore more complete in some conflict cases but noisier.

This supports the architectural split:

semantic assessor predicts evidence relationships;
deterministic admission policy controls what enters the bundle.

No permanent semantic-model winner is declared from this simulation alone.

## Decision

The next benchmark seam is downstream answer evaluation using the simulated final bundles, not another model-label bakeoff.

Required next comparison:
- Oracle bundle
- Gemini bundle
- Sonnet bundle
- Opus bundle
- Native-only baseline when available

Metrics:
- answer correctness
- grounding
- abstention / false certainty
- provenance correctness
- bundle tokens
- latency
- cost

## Artifacts

- `benchmarks/runs/seed_v0.1/2026-10-07_semantic_context_bundle_simulation_v0.1.json`
- `benchmarks/runs/seed_v0.1/2026-10-07_semantic_16case_trace.json`
- `benchmarks/runs/seed_v0.1/2026-10-07_gemini_16_gold_score_v0.1.json`
- `benchmarks/runs/seed_v0.1/2026-10-07_sonnet_opus_16_gold_score_v0.1.json`
