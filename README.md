# ChatGPT Context Gateway

Local-first archive and retrieval layer for ChatGPT conversations.

## Features

- **Raw Payload as Source of Truth**: Saves pristine conversation JSON in `data/raw/<safe_project>/<conversation_id>.json`.
- **SQLite & Full-Text Search (FTS5)**: Indexes metadata, timestamps, and linear user/assistant extracted text.
- **Project-Scoped Sync**: Sync all projects or target specific projects by name or ID.
- **Localhost-Only Retrieval API**: Exposes lightweight JSON endpoints bound exclusively to `127.0.0.1`.
- **Strict Credential Isolation**: Zero credentials in source control; reads authentication tokens/cookies from an external environment file or environment variables.

---

## Installation

Requires Python >= 3.11.

```bash
git clone git@github.com-everthen:everthen/chatgpt-context-gateway.git
cd chatgpt-context-gateway
pip install -e .
```

To run test suites:
```bash
pip install pytest
pytest -v
```

---

## Configuration & Credentials

Authentication material must remain outside the repository. By default, the client looks for an env file in the following order:
1. `--env-file /path/to/env` passed via CLI
2. `CHATGPT_ENV_FILE` environment variable
3. `~/.config/chatgpt-context-gateway/env`
4. `~/.chatgpt-context.env`
5. `.env` in the working directory (ignored by `.gitignore`)

### Env File Format (`~/.config/chatgpt-context-gateway/env`)

```ini
# ChatGPT Web Backend Session Credentials
# Provide access token (Bearer) or session cookie:
CHATGPT_ACCESS_TOKEN="eyJhbGciOi..."
CHATGPT_COOKIE="__Secure-next-auth.session-token=..."

# Optional settings
# CHATGPT_BASE_URL="https://chatgpt.com/backend-api"
# CHATGPT_USER_AGENT="Mozilla/5.0 ..."
```

You can extract your session token or cookie from the browser developer tools (Application -> Cookies / Storage -> `__Secure-next-auth.session-token`) or the network inspector on `https://chatgpt.com`.

---

## CLI Usage

The entrypoint is `chatgpt-context`.

### 1. List Projects

List indexed projects in the local SQLite archive:
```bash
chatgpt-context projects
```

Or query live projects directly from ChatGPT:
```bash
chatgpt-context projects --remote
```

### 2. Sync Conversations

Sync a specific project:
```bash
chatgpt-context sync --project "Project Name"
```

Sync all projects:
```bash
chatgpt-context sync
```

Raw JSON payloads are stored under:
```
data/raw/<safe_project>/<conversation_id>.json
```
And metadata + text content are indexed into SQLite (`data/archive.sqlite3`).

### 3. List Chats

List all indexed conversations or filter by project:
```bash
chatgpt-context chats
chatgpt-context chats --project "Project Name"
```

### 4. Get Conversation Details

View metadata and extracted conversation transcript:
```bash
chatgpt-context get --conversation-id "<conversation-id>"
```

View the raw JSON payload:
```bash
chatgpt-context get --conversation-id "<conversation-id>" --full
```

### 5. Full-Text Search

Search conversations using SQLite FTS5:
```bash
chatgpt-context search "docker kubernetes"
chatgpt-context search "transformer" --limit 10
```

### 6. Run Retrieval Server

Start the localhost-only HTTP API server (default port `8765`):
```bash
chatgpt-context serve --host 127.0.0.1 --port 8765
```

---

## Localhost HTTP API

The server binds strictly to `127.0.0.1` and serves JSON:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check (`{"status": "ok", "version": "0.1.0"}`) |
| `GET` | `/projects` | List indexed projects |
| `GET` | `/projects/{project_id}/conversations` | List conversations for a project |
| `GET` | `/conversations/{conversation_id}` | Retrieve single conversation record |
| `GET` | `/search?q={query}&limit={n}` | Full-text search across conversations |

### Example Queries

```bash
# Health check
curl -s http://127.0.0.1:8765/health

# List projects
curl -s http://127.0.0.1:8765/projects

# Search
curl -s "http://127.0.0.1:8765/search?q=architecture"
```
