# Universal Context Gateway — Research & Architecture Gap Audit v0.2

Status: RESEARCH COMPLETE — HARDENING APPLIED AFTER FALSIFICATION AUDIT
Date: 2026-10-05
Observed branch: feature/context-contract-acquisition-v0.2
Main branch observed: 57e3e8262b0e9885c8898c38f1426ca02236cfd9

## 1. Executive finding

The current Gateway already has a strong evidence core: immutable conversation snapshots, provider/account scoped identity, message-level FTS, exact message and snapshot provenance, ContextRequest/ContextBundle v1, acquisition checkpoints, Camofox completeness gating, untrusted-evidence boundaries, and current-session exclusion.

The latest golden failure is not primarily a retrieval failure. In the failure case, the active ChatGPT session contains a newer assistant commitment followed by the user saying “Gas bro! Thinking”, but the Gateway retrieves an older snapshot that does not contain that newest commitment.

The next architectural boundary is therefore:

CURRENT SESSION CONTINUITY + FRESHNESS / ACQUISITION DECISION + TEMPORAL PROVENANCE + CONTINUATION RECOVERY.

The target is not “better memory”. The target is: before a consumer continues work, determine what context must be available, whether local evidence is fresh enough, whether acquisition is required, and which evidence is authoritative for the requested scope and time.

## 2. External research synthesis

### 2.1 Context is a managed runtime resource

Anthropic treats context engineering as the curation of everything available to the model at inference time, including tools, external data, and message history. Its current guidance emphasizes just-in-time retrieval, progressive disclosure, compaction, and structured notes instead of replaying everything.

Implication: the Gateway should keep cheap identifiers and provenance, then fetch the smallest high-signal evidence set needed for the current turn.

Source: Anthropic, Effective context engineering for AI agents (2025-09-29).
https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents

### 2.2 Session state is distinct from raw history

OpenAI currently separates sessions, turns, items, orchestration state, and compaction. A session persists configuration, conversation, and saved work; a turn is an execution cycle; completed session items can be inspected later; compaction preserves state while reducing active context.

Implication: model current session state separately from the historical archive. The archive is evidence; the current session needs a small operational state layer.

Sources:
OpenAI, Run and continue sessions.
https://developers.openai.com/api/docs/guides/agents-api/sessions
OpenAI, Building Reliable Agents with Memory and Compaction.
https://developers.openai.com/cookbook/examples/agents_sdk/building_reliable_agents_memory_compaction
OpenAI, Compaction.
https://developers.openai.com/api/docs/guides/compaction

### 2.3 Retrieval needs temporal and conversational evaluation

LongMemEval evaluates information extraction, multi-session reasoning, temporal reasoning, knowledge updates, and abstention. LOCOMO-CONV adds implicit and composed conversational queries and finds retrieval gaps that are missed by simpler QA-style evaluation.

Implication: the Gateway golden suite must include implicit continuation, knowledge updates, temporal questions, and abstention when evidence is insufficient.

Sources:
LongMemEval: https://arxiv.org/abs/2410.10813
LOCOMO-CONV: https://arxiv.org/abs/2609.03467

### 2.4 Retrieval should preserve context, not only lexical similarity

Anthropic’s Contextual Retrieval work reports that contextualized BM25 plus embeddings can reduce retrieval failures and that reranking improves further. The architectural lesson is not “add a vector database now”; it is that retrieval units must remain interpretable and sufficiently contextualized.

Implication: keep SQLite FTS5 as the deterministic baseline. Add hybrid retrieval, contextualization, or reranking only after evals show a measurable retrieval gap.

Source: Anthropic, Contextual Retrieval.
https://www.anthropic.com/engineering/contextual-retrieval

### 2.5 Temporal provenance is a real design boundary

Recent memory research distinguishes when information was valid in the source from when a system recorded it. A 2026 bitemporal memory paper explicitly separates valid time and transaction time for point-in-time retrieval.

