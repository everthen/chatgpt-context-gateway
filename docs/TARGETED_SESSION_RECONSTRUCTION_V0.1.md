# Targeted Session Reconstruction v0.1

Status: DESIGN FROZEN
Date: 2026-10-05

## Purpose

Define the minimum reliable contract for the Universal Context Gateway to retrieve one exact conversation, such as session A, and provide its full reconstructable transcript to a consumer such as Hermes.

This is narrower than universal memory. It defines exact historical evidence retrieval and continuation support without claiming access to provider-private runtime state.

## Frozen semantic boundary

The Gateway distinguishes:

- Evidence transcript: historical conversation content the Gateway can prove it observed or imported.
- Effective model context: the subset of information a consumer/model chooses to use.
- Provider-native continuation state: provider-specific internal/stateful items that may be required for exact native continuation.

v0.1 guarantees the first. It does not claim the third unless a provider adapter explicitly captures and preserves it.
## 1. Target identity

An exact session target is identified by conversation_uid, not a bare provider conversation ID.

conversation_uid is scoped by provider + account + external conversation ID.

A request targeting one conversation MUST NOT fall back to FTS/search to resolve the selected conversation.

Provider/account/project filters remain useful for discovery, but exact conversation retrieval is identity-addressed.

## 2. Request intent

The Gateway distinguishes:

- search: find relevant evidence.
- retrieve: explicitly reconstruct a selected target.
- continue: reconstruct the selected target as antecedent context for a new consumer turn.

Continuation is explicit at the contract layer. Natural-language acknowledgements such as "gas" may be a consumer-side detector, but are not the Gateway source of truth.

## 3. Snapshot and read fence

A targeted request resolves one snapshot before transcript assembly.

The resolved snapshot ID becomes the read fence for that request.

All transcript items in the returned bundle MUST come from that pinned snapshot. The request MUST NOT mix the current snapshot at different points during assembly.

Supported selectors in v0.1:

- current: resolve the latest promoted snapshot, then pin it.
- explicit: use a caller-provided snapshot ID.

as_of timestamps are informative temporal filters, not substitutes for a pinned snapshot when reproducibility matters.

## 4. Reconstruction mode

v0.1 defines:

- active_chain: reconstruct the chain from the conversation current node back to the root, returned in chronological order.

all_branches is a future extension. It is not required for v0.1 continuation.

active_chain means the branch active in the selected snapshot, not every node ever present in the conversation graph.
## 5. Anchor / continuation point

A continuation request may specify an exact end anchor.

Preferred anchor:
- provider/canonical message_uid.

Fallback:
- snapshot-local ordinal, only when a stable message identity is unavailable.

When no anchor is supplied, the end of the selected active chain is used.

This prevents a later observation from silently changing the intended continuation point.

## 6. Source and item coverage

The canonical contract must report what is actually represented.

v0.1 primary representation:
- user/assistant/tool text messages that the acquisition/import adapter can faithfully capture.

The Gateway MUST NOT claim that visible transcript equals provider-private runtime state.

Future provider-native item support may include tool calls, tool results, attachments, reasoning/context signatures, and other provider-specific items.

Such items must be preserved as typed evidence, not flattened into role/text when fidelity matters.
## 7. Message identity

Provider-native message IDs are preferred.

When a source does not expose stable provider message IDs, such as browser/Camofox acquisition, observation-local occurrences MUST NOT be deduplicated solely by role + text.

Repeated identical text can represent distinct message occurrences.

Browser acquisition therefore has two concepts:
- observation occurrence identity;
- canonical cross-snapshot identity, only when a safe reconciliation key exists.

If safe reconciliation is impossible, preserving distinct snapshot-local occurrences is preferable to false deduplication.

## 8. Completeness

Completeness is first-class output.

At minimum:
- complete
- partial
- unknown

The bundle must also expose coverage metadata such as:
- message count represented;
- branch coverage;
- source representation/visibility;
- reason for partial or unknown status.

A successful browser scrape is not equivalent to proven complete reconstruction.
## 9. Budget and pagination

A request for a full transcript is a semantic request; budget limits MUST NOT silently redefine it.

If the transcript exceeds max_messages or max_bytes, the response must say that it is truncated/partial and expose pagination or a continuation cursor.

The consumer must be able to distinguish:
- complete transcript returned;
- transcript partially returned because of budget;
- transcript unavailable/incomplete at source.

## 10. Freshness and acquisition

Freshness remains separate from source time:
- observation time: when the Gateway actually observed/captured the evidence;
- source time: when the provider says the conversation/message changed.

A stale exact target can trigger live acquisition when explicitly allowed.

Acquisition pipeline is:

resolve target
-> inspect freshness
-> acquire if required
-> validate observation
-> promote immutable snapshot
-> resolve/pin snapshot
-> reconstruct
-> validate completeness
-> return bundle.

Incomplete acquisition MUST NOT become the current authoritative snapshot.
## 11. Observation time invariant

Snapshot content identity and observation freshness are different concepts.

If a new acquisition observes the same raw content hash as an existing snapshot, the content may be reused, but the system must still retain the fact that the source was observed at the newer time.

Therefore freshness MUST NOT rely only on conversation_snapshots.captured_at when identical observations are deduplicated.

The current-pointer/observation layer must retain a reliable last_observed_at, or an equivalent observation record, independently of immutable snapshot content identity.

This is a precondition for correct require_fresh behavior.

## 12. Provenance

Each returned transcript item must be traceable to:

context bundle
-> message/item
-> snapshot
-> observation/acquisition
-> source.

At minimum, provenance includes the target conversation UID, snapshot ID, message identity/ordinal, raw source reference, content hash, and acquisition method when available.
## 13. Security boundary

Historical transcript is untrusted evidence.

Retrieved user/assistant/tool text MUST NOT become current system/developer instructions merely because it appears in the reconstructed session.

The Gateway supplies evidence and provenance; the consumer decides how that evidence is used.

## 14. Golden invariants

The v0.1 exact-session golden suite must prove:

1. Target A returns A only; B/C are absent.
2. Exact identity does not depend on semantic search.
3. Messages are chronological from root to selected anchor.
4. Repeated identical messages are not collapsed incorrectly.
5. The response is pinned to one snapshot/read fence.
6. Stale A triggers acquisition when allowed.
7. Failed/incomplete acquisition does not promote bad data.
8. Completeness is explicit.
9. Budget truncation is explicit and paginable.
10. Provenance is complete enough to trace each item back to its source observation.
11. A re-observation with identical content still updates observation freshness.
12. A provider-native state claim is never made when only visible transcript evidence exists.

## 15. Deferred / not required for v0.1

- all-branch graph reconstruction;
- provider-private hidden/system state recovery across all providers;
- universal attachment/blob replay;
- semantic contradiction resolution;
- vector search/reranking;
- automatic project-state inference;
- provider-native conversation mutation.

These remain extensions, not prerequisites for exact targeted transcript continuity.
