# Host Session Binding v0.1

## Status

FROZEN FOR EXPERIMENTAL USE; live acquisition and worker handoff are implemented as separate hardened layers.

This contract maps a provider-hosted session identity to one canonical `conversation_uid` inside the Universal Context Gateway. It is provider-specific at acquisition time and provider-neutral at the canonical model boundary.

## Proven semantics

1. The OpenAI MCP host supplies `openai/session` metadata.
2. The Gateway never returns or persists the raw host session value. It derives a short SHA-256 fingerprint for equality and diagnostics.
3. A binding key is `(provider, host_session_fingerprint)`.
4. A binding records `account_id`, `conversation_uid`, `bound_at`, `last_seen_at`, and `source`.
5. Binding is only accepted when the target conversation exists and its provider/account match the binding.
6. An existing host-session binding is not silently moved to another conversation. A conflicting rebind is rejected.
7. For `retrieve` or `continue` requests that omit an explicit target, an existing ChatGPT host-session binding supplies the exact conversation target.
8. Exact retrieval then uses the existing targeted-session reconstruction semantics: current snapshot resolution, read fence, active-chain transcript, completeness, and provenance.

## Experiment proof

Observed on the authenticated ChatGPT session:

- Host session fingerprint: `c1ec0a5e1a3797a1`
- Browser source: Camofox authenticated profile `chatgpt_human_login`
- Conversation title: `Lanjutkan Proof Hermes`
- ChatGPT conversation id observed by Camofox: `6ac34f04-b2b8-83ec-9491-9658f24968eb`
- Canonical conversation UID: `8ee1f62dbce592995564ab9fec5246c8fd5b72e266f2fa5856bbc2aca75459c2`

The Gateway successfully accepted a `continue` request with no target and resolved it to the bound canonical conversation. The returned transcript used exact-snapshot retrieval and contained 9 messages with complete active-chain coverage.

## Separation of concerns

Camofox is the acquisition channel. It is not the memory store.

The Universal Context Gateway remains responsible for normalization, canonical identity, snapshots, provenance, binding, and retrieval.

## Deferred

Automatic live Camofox acquisition from the MCP `context_request` path is not frozen here yet. v0.1 proves identity-to-conversation binding and exact archive retrieval. Live acquisition remains a separate follow-up step so freshness behavior can be falsified independently.

Provider-specific host metadata beyond OpenAI remains deferred.
