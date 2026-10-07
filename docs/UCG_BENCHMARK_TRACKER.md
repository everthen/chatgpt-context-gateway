# UCG Benchmark Workstream Tracker

## Current state

- [x] North-star recorded
- [x] Master plan recorded
- [x] P1/P2 design drafted
- [ ] P1 dataset schema implementation
- [ ] P1 120-case diagnostic dataset
- [ ] P1 eval split freeze
- [ ] P2 harness skeleton
- [ ] EXP-0 oracle
- [ ] EXP-1 native-only baseline
- [ ] EXP-2 native + UCG
- [ ] retrieval metrics
- [ ] context-noise metrics
- [ ] answer evaluation
- [ ] reproducible run artifacts
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
