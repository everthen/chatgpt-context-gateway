# UCG Benchmark Workstream Tracker

## Current state

- [x] North-star recorded
- [x] Master plan recorded
- [x] P1/P2 design drafted
- [x] P1 dataset schema implementation
- [ ] P1 120-case diagnostic dataset
- [ ] P1 eval split freeze
- [x] P2 harness skeleton
- [ ] EXP-0 oracle
- [ ] EXP-1 native-only baseline
- [ ] EXP-2 native + UCG
- [x] retrieval metrics
- [x] context-noise metrics
- [ ] answer evaluation
- [x] reproducible run artifacts
- [ ] CORE GATE report

## Rule

Every material step must leave a GitHub trail:
1. spec/change in repo;
2. implementation;
3. test/benchmark output;
4. failure analysis;
5. decision and next step.

## Current focus

**P1 + P2 only.**

No Zep bake-off, Mem0 DX bake-off, OMP compatibility work, or SaaS productization should become the main workstream before the CORE GATE is answered.

## North-star experiment

```
Native Only
    vs
Native + UCG
    vs
Oracle Context

Question:

Does UCG improve relevant-context recall and downstream answer
quality while reducing/controlling irrelevant context?
```

## First executable retrieval result

Recorded on 2026-10-07 in `docs/UCG_BENCHMARK_FIRST_RUN.md` and `benchmarks/runs/seed_v0.1/2026-10-07_ucg_only.json`.

Key finding: UCG/FTS5 baseline reached 0.6563 gold recall with 1.0000 provenance completeness and 0.0625 context noise ratio. This is a retrieval baseline only; CORE GATE remains unanswered because Native and Oracle arms are not runnable yet.

## EXP-2 results

- [x] Explicit multi-query evidence assembly
- [x] Lexical automatic decomposition control
- [x] RRF ranking experiment
- [x] Raw run artifacts recorded
- [x] E2E Oracle/Native/UCG contract drafted
- [ ] Real Oracle model adapter
- [ ] Real Native-memory adapter
- [ ] Real UCG model adapter
- [ ] Blind answer evaluator
- [ ] CORE GATE end-to-end report

Latest retrieval finding: auto lexical decomposition reaches 93.75% gold recall but 31.25% context noise; explicit decomposition reaches 75.00% recall with 14.58% noise. No north-star conclusion yet.

## Context worthiness

- [x] Evidence admission policy v0.1
- [x] Temporal/conflict admission attack suite
- [x] Context worthiness gate implementation
- [x] Context worthiness attack suite
- [x] Oracle-worthiness ceiling benchmark
- [ ] Reliable worthiness annotation layer

Finding:

```
auto decomposition: 93.75% recall / 31.25% noise
generic admission:   87.50% recall / 30.21% noise
oracle worthiness:   93.75% recall /  0.00% noise
```

Decision: stop treating rank/top-k admission as the main solution. The next seam is reliable, auditable worthiness annotation before final context assembly.


## Worthiness assessment

- [x] Evidence-bound worthiness assessment contract
- [x] Lexical worthiness assessor lower bound
- [x] Worthiness assessment benchmark
- [x] Assessor fail-closed interface
- [ ] Semantic/model worthiness assessor
- [ ] Human audit of worthiness labels

Latest finding:

```
lexical assessor:
task-fit accuracy       52.08%
role accuracy            52.08%
worthiness precision     63.54%
worthiness recall        87.50%
```

Decision: lexical overlap is a lower-bound control only. Next treatment is a real semantic/model assessor using the same evidence-bound assessment contract.


## Traceability

- [x] Traceability protocol v0.1
- [x] Trace record validation contract
- [x] Dataset SHA-256 helper
- [x] Traceability contract smoke test
- [ ] Enforce trace record generation in every benchmark CLI run

Rule:

```
commit + dataset hash + config + assessor + artifact
+ finding + decision + next step
= traceable experiment
```

A local pass without a reconstructable trace is not accepted as a research result.


## Semantic worthiness assessor

- [x] EXP-2E issue created (#5)
- [x] Blind semantic assessor contract
- [x] Strict structured-output parser
- [x] Blind/gold pack separation
- [x] Fail-closed unavailable model adapter
- [x] Trace record with dataset SHA-256
- [ ] Real semantic/model adapter
- [ ] Semantic assessor benchmark run

Current trace:
`benchmarks/runs/seed_v0.1/2026-10-07_semantic_assessor_trace.json`

Decision: the evaluator and blind input contract are now frozen for the treatment experiment. Only the real model/provider adapter remains unbound.


## EXP-2E — Semantic model treatment

- [x] Blind semantic assessor contract
- [x] Strict response parser
- [x] Blind/gold pack separation
- [x] OpenAI-compatible model adapter
- [x] Adapter contract smoke test
- [x] Real endpoint probe recorded
- [x] Fail-closed treatment behavior
- [ ] Real semantic model run

Treatment status:

```
CONTRACT        PASS
ADAPTER         PASS
ENDPOINT        BLOCKED
MODEL RUN       BLOCKED
```

No semantic/model quality claim is allowed until a real model response is captured and scored against the frozen gold sidecar.