Implication: the Gateway should eventually distinguish source_updated_at, observed_at, ingested_at, snapshot_seq, and current pointer instead of treating one timestamp as freshness truth.

Source: A Graph-Native Bitemporal Memory Store for Conversational AI Agents.
https://arxiv.org/abs/2607.26520

## 3. Current architecture assessment

### 3.1 Already strong

Current flow:

Provider adapters -> canonical archive -> immutable snapshots -> message index -> retrieval -> ContextBundle -> HTTP/MCP consumers.

The current ContextRequest already carries consumer, session_id, query, scope, freshness, budget, trust, and current-conversation exclusion.

The current context_request path already exposes an acquisition-required result when fresh evidence is absent.

The Camofox layer already rejects incomplete observations before promotion to historical evidence.

### 3.2 Primary weakness

The Gateway can decide that acquisition is required, but the complete control loop is not yet owned by the Gateway:

freshness check -> select acquisition adapter -> acquire -> ingest -> re-evaluate -> retrieve -> assemble.

The current consumer integration can therefore ask for context against a stale corpus without forcing a current observation.

## 4. Data-model issue exposed by the golden failure

The current Camofox observation conversion maps browser observation time into conversation create/update timestamps. That conflates “when the provider changed” with “when we observed it”.

Recommended future semantics:
- source_created_at
- source_updated_at
- observed_at
- ingested_at
- snapshot_seq
- snapshot_id
- acquisition_method
- acquisition_attempt_id

Do not remove existing fields yet. First define the semantic contract.

## 5. Proposed v0.2 contracts

### 5.1 Freshness policy

Expand freshness into:
- mode: accept_stale | prefer_fresh | require_fresh
- max_observation_age
- max_source_age
- allow_live_acquisition
- allow_partial

Important distinction:

observation freshness is not source freshness.

### 5.2 Acquisition decision

Return an explicit decision object with:
- status: satisfied | stale | missing | partial | acquisition_required | acquisition_failed
- candidate source/provider/account
- scope
- method
- checkpoint
- reason
- expected cost
- expected freshness gain

The Gateway should be able to say: “I have evidence, but it is not fresh enough for this request.”

### 5.3 Current session state

Add a small operational state abstraction:
- session_id
- current_conversation_uid
- current_turn_id
- previous_turn_id
- pending_action
- last_assistant_commitment
- last_user_request
- active_task
- last_observed_at

This is not a replacement for the archive.

## 6. Continuation recovery

“Gas bro!” is an implicit query. It means the current user utterance depends on the immediately preceding conversational state.

The correct flow is:

user utterance -> continuation detection -> antecedent window -> freshness check -> acquisition if required -> retrieve previous actionable commitment -> ContinuationContext.

The continuation detector should not decide the task itself. It only signals that the current utterance depends on preceding state. Historical evidence still establishes what action was being approved.

Suggested ContinuationContext fields:
- detected
- antecedent_session_id
- antecedent_message_id
- antecedent_snapshot_id
- pending_action
- evidence_ids
- freshness_status

## 7. Temporal and snapshot semantics

The snapshot pointer is useful but should not be the only temporal primitive.

Future retrieval modes should include:
- current
- latest_observed
- as_of_snapshot
- as_of_time

This supports questions such as: what did we know then, what changed, and what was the latest decision at that point?

## 8. Retrieval strategy

Phase 1: SQLite FTS5 + exact provenance.

Phase 2, only after evals prove a gap: lexical + semantic hybrid retrieval, contextualized retrieval units, reranking, temporal weighting.

Do not introduce a vector database merely because modern RAG systems use one.

## 9. Evidence lineage

Universal Gateway should eventually treat these as first-class evidence classes:
- ConversationEvidence
- ResearchSourceEvidence
- ArtifactEvidence
- AttachmentEvidence

Messages may reference citations, URLs, source metadata, attachments, and research artifacts. Cross-provider workflows must preserve those links rather than only the final prose.

## 10. Gateway Golden Suite

