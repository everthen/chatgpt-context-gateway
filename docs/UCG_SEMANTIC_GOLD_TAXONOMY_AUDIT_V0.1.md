# Semantic Gold Taxonomy + Four-Case Audit v0.1

Date: 2026-10-07

## Why the taxonomy changed

The previous benchmark conflated semantic role, worthiness/admission, and context sufficiency. That made a model look wrong when it correctly identified useful historical context or a material contradiction that the old gold set had labeled only as none/distractor.

The v0.1 audit therefore separates:

1. task_fit — direct | supporting | contextual | none;
2. worthiness_role — direct_support | supporting | contradiction | contextual | none;
3. temporal_state — current | obsolete | proposed | unknown;
4. admission — admit | admit_conflict | reject;
5. sufficiency_role — required | complementary | optional | not_needed;
6. conflict_group — explicit grouping for unresolved or historical conflicts.

## Audit method

This is an oracle/manual audit against the frozen synthetic corpus.

It is **not an independent human inter-rater study**. The purpose is to establish a defensible reference taxonomy before spending more provider/model budget on the semantic treatment.

Dataset SHA-256:

977d081d4b0221d89c04bcd6ebe513c23304bbb2e94973b4fb9dbf25c5c34141

Cases:

- LS-02 — current retention fact;
- NS-04 — north-star framing with competing goals;
- XP-01 — distributed cross-provider provenance requirement;
- TU-04 — latest automatic-recall decision.

## Case-level audit decisions

### LS-02

Minimal sufficient set: ls02.gold

The 30-day final policy is direct support and should be admitted.

The pipeline-revisited sentence is contextual but not necessary.

Cold archival is contextual but not required.

The 90-day proposal is historical/obsolete contradiction. It matters only under history/conflict mode and is rejected for the default current-fact mode.

### NS-04

Minimal sufficient set: ns04.gold

Conflict-complete set: ns04.gold + ns04.dist1 + ns04.dist2

The two competing-goal statements are not random noise. They materially qualify the framing, so the audit marks them contradiction + admit_conflict.

This is the canonical example showing why contextual or contradiction must not automatically mean noise.

### XP-01

Minimal sufficient set: xp01.openai + xp01.google

The positive design requirement is distributed across two provider sources, so both are required.

The draft-gap item is contradiction/proposed and is useful as conflict/history context, not as proof of the positive requirement.

### TU-04

Minimal sufficient set: tu04.gold

The current position is explicitly that automatic recall remains a hypothesis pending benchmarking.

The two older claims are obsolete contradictions and should be rejected for a latest-current-decision query.

## Re-score of the existing bake-off

| Model | Cases scored | Role accuracy | Temporal accuracy | Admission accuracy | Required-evidence recall | Contradiction recall |
|---|---:|---:|---:|---:|---:|---:|
| Gemini 3.8 Flash | 4 | 79.17% | 91.67% | 91.67% | 100% | 62.50% |
| Gemini 3.8 Flash High | 1 | 50.00% | 100% | 100% | 100% | 0% |
| Muse Spark 1.2 | 0 | — | — | — | — | — |
| Muse Spark 1.3 | 0 | — | — | — | — | — |

The important result is not that Gemini Flash is now 79% intelligent. The important result is that the richer taxonomy separates semantic role from final context admission.

Gemini Flash identified all required evidence in these four cases and derived the correct admission decision at 91.67% average candidate level.

## Model roster update

The router currently exposes these additional semantic-assessor candidates:

- ag/claude-sonnet-4-6
- ag/claude-opus-4-6-thinking

They are registered as next-treatment candidates, not mixed into the present score table.

The next model bake-off should use a capped output budget for Opus/Sonnet and record actual latency/quota separately. Router maximum-output metadata is not equivalent to the user's available quota.

## Decision

The gold taxonomy is upgraded.

The four-case oracle/manual audit is frozen.

The current provisional treatment candidate remains Gemini 3.8 Flash because it completed all four diagnostic cases and retained the strongest combination of semantic completeness and operational usability.

The next semantic bake-off should add Sonnet 4.6 and Opus 4.6 with a smaller output budget, then compare all candidates using this richer gold.

## Trace artifacts

- src/context_gateway/benchmark/semantic_gold.py
- tests/test_semantic_gold.py
- benchmarks/audits/seed_v0.1/2026-10-07_semantic_gold_audit_v0.1.json
- scripts/score_semantic_gold_audit_v0.1.py
- benchmarks/runs/seed_v0.1/2026-10-07_semantic_bakeoff_compact_v0.1.json
- benchmarks/runs/seed_v0.1/2026-10-07_semantic_gold_score_v0.1.json