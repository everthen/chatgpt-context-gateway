# UCG Evidence Admission Policy v0.1

Date: 2026-10-07

## Problem

Multi-query retrieval can deliberately optimize for recall and still return too much evidence for the model context.

The current seed benchmark demonstrates the trade-off:

- single-query FTS5: 65.63% recall, 6.25% context noise;
- explicit subqueries + RRF: 75.00% recall, 14.58% context noise;
- automatic lexical decomposition + RRF: 93.75% recall, 31.25% context noise.

The conclusion is not 'retrieve less'. It is:

> retrieval and context admission are different optimization problems.

Retrieval should be allowed to be high-recall. Context admission should be conservative.

## Policy v0.1

### Stage 1 — Candidate generation

Generate a broad candidate set from one or more retrieval intents.

For each candidate, retain a retrieval-support trace:

- query index;
- query text;
- rank within that query.

This is retrieval provenance, not semantic proof.

### Stage 2 — Query-local admission gate

A candidate is eligible for context only when it appears within the top N candidates of at least one retrieval intent.

Default:

- per_query_cap = 2

This prevents a candidate that is only weakly supported by one query from entering the context simply because the overall candidate pool is large.

### Stage 3 — Coverage preservation

Before filling the remaining context budget, admit the best eligible candidate for each retrieval intent.

This protects against a failure mode where one highly lexical query dominates the whole context and evidence for another required facet disappears.

### Stage 4 — Hard context budget

Default:

- final_limit = 4

After coverage seeding, remaining slots are filled by RRF order.

The policy is intentionally deterministic and auditable.

## What this policy does not claim

Evidence admission is not a truth oracle.

It does not by itself determine:

- whether a statement is factually correct;
- whether evidence is obsolete;
- whether two sources conflict semantically;
- whether the evidence actually satisfies the user's claim.

Those need later evidence-evaluation stages.

The intended pipeline is:

query -> query planning / decomposition -> high-recall candidate retrieval -> candidate evidence + retrieval trace -> EVIDENCE ADMISSION -> conflict / temporal / provenance checks -> context bundle -> LLM reasoning

## Why this is the right seam

A single scoring model for both retrieval and context selection creates a bad incentive:

- increasing recall tends to increase candidate volume;
- increasing candidate volume increases noise;
- reducing candidate volume too early can destroy recall.

Separating the stages lets UCG measure both curves independently.

## Benchmark

The experiment adds a ucg_admission arm to the retrieval benchmark.

It records:

- candidate limit;
- per-query admission cap;
- final context limit;
- returned evidence;
- retrieval metrics;
- context noise;
- provenance completeness.

The seed benchmark is still diagnostic. This experiment is not a CORE GATE result.

## Next falsification

Run the policy on the frozen 16-case seed, then on the planned 120-case diagnostic set.

The policy should pass only if it:

1. materially reduces context noise versus automatic decomposition + RRF;
2. does not collapse gold recall;
3. preserves provenance completeness;
4. remains deterministic and reproducible.

After that, add adversarial cases where:

- the correct evidence ranks below the local cap;
- different queries surface conflicting claims;
- obsolete evidence ranks highly;
- cross-provider evidence must be combined;
- one query produces many lexical distractors.

The policy should fail loudly rather than silently hiding missing evidence.

## Decision

Keep this as Evidence Admission v0.1, an experiment behind the benchmark harness.

Do not treat it as a product-level semantic relevance guarantee yet.
