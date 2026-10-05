# ChatGPT Context Gateway

Local-first archive and retrieval layer for ChatGPT conversations.

Design goals:
- Keep raw conversation payloads as the source of truth.
- Index metadata and extracted text in SQLite.
- Support project-scoped sync.
- Expose a localhost-only retrieval API.
- Keep authentication material outside the repository.

The sync adapter uses the authenticated ChatGPT web backend. This is not a public API and may change; isolate it behind the client module.

Commands will include projects, sync, chats, get, search, and serve.
