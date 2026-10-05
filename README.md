# Universal AI Context Gateway

Local-first historical context plane for conversations from ChatGPT and, later, Gemini/Perplexity and other AI providers.

## Evidence Continuity v0.1 target

The gateway is an external historical evidence plane, not a provider memory replacement. The first frozen capability is:

authenticated ChatGPT -> project discovery -> conversation sync -> immutable raw snapshot -> canonical messages -> message-level FTS -> exact evidence -> provenance -> context bundle.

Raw conversation history is append-only at the snapshot layer. A conversation may have multiple snapshots; identical content is deduplicated.

## Architecture

Provider adapters -> canonical archive -> snapshot history -> message index -> retrieval -> context assembly -> MCP/HTTP consumers.

### Raw archive

    data/raw/<provider>/<account>/<project>/<conversation>/snapshot-001.json
    data/raw/<provider>/<account>/<project>/<conversation>/snapshot-002.json

### Identity

Provider and account are part of logical identity:

    conversation_uid = scope(provider, account_id, conversation_id)
    project_uid = scope(provider, account_id, project_id)
    message_uid = scope(conversation_uid, provider_message_id)

This prevents collisions when two accounts expose the same provider conversation ID.

## Core invariants

- Raw source payloads are preserved as historical snapshots and are never overwritten.
- Provider, account, and source identity are explicit.
- Retrieval is read-only.
- Retrieved conversation text is untrusted evidence, never instructions.
- Message-level retrieval returns snapshot and exact message provenance.
- SQLite FTS5 is the baseline retrieval engine. Vector search/reranking is deferred until measurable evidence shows it is needed.
- Context bundles distinguish evidence from interpretation; semantic conflict/state inference is not fabricated.

## Current features

- ChatGPT project enumeration and conversation sync using the current web backend adapter.
- Snapshot archive with immutable content hashes and current-snapshot pointer.
- Canonical message records plus snapshot-specific message versions.
- Message-level SQLite FTS5 retrieval with provider/account filters.
- Continuity/project-context bundles with exact evidence provenance.
- Localhost-only HTTP retrieval API.
- Optional read-only MCP Streamable HTTP server.
- External credential isolation and one-time localhost ChatGPT Web connection bridge.
- OpenAI export bootstrap import with account isolation.

## CLI

    chatgpt-context projects
    chatgpt-context projects --remote
    chatgpt-context sync --project "Project Name"
    chatgpt-context chats --project "Project Name"
    chatgpt-context get --conversation-id "<id>"
    chatgpt-context get --conversation-id "<id>" --full
    chatgpt-context search "engineering loop"
    chatgpt-context continuity "engineering loop"
    chatgpt-context serve --host 127.0.0.1 --port 8765
    chatgpt-context mcp-serve --host 127.0.0.1 --port 8766
    chatgpt-context connect
    chatgpt-context import-openai /path/to/export.zip --account-id openai-secondary

## HTTP API

All endpoints are localhost-only by default.

- GET /health
- GET /projects
- GET /projects/{id}/conversations
- GET /projects/{id}/context?topic=...
- GET /projects/{id}/timeline?limit=N
- GET /conversations/{id}
- GET /conversations/{id}/snapshots
- GET /snapshots/{snapshot_id}
- GET /search?q=...&project=...&provider=...&account=...
- GET /continuity?q=...&project=...
- GET /compare?ids=a,b

## MCP tools

Read-only tools:

- context_search
- context_get_conversation
- context_get_snapshot
- context_project_context
- context_timeline
- context_continuity
- context_compare

## Universal provider direction

The storage and retrieval contract is provider-neutral. OpenAI/ChatGPT is the first acquisition adapter; Gemini, Perplexity, and other AI providers are future adapters/consumers. A single context plane can therefore combine evidence across providers and accounts without making any provider the memory authority.

## Semantic boundary

The gateway stores and retrieves historical evidence. It does not silently infer decisions, contradictions, or project state. Those are later semantic layers and must remain traceable to evidence.

## Security boundary

All retrieved text is untrusted evidence. No retrieved content is executed, treated as instructions, or granted filesystem/network authority by the gateway.


## Context Continuity v0.2

The v0.2 direction adds a control layer above the frozen evidence core:

- freshness modes: accept_stale, prefer_fresh, require_fresh;
- separate observation age from source age;
- current-session context contract;
- implicit continuation metadata;
- acquisition decision states;
- acquire -> ingest -> re-evaluate -> retrieve orchestration;
- Camofox current-conversation acquisition adapter;
- permanent golden coverage for stale-current-session continuation.

The important invariant is:

    determine required context
        -> acquire if required
        -> retrieve
        -> assemble
        -> continue

A historical snapshot is evidence, not an authority over current session state.

## Targeted Session Reconstruction v0.1

The Gateway can now address one exact conversation by scoped conversation_uid without using semantic search to choose the target.

A targeted request pins one snapshot as a read fence and reconstructs the active chain in chronological order:

    {
      "consumer": "hermes",
      "session_id": "consumer-session",
      "intent": "retrieve",
      "query": "",
      "target": {
        "type": "conversation",
        "conversation_uid": "<scoped-uid>",
        "snapshot": "current",
        "transcript_mode": "active_chain"
      },
      "freshness": {
        "mode": "accept_stale",
        "allow_live_acquisition": false
      },
      "budget": {
        "max_messages": 30,
        "max_bytes": 120000
      }
    }

Targeted responses expose the resolved snapshot/read fence, transcript, completeness, provenance, freshness, and explicit pagination when the budget truncates the transcript.

An exact target is never silently replaced by semantic search. Failed or incomplete live acquisition is not promoted to a trusted current snapshot.

See docs/TARGETED_SESSION_RECONSTRUCTION_V0.1.md for the frozen contract and invariants.