### Retrieval
- exact message recall
- conversation recall
- provider/account isolation
- snapshot correctness
- provenance correctness

### Freshness
- fresh local evidence
- stale evidence
- missing evidence
- partial observation
- acquisition unavailable
- acquisition failure
- successful acquisition followed by retrieval

### Continuity
- Lanjutin...
- Gas
- Gas bro
- Gas yang tadi
- yang terakhir
- lanjut dari keputusan tadi
- implicit continuation after a new session

### Temporal
- knowledge update
- conflicting snapshots
- point-in-time retrieval
- newest-known vs currently-known

### Safety
- retrieved text cannot become instructions
- excluded current session cannot re-enter historical context
- cross-account collision fails closed
- incomplete acquisition cannot be promoted

### Consumer behavior
- enough evidence to continue
- abstain when evidence is insufficient
- do not invent missing state

## 11. Proposed architecture boundary

Universal Context Gateway should be understood as:

Historical Evidence + Current Context Acquisition + Context Interchange Plane.

Core layers:
1. Evidence Core: snapshot, identity, provenance, retrieval.
2. Context Contract: scope, freshness, budget, trust.
3. Acquisition Control: checkpoint, freshness decision, adapter selection, ingest/retry.
4. Session Continuity: current state, antecedent recovery, continuation context.
5. Evidence Extensions: citations, sources, artifacts, attachments.

The semantic claim, contradiction, and project-state engine remains outside this core until a falsifiable need is demonstrated.

## 12. Implementation order

Do not patch “Gas” first.

Recommended order:
1. Split observation freshness from source freshness.
2. Add explicit acquisition decision contract.
3. Add acquisition orchestrator: decide -> acquire -> ingest -> retry retrieval.
4. Add current-session state contract.
5. Add continuation recovery contract.
6. Add golden tests for implicit continuation and stale-current-session.
7. Improve ranking only after measured retrieval failures.

## 13. Permanent golden failure case

Assistant commitment:

“Setelah benchmark aman, aktifkan engine ini sebagai default Hermes -> jalankan golden test dari session Hermes baru.”

User:

“Gas bro! Thinking”

Expected:
1. detect continuation dependency;
2. inspect current session state;
3. verify Gateway freshness for the current conversation;
4. acquire the latest observation when stale;
5. ingest a new immutable snapshot;
6. resolve the immediately preceding actionable commitment;
7. return a ContextBundle with exact provenance;
8. consumer continues with that committed action.

Failure:

Gateway retrieves an older snapshot and reconstructs the wrong pending action.

This remains a permanent regression test.

## 14. Non-goals for v0.2

Do not yet add:
- vector database;
- opaque semantic graph;
- automatic contradiction resolution;
- automatic project-state inference;
- provider memory authority;
- irreversible summarization of raw evidence.

Raw evidence remains recoverable and provenance-first.

## 15. Research verdict

The Gateway’s identity should now be formalized as:

Historical Evidence + Current Context Acquisition + Context Interchange Plane

not:

Universal Conversation Memory.

The key architectural upgrade is moving from:

retrieve history

to:

determine required context -> acquire if needed -> retrieve -> assemble -> continue.

That is the boundary exposed by the latest “Gas bro!” failure.


## 16. Post-audit hardening status

The falsification audit exposed and closed these implementation gaps:

- incomplete Camofox observations are retained but cannot advance the current trusted snapshot;
- browser no-progress is fail-closed as incomplete;
- observation time is stored separately from source timestamps;
- concurrent handoff redemption is serialized and remains strictly one-time;
- exact target provider/account scope is enforced;
- worker capability scope is allow-listed and aggregate hermes-cli is denied;
- worker timeouts terminate the worker process group;
- worker stdout is parsed as Hermes stream-json;
- worker environment inheritance is sanitized;
- raw handoff bearer values are never returned to the model;
- expired handoffs and worker artifacts have bounded cleanup;
- the raw handoff/redeem path now resolves the same exact pinned reconstruction contract.
