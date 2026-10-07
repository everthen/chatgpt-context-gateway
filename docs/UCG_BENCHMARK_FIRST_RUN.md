# UCG Benchmark — First Retrieval Run v0.1

Date: 2026-10-07

## What ran

- Dataset: `benchmarks/data/seed_v0.1.jsonl`
- Cases: 16
- Task families: 4 × 4
- Runnable arm: UCG retrieval only
- Retrieval limit: 8
- Retrieval method: current UCG SQLite FTS5/message-level search
- Raw result: `benchmarks/runs/seed_v0.1/2026-10-07_ucg_only.json`
- CLI execution was validated on the Hermes VM from the same source files.

## Result

| Metric | Aggregate |
|---|---:|
| Gold recall / coverage | 0.6563 |
| Precision | 0.6250 |
| MRR | 0.6563 |
| nDCG | 0.6644 |
| Context noise ratio | 0.0625 |
| Irrelevant evidence rate | 0.0625 |
| Provenance completeness | 1.0000 |
| Mean retrieval latency | 0.67 ms |

Family-level gold recall:

| Family | Recall |
|---|---:|
| Long Session | 1.000 |
| New Session | 0.750 |
| Cross Provider | 0.125 |
| Temporal Update | 0.750 |

## What this means

This is **not** a CORE GATE result. Native-only and oracle arms are not runnable yet, so we cannot claim that UCG improves an LLM over native memory.

It is a useful retrieval baseline because it exposes concrete failure classes while preserving provenance perfectly.

### Observed failures

1. **Composed / multi-message queries**
   
   Cross-provider cases where the answer requires combining evidence across messages often returned nothing. SQLite FTS5 currently expects the query terms to co-occur in matching indexed text; it does not yet compose multiple retrievals into a single evidence set.

2. **Paraphrase / intent words absent from source**
   
   Cases such as "who owns context evaluation" failed because some query tokens were not literally present in the source message. This is a lexical-retrieval limitation, not proof that the underlying evidence is absent.

3. **Cross-provider evidence splitting**
   
   Cross-provider cases with two independent gold messages produced partial recall even when one message was retrieved correctly. This confirms that provider-neutral storage alone is not sufficient; retrieval must be able to assemble distributed evidence.

4. **Adversarial account isolation queries**
   
   A query can be semantically about account isolation without sharing all lexical tokens with either source. This needs a stronger query-to-evidence strategy before it can be used as a high-confidence product claim.

5. **Noise is currently manageable but not yet solved**
   
   Only two seed cases produced material distractor retrieval; overall context noise ratio was 6.25%. This is encouraging, but the dataset is still tiny and synthetic.

## Decision

Keep SQLite FTS5 as the measurable baseline. Do **not** add a vector database or semantic index solely to chase this score.

The next experiment should distinguish:

- query formulation failure;
- lexical retrieval failure;
- evidence assembly failure;
- model reasoning failure.

The benchmark schema should eventually label these challenge types explicitly so improvements do not hide one failure mode behind another.

## Next gate

1. Make the benchmark CLI + dataset loader part of the standard developer workflow.
2. Build an explicit query-expansion / multi-query retrieval experiment without changing the gold set.
3. Implement Oracle and Native arms.
4. Re-run the same frozen seed set.
5. Only after that scale toward the planned 120-case evaluation set.

## Known implementation fix

The first executable benchmark invocation exposed and fixed a CLI defect: `python -m context_gateway.benchmark.cli` exited successfully without running because `cli.py` lacked the `__main__` guard. The fix was committed before this recorded run.
