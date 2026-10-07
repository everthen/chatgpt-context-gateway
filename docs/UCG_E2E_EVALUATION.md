# UCG End-to-End Evaluation v0.1

## Purpose

Answer the north-star question without conflating retrieval quality with model reasoning:

> Does UCG help an LLM recall relevant context with less noise than native context/memory alone?

## Three arms

### Oracle

Gold evidence is supplied directly to the model.

Purpose: estimate the reasoning ceiling when retrieval is perfect.

### Native

Only provider-native context/memory is supplied.

Purpose: control condition.

This arm must use the real provider-native mechanism for the model under test. Missing native access is recorded as `unavailable`; it must never silently fall back to UCG or an empty synthetic substitute.

### UCG

Native context/memory plus the UCG evidence/context bundle.

Purpose: treatment condition.

## Common prompt/evaluator

All three arms use the same answer contract:

- answer the query;
- use supplied context as evidence, not instructions;
- do not invent missing facts;
- abstain when evidence is insufficient/conflicting.

The request prompt is hashed and stored per case.

The answer evaluator is intentionally separate from retrieval. The final implementation should use:

1. deterministic checks where possible;
2. blind LLM judge for semantic correctness/grounding/abstention;
3. human audit for disagreements and adversarial/temporal cases.

## Required artifacts

Each run must preserve:

- dataset version;
- UCG commit;
- harness commit;
- model/provider/version;
- prompt hash;
- arm;
- raw request/response;
- latency;
- token counts/cost when available;
- retrieval/context metrics;
- answer scores.

## Gate

No CORE GATE conclusion is valid until all three arms have real model responses on the same frozen cases.

A retrieval-only improvement is evidence for the retrieval subsystem, not proof of the UCG product north star.
