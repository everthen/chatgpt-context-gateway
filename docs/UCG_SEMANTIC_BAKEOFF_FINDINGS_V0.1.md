# Semantic Worthiness Bake-off v0.1

Date: 2026-10-07

## Scope

Four real model candidates were evaluated on four diagnostic cases using the same blind candidate protocol and the same dataset:

- `LS-02` event retention
- `NS-04` north-star/conflict framing
- `XP-01` cross-provider provenance
- `TU-04` automatic recall decision

Models:

- `ag/gemini-3.8-flash`
- `ag/gemini-3.8-flash-high`
- `oc/muse-spark-1.2-contributor-free`
- `oc/muse-spark-1.3-contributor-free`

Dataset SHA-256:

`977d081d4b0221d89c04bcd6ebe513c23304bbb2e94973b4fb9dbf25c5c34141`

## Results

| Model | Completed | Protocol compliance | Strict support precision | Strict support recall | Notes |
|---|---:|---:|---:|---:|---|
| Gemini 3.8 Flash | 4/4 | 0% | 58.33% | 100% | Fastest complete path; commonly emits fenced JSON; rich conflict/context reasoning |
| Gemini 3.8 Flash High | 1/4 | 100% on completed case | 100% on completed case | 100% on completed case | Other 3 cases timed out around 90s |
| Muse Spark 1.2 | 0/4 | 0% | — | — | JSON/response normalization failure |
| Muse Spark 1.3 | 0/4 | 0% | — | — | JSON/response normalization failure |

## Key finding

Semantic quality and protocol compliance are separate dimensions.

Gemini 3.8 Flash correctly surfaced contextual, historical, and contradictory evidence in several cases. For example, an earlier 90-day retention proposal was classified as historical/contextual while the current 30-day policy was direct support. A current-vs-obsolete recall decision conflict was also explicitly grouped as a conflict.

The current seed gold taxonomy labels those non-answer items primarily as `none`/distractor. That is too coarse for a semantic-worthiness benchmark: a historical explanation or contradiction can be worth retaining even when it should not be treated as direct answer support.

Therefore exact-role and temporal scores from this bake-off are diagnostic, not a final semantic quality ranking.

## Operational finding

Gemini 3.8 Flash is the strongest provisional treatment candidate because it completed all four cases. Gemini 3.8 Flash High showed exact-schema compliance on its one completed case but timed out on the other three. Muse models are not benchmark-ready in the current adapter path because their output could not be normalized reliably; this is not evidence that their underlying semantic capability is inferior.

## Decision

Do not declare a permanent winner.

Use `ag/gemini-3.8-flash` as the provisional treatment candidate for the next frozen benchmark while the gold taxonomy is upgraded and raw-response capture is strengthened for Muse.

## Next experiment

1. Add gold roles for `direct_support`, `supporting`, `contextual`, `contradiction`, `obsolete`, and `proposed`.
2. Add a small human/oracle audit on the same diagnostic cases.
3. Re-score Gemini 3.8 Flash using that richer taxonomy.
4. Capture raw Muse responses before normalization so provider-format failures remain diagnosable.
5. Run the 16-case semantic treatment benchmark only after those controls are in place.