# Evidence-Bound Worthiness Assessment v0.1

Date: 2026-10-07

## Purpose

Context worthiness is an evaluated property of a specific evidence item for a specific task. It must not be an unbound boolean such as `relevant=true`.

Every assessment binds to:

- evidence_id;
- evidence_hash;
- task fit;
- worthiness role;
- claim IDs;
- temporal state;
- optional conflict group;
- optional redundancy group;
- provenance completeness;
- assessment method;
- assessor version;
- optional confidence.

## Binding rule

An assessment can only be applied when both the evidence identifier and evidence hash match the retrieved item.

This prevents:

- stale assessments being reused after evidence changes;
- an assessment for one evidence item being attached to another;
- silent mutation of the evidence behind an existing worthiness decision.

## Assessment roles

- direct_support: directly relevant to the task claim;
- supporting: needed to establish a sub-claim or complete a distributed answer;
- contradiction: materially conflicts with another relevant claim and may therefore be necessary context;
- contextual: useful task context without directly proving the claim;
- none: retrieved but not worth putting into the final context.

## Assessment method

The contract records whether the assessment came from a rule, model, human, or benchmark oracle.

This is important because a model-produced assessment is not the same kind of evidence as an archive fact. The evaluator that produces the assessment must itself be benchmarked.

## Current experiment

The 16-case Oracle-Worthiness experiment demonstrates the potential ceiling:

- automatic decomposition + RRF: 93.75% recall / 31.25% noise;
- generic admission: 87.50% recall / 30.21% noise;
- oracle worthiness: 93.75% recall / 0% noise.

Therefore the next target is not more generic rank filtering. The next target is an auditable assessment pipeline that can approximate the oracle labels without using the gold set.

## Safety boundary

The assessment layer does not become the final judge of truth.

It labels how an evidence item relates to the task and other evidence. The LLM remains responsible for interpreting the admitted context, especially when conflicts remain unresolved.
