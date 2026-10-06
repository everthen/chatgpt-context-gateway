# Session Recovery & Forensic Continuation v0.1

Status: design/implementation candidate on `feature/session-recovery-capture-v0.4`.

## 1. Problem

A replacement agent may inherit an incomplete or stale reconstruction of a ChatGPT session that stopped accepting turns. The safe behavior is not to continue immediately. It must acquire more evidence, attack its own reconstruction, evaluate whether the state is sufficiently proven, and only then continue.

## 2. Boundary

UCG remains the frozen evidence/context substrate. Session Recovery is a consumer/orchestration protocol above UCG.

```text
UCG
  ├─ exact snapshot
  ├─ live hot observation
  ├─ deep acquisition
  ├─ provenance
  └─ freshness
        ↓
Session Recovery
  ├─ Discovery
  ├─ Falsification
  ├─ Evaluation
  └─ Continuation
```

The recovery layer must never reinterpret historical conversation text as current instructions.

## 3. Capture tiers

### Hot

Read only the currently rendered ChatGPT viewport. Store it as an unsealed observation and compare it against the current immutable snapshot. Hot capture is allowed to be partial and must never promote itself to `current`.

### Deep

Run the existing Camofox full acquisition path, ingest the result, and promote only a complete observation according to the frozen UCG rules.

### Recovery policy

Continuation uses a two-stage strategy:

```text
hot observation
    ↓
anchored + no material gap → evaluate
    ↓
material gap / unsealed evidence
    ↓
deep acquisition
    ↓
sealed snapshot → evaluate
```

## 4. Epistemic pipeline

```text
DISCOVERY
  ↓
Candidate reconstruction
  ↓
FALSIFICATION
  ↓
EVALUATION
  ├─ RESUMABLE
  ├─ NEEDS_MORE_DISCOVERY
  └─ BLOCKED
  ↓
CONTINUE
```

Discovery collects evidence and proposes a candidate state. Falsification explicitly tries to break that candidate using newer turns, conflicting artifacts, tool receipts, Git/runtime evidence, temporal mismatch, and alternate explanations. Evaluation decides whether the remaining evidence is enough to continue safely.

## 5. Recovery assessment

The current consumer-side assessment records:

- identity status;
- transcript/evidence status;
- last verified message ordinal and message UID;
- candidate last assistant commitment/action;
- open gaps;
- hypotheses to attack;
- contradictions;
- resume safety confidence.

`RESUMABLE` requires reliable identity, complete relevant transcript evidence, and no blocking contradiction. Unsealed live observations remain leads until they are reconciled into a sealed snapshot when the distinction matters.

## 6. Account/profile boundary

The browser profile and canonical account identity remain separate:

```text
Camofox profile: chatgpt_human_login
canonical account: camofox-human-login
conversation_uid: scoped canonical conversation
```

Account management is now explicit through the `account_profiles` table and the `context_account_login` / `context_account_status` MCP tools. Login is interactive in the persistent Camofox profile; credentials are not accepted through the UCG API.

## 7. Golden failure case

A stuck ChatGPT session is replaced by a new agent. The new agent receives a continuation request such as `Gas bro! Thinking`.

Expected behavior:

1. Identify the canonical conversation.
2. Perform hot observation of the newest rendered viewport.
3. Determine whether the hot observation is anchored to the immutable snapshot.
4. Deep-acquire when a material gap or unsealed newer state exists.
5. Reconstruct the latest verified actionable commitment.
6. Falsify that reconstruction.
7. Classify `RESUMABLE`, `NEEDS_MORE_DISCOVERY`, or `BLOCKED`.
8. Continue only after the evaluation gate permits it.

## 8. Non-goals

This layer does not become a second memory store, does not replace UCG snapshot semantics, does not claim provider-private runtime state, and does not automatically resolve semantic contradictions without evidence.
