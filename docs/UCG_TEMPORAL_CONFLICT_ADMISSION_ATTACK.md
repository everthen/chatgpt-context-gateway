# Temporal + Conflict Admission Attack v0.1

Date: 2026-10-07

## Attack objective

Test whether UCG can prevent a high-ranking stale claim from entering the final context while avoiding the opposite failure: silently choosing one of two genuinely conflicting current claims.

The seam under attack is:

```
retrieval rank
    ↓
temporal state
    ↓
supersession / conflict relation
    ↓
context admission
```

Retrieval rank is deliberately treated as an imperfect signal.

## Rules under test

### Current query

If upstream temporal analysis marks one claim as obsolete and another as current, the current claim may be admitted while the obsolete claim is excluded.

However, this is **not** itself a semantic truth decision. The current/obsolete classification must come from an upstream temporal analysis layer.

### Explicit supersession

When the newer claim is explicitly marked `temporal_relation=supersedes`, admission can resolve the conflict and annotate the winner as:

- `temporal_resolution=supersedes_previous`
- `conflict_status=resolved`

### Unresolved current conflict

When two candidates are both current and no authoritative supersession exists, admission must keep both and mark them:

- `conflict_status=unresolved`

This is intentionally safer than silently selecting the newer timestamp.

### History query

For historical questions, the current claim and the best historical predecessor may both enter context.

## Attack cases

The suite contains six cases:

1. stale lexical winner at rank #1 vs current evidence at rank #2;
2. current rank #1 vs stale rank #2;
3. two current conflicting claims without supersession;
4. explicit supersession;
5. historical query requiring predecessor + current state;
6. conflicting current claims from different providers.

All six passed in the isolated Hermes VM execution.

## Important design decision

**Recency is not truth.**

The admission layer may use temporal state and an explicit supersession relation, but must not convert:

```
newer timestamp
    =>
true claim
```

That would make UCG an implicit semantic judge.

Instead:

```
retrieval
   ↓
temporal analysis
   ↓
conflict/supersession relation
   ↓
admission
```

The relation is evidence about state; the LLM still performs final interpretation.

## Remaining attack surface

This v0.1 attack suite is still deterministic and synthetic.

Next production-grade attacks should include:

- same claim changing across multiple snapshots;
- ambiguous update language such as "we may switch";
- reversion to a previously obsolete value;
- two providers with conflicting timestamps;
- account-scoped conflicts;
- source authority differences;
- explicit user request for historical state;
- conflicting evidence where neither source is authoritative.

The next gate is not "does the selector pass unit tests?"

The next gate is:

> can temporal/conflict admission improve context quality without suppressing evidence that a downstream model actually needs to reason about the conflict?
