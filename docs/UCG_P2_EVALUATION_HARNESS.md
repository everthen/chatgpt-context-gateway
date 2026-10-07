# P2 — Evaluation Harness v0.1

## Purpose

Mengukur apakah UCG meningkatkan long-term/context recall dan downstream answer quality tanpa menambah irrelevant-context noise.

## Experimental arms

### EXP-0 — Oracle Context

Gold evidence diberikan langsung kepada LLM.

Purpose:
- estimate model reasoning ceiling;
- detect cases where failure is not a UCG retrieval problem.

### EXP-1 — Native Only

LLM menggunakan native context/memory tanpa UCG.

Purpose:
- control group.

### EXP-2 — Native + UCG

LLM dapat memakai UCG dengan explicit user-triggered recall.

Purpose:
- primary treatment.

### EXP-3 — Native + UCG + Model/Automatic Recall

Ditunda sampai EXP-2 stabil.

Purpose:
- test whether automatic retrieval is actually better than explicit trigger.

## Metrics

### Retrieval quality

- Recall@k
- Precision@k
- MRR
- nDCG@k
- gold coverage

### Context quality

- irrelevant evidence rate
- context noise ratio
- temporal correctness
- provider/account correctness
- provenance completeness
- bundle token count

### End-to-end

- answer correctness
- faithfulness / grounding
- abstention correctness
- human preference on sampled cases

### Operational

- retrieval latency
- end-to-end latency
- input/output tokens
- estimated cost

## Context Noise Ratio

```
noise_ratio =
irrelevant_retrieved_items / total_retrieved_items
```

Do not use this as the sole quality metric.

A system that retrieves everything can achieve high recall while being unusably noisy.

## Evaluation layers

### L1 — Deterministic

Checks:
- did gold evidence appear?
- were wrong provider/account/snapshot items retrieved?
- was obsolete evidence selected?
- latency/token counts;
- provenance integrity.

### L2 — LLM Judge

Checks:
- answer correctness;
- grounding;
- context relevance;
- comparative preference.

Judging must be blind to the treatment label where practical.

### L3 — Human audit

Audit ~5–10% of cases, especially:
- disagreements;
- large baseline/UCG deltas;
- adversarial cases;
- temporal updates;
- failures with high model confidence.

## Run manifest

Every run must record:

- dataset version;
- case version;
- UCG commit SHA;
- benchmark harness commit SHA;
- model/provider;
- model version;
- prompt/template hash;
- configuration;
- retrieval parameters;
- timestamp;
- random seed where applicable.

## Raw artifacts

Each case/run should be reproducible from raw artifacts:

```
run/
  case.json
  baseline_request.json
  baseline_response.json
  ucg_request.json
  ucg_bundle.json
  ucg_response.json
  retrieval.json
  scoring.json
  manifest.json
```

## Interpretation rules

Never optimize solely for end-to-end answer score.

A regression is meaningful when:
- retrieval improves but answer does not;
- answer improves while retrieval quality degrades;
- noise increases;
- provenance breaks;
- obsolete evidence usage rises.

These should become explicit failure modes.

## Decision gates

### CORE GATE — PASS

Require evidence that Native + UCG, relative to Native Only:
- improves relevant context recall;
- controls irrelevant retrieval;
- preserves provenance;
- gives repeatable downstream benefit;
- has acceptable token/latency overhead;
- keeps final judgment with the model.

### CORE GATE — FAIL

Examples:
- gains appear only on cherry-picked cases;
- irrelevant context rises enough to offset answer gains;
- results are not reproducible;
- provenance becomes unreliable;
- overhead erases practical benefit.

## Automatic recall

Do not evaluate automatic recall as a product assumption.

It is a later experimental arm. Only promote it when measured against explicit-trigger UCG and native-only control.

## Acceptance criteria

P2 is complete when:
- dataset loader works;
- all four experiment arms are representable;
- deterministic metrics are implemented;
- blind LLM-judge path exists;
- run artifacts are persisted;
- results can be reproduced from a commit + manifest;
- CORE GATE report can be generated automatically.
