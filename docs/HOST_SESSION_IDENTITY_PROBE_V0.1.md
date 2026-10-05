# Host Session Identity Probe v0.1

## Purpose

Prove the host-provided MCP session identity path before introducing any canonical identity binding.

The probe is diagnostic only. It must not equate a host session identifier with `conversation_uid`.

## Current contract

- Host correlation identity: provider/host supplied metadata such as ChatGPT `_meta["openai/session"]`.
- Canonical historical identity: Gateway scoped `conversation_uid`.
- Binding between the two is a separate future contract.
- Raw host session identifiers are never returned by the probe.

## MCP tool

`context_host_identity_probe`

The tool returns:

- `request_id`
- `meta_keys`
- whether `openai/session` is present
- a short SHA-256 fingerprint of the raw session value
- raw session length
- `raw_identity_returned=false`

## Proof levels

### Level 0 — SDK path

Synthetic `_meta["openai/session"]` reaches the Gateway through MCP Streamable HTTP.

Observed on 2026-10-05:

- MCP SDK: 1.29.0
- same synthetic session value produced the same fingerprint across repeated calls
- raw session value was not returned

### Level 1 — Native ChatGPT host behavior

Required client-side proof:

1. Call `context_host_identity_probe` twice from the same ChatGPT conversation.
2. Confirm the fingerprint is identical.
3. Reload and call again in the same conversation; confirm stability.
4. Start a new ChatGPT conversation and call again.
5. Confirm the new conversation produces a different fingerprint.

This proves correlation behavior but does **not** prove mapping to a historical `conversation_uid`.

### Level 2 — Canonical binding

Only after Level 1 succeeds:

`openai/session -> HostSessionBinding -> conversation_uid`

The binding must remain separate from exact retrieval semantics.

## Important non-invariants

Do not assume:

- `openai/session == conversation_uid`
- `openai/session` is provider-independent
- another provider exposes an equivalent host identity
- a host identity is an authorization credential

## Current external-client constraint

OpenAI currently documents `_meta["openai/session"]` for ChatGPT tool calls and documents Secure MCP Tunnel for private MCP servers. OpenAI's current ChatGPT MCP documentation explicitly lists Pro for developer-mode read/fetch MCP access; Go is not explicitly listed there. Native ChatGPT proof therefore depends on the account/surface exposing custom MCP developer mode.

## Success criterion

The Gateway may proceed to identity-binding design only after native Level 1 evidence is captured. Until then, exact historical reconstruction remains driven by explicit `conversation_uid` targets and discovery/fallback mechanisms.
