# P1 — Golden Context Dataset v0.1

## Purpose

Menguji core north-star UCG:

> Dengan UCG, apakah LLM lebih mampu mengingat context yang relevan dengan lebih sedikit noise dibanding native memory/context saja?

P1 tidak mengevaluasi kualitas model secara umum. P1 menyediakan **kasus diagnostik** yang memungkinkan retrieval failure, context-selection failure, dan reasoning failure dipisahkan.

## Dataset unit

Setiap case wajib memiliki:

- `case_id`
- `task_family`
- `corpus`
- `query`
- `gold_evidence`
- `supporting_evidence`
- `distractors`
- `temporal_state`
- `expected_claims`
- `provenance_map`
- `difficulty`

### Conceptual schema

```json
{
  "case_id": "ctx-001",
  "task_family": "new_session",
  "query": "...",
  "gold_evidence": [
    {
      "provider": "chatgpt",
      "account_id": "main",
      "conversation_id": "...",
      "message_id": "...",
      "snapshot_id": "...",
      "role": "required"
    }
  ],
  "supporting_evidence": [],
  "distractors": [],
  "temporal_state": {},
  "expected_claims": [],
  "provenance_map": {},
  "difficulty": "hard"
}
```

## Task families

### 1. Long Session

Informasi relevan muncul jauh di belakang dalam sesi/percakapan panjang.

Target:
- long-range recall;
- chronology;
- temporal/causal linkage.

### 2. New Session Rehydration

Context tersebar pada session A/B/C dan query muncul pada session baru.

Target:
- cross-session reconstruction;
- selective context recall;
- low-noise context assembly.

### 3. Cross-Provider

Evidence dibagi di ChatGPT, Claude/Gemini/Perplexity/custom-agent style sources.

Target:
- provider-neutral retrieval;
- scoped identity;
- cross-provider evidence assembly.

### 4. Temporal Update / Obsolete Memory

Fakta lama diperbarui atau dibatalkan oleh evidence baru.

Target:
- freshness;
- update handling;
- obsolete-memory avoidance.

### 5. Adversarial Distractors

Distractor sengaja:
- lexically similar;
- semantically related;
- from same project;
- from wrong time;
- obsolete;
- from wrong provider/account;
- plausible but incorrect.

Target:
- precision;
- noise resistance;
- identity correctness.

## Initial target size

v0.1:
- 120 cases total;
- 40 Long Session;
- 40 New Session;
- 40 Cross-Provider.

Across all families, include:
- easy;
- medium;
- hard;
- adversarial.

Temporal-update/obsolete-memory cases should be distributed across the families rather than becoming a separate silo.

## Gold evidence policy

Gold evidence is the minimum evidence set required to answer the query correctly.

Do not force a single exact evidence set when multiple paths are legitimately sufficient. Use:
- required evidence;
- acceptable alternative evidence;
- supporting evidence.

This prevents penalizing valid retrieval paths.

## Distractor policy

Every non-trivial case should have at least one meaningful distractor. Hard/adversarial cases should contain distractors that are plausible but wrong because of:
- time;
- scope;
- account;
- provider;
- supersession;
- semantic relation.

## Dataset split

Use:
- `train/dev` only for harness development;
- `eval` held out for final measurement.

Keep the first official eval set frozen once the benchmark is declared stable.

## Provenance requirement

Every gold evidence item must be traceable to an exact source object wherever possible:
provider → account → conversation → snapshot → message/artifact.

Do not make the benchmark depend on summaries that cannot be traced back to source evidence.

## Acceptance criteria

P1 is complete when:
- schema is frozen;
- 120 diagnostic cases exist;
- every case has gold evidence and expected claims;
- distractor strategy is represented;
- provenance is complete;
- train/dev/eval split is frozen;
- dataset can be loaded deterministically by P2.
