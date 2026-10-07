# UCG Traceability Protocol v0.1

Date: 2026-10-07

## Invariant

Every material engineering or research step must be reconstructable from repository state, inputs, configuration, artifacts, findings, and the decision that followed.

A Git commit is necessary but not sufficient.

## Required trace record

Every benchmark/research step records:

- experiment_id;
- step_id;
- parent_step when applicable;
- objective;
- repository;
- branch;
- exact code commit;
- dataset version and SHA-256 hash;
- assessor name and version;
- configuration;
- artifact paths;
- status: pass | fail | inconclusive | blocked;
- finding;
- decision;
- next step;
- UTC timestamp.

## Why the hash matters

Dataset labels and evidence corpora are part of the experiment input. A dataset filename alone is not enough because the contents may change.

The trace record therefore stores a SHA-256 digest of the exact dataset bytes used for the run.

## Evidence assessment traceability

Worthiness assessments additionally bind to:

- evidence_id;
- evidence_hash;
- claim IDs;
- temporal state;
- conflict/redundancy groups;
- assessment method;
- assessor version.

This prevents an assessment from silently drifting away from the evidence it describes.

## Decision chain

Every non-trivial result should be recorded as:

OBSERVATION -> FAILURE/IMPLICATION -> DECISION -> NEXT EXPERIMENT

Example:

auto decomposition -> 93.75% recall but 31.25% noise -> rank-only admission is insufficient -> build worthiness assessment benchmark

## Artifact rule

Raw artifacts are immutable evidence of the run. Derived summaries may be rewritten, but the original raw run must remain addressable.

## Reproducibility rule

A claimed improvement is not accepted unless another run can be reconstructed from the trace record and the referenced code/data/config.

If an external model/provider is required but unavailable, the result must be marked unavailable or blocked. No synthetic model result may fill the gap.

## Branch discipline

Experimental work remains isolated until its falsification criteria are passed.

Promotion to main requires:

1. passing deterministic tests;
2. raw benchmark artifact;
3. failure analysis;
4. decision record;
5. no unresolved traceability gaps.

## Current UCG discipline

The current evidence-admission/worthiness work is intentionally isolated on:

`experiment/evidence-admission-v0.1`

The branch contains the retrieval experiments, temporal/conflict attacks, worthiness gate, assessment contract, lower-bound assessor, Oracle-worthiness ceiling, and traceability protocol.

Do not call an experiment a CORE GATE result merely because its local tests pass.
