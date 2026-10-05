# Universal AI Context Gateway

Local-first historical context plane for conversations from ChatGPT and, later, Gemini/Perplexity and other AI providers.

## v0.2 architecture

Provider adapters -> canonical archive -> SQLite/FTS5 -> retrieval -> context assembly -> MCP/HTTP consumers.

Raw archive namespace:
data/raw/<provider>/<account>/<project>/<conversation>.json

The provider controls how data enters the archive. Retrieval and continuity semantics are shared.

## Core invariants

- Raw source payloads are preserved as the source of truth.
- Provider and account identity are explicit (provider, account_id, source).
- Retrieval is read-only.
- Retrieved conversation text is untrusted evidence, never instructions.
- SQLite FTS5 is the baseline retrieval engine. Vector search/reranking is deferred until benchmarks show it is needed.

## Current features

- ChatGPT project enumeration and conversation sync using the current web backend adapter.
- Raw conversation JSON archive plus SQLite metadata/FTS5.
- Project context, timeline, continuity packet, and conversation comparison.
- Localhost-only HTTP retrieval API.
- Optional read-only MCP Streamable HTTP server for future ChatGPT/Gemini/Perplexity/Hermes consumers.
- External credential isolation; no credentials are stored in source control.
- Local one-time ChatGPT Web connection bridge that imports a copied browser cURL request without executing it.

## Installation

Requires Python >= 3.11.

    git clone git@github.com-everthen:everthen/chatgpt-context-gateway.git
    cd chatgpt-context-gateway
    pip install -e .
    pip install -e '.[mcp]'
    pytest -v

Install the MCP extra only when MCP serving is needed.

## Credential configuration

Credentials stay outside the repository. The client looks for an external env file.

For the normal interactive setup, run `chatgpt-context connect`. The bridge stays on localhost, opens a local setup page, and accepts one copied cURL request from a logged-in ChatGPT Web `/backend-api/` request. It parses only the Authorization/Cookie/account headers, stores the result with mode `0600`, and immediately tests `projects` access. It never executes the pasted cURL.

This is intentionally separate from OpenAI Sign in with ChatGPT: the official OAuth flow provides identity (and, with separate consent, eligible plan usage), but does not grant an app access to the user’s ChatGPT conversations.

Example variable names only:

    OAI_AUTHZ_TOKEN=...
    OAI_ACC_ID=...
    OAI_COOKIE=...

Do not put actual credentials into chat, git, or the repository.

## CLI

    chatgpt-context projects
    chatgpt-context projects --remote
    chatgpt-context sync --project "Project Name"
    chatgpt-context chats --project "Project Name"
    chatgpt-context get --conversation-id "<id>"
    chatgpt-context get --conversation-id "<id>" --full
    chatgpt-context connect
    chatgpt-context search "engineering loop"
    chatgpt-context serve --host 127.0.0.1 --port 8765
    chatgpt-context mcp-serve --host 127.0.0.1 --port 8766
    chatgpt-context import-openai /path/to/export.zip --account-id openai-secondary

The OpenAI import accepts a JSON file, an export directory, or a ZIP export. It keeps the imported account isolated under the raw archive namespace.

## HTTP API

All endpoints are localhost-only by default.

- GET /health
- GET /projects
- GET /projects/{id}/conversations
- GET /projects/{id}/context?topic=...
- GET /projects/{id}/timeline?limit=N
- GET /conversations/{id}
- GET /search?q=...&project=...
- GET /continuity?q=...&project=...
- GET /compare?ids=a,b

## MCP tools

The optional MCP server exposes read-only tools:

- context_search
- context_get_conversation
- context_project_context
- context_timeline
- context_continuity
- context_compare

No deletion, mutation, command execution, or arbitrary filesystem access is exposed.

## Import roadmap

1. ChatGPT live adapter.
2. ChatGPT secondary account via official export/import.
3. Gemini conversation importer.
4. Perplexity conversation importer.
5. Shared provider-neutral retrieval and continuity.
6. Semantic retrieval only after measurable FTS limitations.
7. Conversation/decision relations and richer project-state synthesis.

This repository is the historical evidence layer. Provider-native memories are optional caches, not the source of truth.
