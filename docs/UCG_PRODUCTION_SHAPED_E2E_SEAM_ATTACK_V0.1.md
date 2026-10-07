# UCG Production-Shaped E2E Seam Attack v0.1

## Purpose

This gate moves the lane-aware ContextBundle work from component/contract proof into a production-shaped transport and consumer seam proof.

Target path:

```text
production-shaped admission
  ↓
real selection-assessment shape
  ↓
lane materialization
  ↓
serialized ContextBundle
  ↓
deserialize + invariant validation
  ↓
answer-consumer projection
```

The production retrieval path remains intentionally unwired.

## Transport contract

A ContextBundle is serialized as:

```text
{
  "schema_version": "ucg-context-bundle.v0.1",
  "bundle": {
    "answer_context": [],
    "control_context": [],
    "epistemic_relations": []
  }
}
```

The transport layer now:

- rejects unsupported schema versions;
- rejects non-object or malformed lane arrays;
- validates the full bundle after deserialization;
- preserves lane metadata, citation eligibility, provenance, and relation guidance;
- keeps control raw evidence out of the answer-consumer projection.

Canonical serialization is byte-stable after deserialize → serialize round-trip.

## Strengthened invariants

The validator now additionally requires:

1. every relation endpoint exists in the bundle;
2. a relation cannot target itself;
3. relation guidance exactly matches the canonical relation type;
4. the relation target lane matches the relation semantics;
5. boundary/conflict/state control lanes must have the corresponding epistemic relation;
6. control evidence cannot become citation-eligible or answer-visible.

This closes seams that previously depended on in-memory construction order.

## Attack suite

The executable harness is:

`benchmarks/production_shaped_e2e_attack_v0_1.py`

Targeted adversarial cases:

- XP-02 — complementary provider evidence plus account-boundary control evidence;
- XP-04 — account-isolation boundary.

Core seam attacks:

- flatten control evidence into answer context;
- escalate control evidence to citation authority;
- delete required epistemic relations;
- retarget a boundary relation;
- invert boundary direction;
- tamper relation answer guidance.

A separate focused regression test explicitly retargets a boundary relation onto positive answer-support evidence and verifies fail-closed rejection.

## Direct execution results

Hermes VM does not provide pytest, so the historical pytest-based assertions were not claimed as pytest execution.

Direct checks executed instead:

| Gate | Result |
|---|---:|
| Legacy ContextBundle / selection self-checks | **15 PASS** |
| Focused transport checks | **3 PASS** |
| Production-shaped seam harness attacks | **6 PASS** |
| Focused retarget-to-answer-support attack | **PASS** |
| Canonical serialize → deserialize → serialize | **PASS** |
| Control raw-text exposure at answer boundary | **PASS** |

The explicit control-to-answer leak continues to fail closed.

## Decision

**PASS — production-shaped ContextBundle transport/consumer seam gate.**

This does **not** yet authorize production retrieval wiring.

The next gate is the real production admission → selection → lane materializer path, with persisted ContextBundle transport and the existing broader answer-quality evaluation rerun against that actual path.

TU-04 remains owned by upstream semantic assessment and must continue to fail closed rather than being fabricated downstream.
