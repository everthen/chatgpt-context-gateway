# Context Worthiness Gate v0.1

Date: 2026-10-07

## Question

The central admission question is not:

> Did retrieval find this evidence?

It is:

> Is this evidence actually worth putting into the model context for this task?

A retrieved item can be lexically similar but useless; directly supportive; necessary supporting context; contradictory and therefore important; redundant with stronger evidence; obsolete for the requested temporal mode; or unusable because provenance is incomplete.

Therefore UCG separates retrieval from context worthiness.

## Pipeline

query -> query planning / decomposition -> high-recall retrieval -> candidate evidence -> temporal + conflict analysis -> worthiness annotations -> CONTEXT WORTHINESS GATE -> minimal sufficient context -> LLM reasoning

## Worthiness decision

The gate consumes upstream annotations:

- task fit: direct | supporting | contextual | none;
- worthiness role: direct_support | supporting | contradiction | contextual | none;
- provenance completeness;
- temporal state;
- conflict status;
- claim IDs covered;
- redundancy group.

The gate returns:

- admit;
- admit_conflict;
- reject.

### Admit

Use when evidence has clear task/claim value and sufficient provenance.

### Admit conflict

Use when contradictory evidence is itself necessary context because the disagreement is unresolved.

The gate should not silently remove disagreement just to make the context cleaner.

### Reject

Use for no task/claim value, incomplete provenance, obsolete evidence for a current task, or invalid annotations.

## Minimal sufficient context

Worthiness is not only per-item classification.

The selector also constructs the smallest defensible set:

1. remove items with no task/claim value;
2. preserve unresolved contradictions;
3. collapse redundant evidence supporting the same claim;
4. preserve complementary evidence supporting distinct claims;
5. respect the final context budget.

## Important non-goal

The worthiness gate is not a semantic truth oracle.

A direct_support annotation means an upstream evidence analysis step classified the item as supporting the task claim. It does not mean the claim is objectively true.

That upstream classification must itself be evaluated separately.

## Why this matters for the north star

The north star requires separating at least three measurements:

1. retrieval recall — did UCG find the evidence?
2. worthiness precision — did UCG send evidence that actually helps?
3. downstream answer quality — did the model reason better with that context?

Conflating these hides failure modes.

## Attack suite

The v0.1 synthetic attack suite includes lexical match with zero task value; direct support; supporting sub-claim; unresolved contradiction; incomplete provenance; obsolete evidence; redundant paraphrases; complementary evidence; and cross-source current conflict.

The isolated implementation test passed.

## Next hard cases

- ambiguous language such as 'may switch' versus an actual decision;
- reversible decisions and explicit reversion;
- evidence that supports one claim but contradicts another;
- source or authority differences;
- account-scoped evidence;
- evidence that is individually weak but jointly sufficient;
- cases where the model needs both sides of a conflict to answer correctly.

## Decision

Keep Context Worthiness Gate v0.1 behind the experiment branch.

Do not attach it to the main retrieval benchmark until the benchmark schema can provide auditable task-fit and claim-support annotations.

That separation is intentional: otherwise the benchmark would measure our annotation assumptions rather than the UCG retrieval/admission system.
