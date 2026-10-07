# Semantic Worthiness Assessor v0.1

Date: 2026-10-07

## Objective

Test whether a semantic/model-based assessor can decide which retrieved evidence is worth sending to the LLM without seeing benchmark truth labels.

## Blindness

The model-facing assessment pack must not expose:

- gold/supporting/distractor labels;
- benchmark evidence keys;
- expected claims;
- gold provenance maps;
- expected answer annotations.

Candidates receive local opaque IDs such as `C1`, `C2`, `C3`.

The model sees the query and the candidate evidence text plus provenance identity fields that are legitimately available at retrieval time.

## Required model output

One structured assessment for every candidate:

- candidate_id;
- task_fit;
- worthiness_role;
- temporal_state;
- claim_ids;
- conflict_group;
- redundancy_group;
- provenance_complete;
- confidence.

Allowed task_fit values:

`direct | supporting | contextual | none`

Allowed worthiness roles:

`direct_support | supporting | contradiction | contextual | none`

Allowed temporal states:

`current | obsolete | proposed | unknown`

## Set-level reasoning

The assessor receives the candidate set together because worthiness is not purely item-local.

It must be able to recognize:

- two candidates that express the same claim;
- a current claim and its obsolete predecessor;
- unresolved contradictions;
- complementary evidence required for a distributed answer;
- proposals that have not become decisions.

## Parser rules

The harness rejects:

- invalid JSON;
- unknown candidate IDs;
- duplicate candidate assessments;
- missing candidates;
- invalid enum values;
- confidence outside 0..1.

A malformed or partial model response is therefore an assessment failure, not silently ignored.

## Assessor ladder

```
Oracle / Human        = ceiling
Semantic Model        = treatment
Lexical Rule          = lower bound
Unavailable           = explicit blocked state
```

No model result is fabricated when an adapter is unavailable.

## Evaluation

The semantic assessor will be compared against the gold sidecar for:

- task-fit accuracy;
- worthiness-role accuracy;
- temporal-state accuracy;
- contradiction recall;
- worthiness precision;
- worthiness recall;
- confidence calibration;
- context noise after admission;
- retained relevant evidence.

## Traceability

Every semantic assessment run must record:

- exact code commit;
- dataset version + SHA-256;
- blind input artifact;
- gold sidecar artifact stored separately;
- model/provider/version;
- prompt/template hash;
- model configuration;
- raw model request;
- raw model response;
- parser result;
- scoring;
- decision;
- next step.

## Current status

The blind assessment contract, strict parser, fail-closed unavailable adapter, and gold/blind pack separation are implemented.

No real semantic model result is claimed yet.

Next step: connect a real model adapter and run the same frozen candidate packs without changing the evaluator.
