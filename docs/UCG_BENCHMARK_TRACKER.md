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
