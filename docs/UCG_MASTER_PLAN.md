# UCG Master Plan — Tujuan Saat Ini & Selanjutnya

**Status:** CORE BUILD → PROVE → EXPAND  
**North-star gate:** 

> Dengan UCG, apakah LLM benar-benar menjadi lebih mampu mengingat kembali context yang relevan, dengan lebih sedikit noise, dibanding native memory/context saja?

## 1. Current Goal

UCG = **Universal Context & Evidence Layer for AI**.

Core capability yang harus dibuktikan adalah **Context Rehydration**:

- long-session recall;
- new-session rehydration dari sesi A/B/C;
- cross-model / cross-provider context handoff;
- native LLM memory + UCG, tanpa UCG mengambil alih judgment.

## 2. Gold Rule

Setiap fitur baru:

```
FEATURE
  ↓
Apakah membuat context/evidence lebih
portable, fresh, reliable, traceable, atau useful?
  ↓
YES → keep / benchmark
NO  → jangan masuk core
```

Filter kedua:

> Apakah fitur membuat UCG lebih berguna bagi ChatGPT + Claude + Gemini + Perplexity + custom agents secara provider-neutral?

Jika hanya membuat Hermes lebih canggih → pindahkan ke Hermes.

**Automatic recall = hypothesis, bukan requirement.**

## 3. Master Roadmap

### P0 — Freeze & Baseline
Freeze core saat ini dan benchmark environment.

### P1 — Golden Context Dataset
Buat task nyata dengan relevant evidence + distractors.

Task families:
- Long Session
- New Session Rehydration
- Cross-Model Handoff

### P2 — Evaluation Harness
Bangun control-vs-treatment evaluation yang merekam:
- retrieval results;
- evidence/provenance;
- latency;
- token usage;
- model output.

### P3 — Native-Only Baseline
Native context/memory saja.

### P4 — Native + UCG
Explicit user-triggered UCG Context Rehydration sebagai baseline treatment.

### P5 — Failure Analysis
Cari:
- missed recall;
- false recall;
- temporal errors;
- cross-provider collisions;
- context overload;
- provenance gaps.

### P6 — Core Improvement Loop

```
Benchmark
  ↓
Failure
  ↓
Targeted change
  ↓
Regression
  ↓
Benchmark ulang
```

Jangan menambah vector DB / graph / semantic reranking hanya karena populer; lakukan berdasarkan failure evidence.

### P7 — Trigger Strategy

Bandingkan:
1. Explicit user trigger
2. Model-triggered recall
3. Gated automatic recall

Auto hanya dipromosikan jika recall meningkat tanpa degradasi material pada noise/answer quality.

### G1 — Core Gate

**PASS** bila:
- relevant recall naik;
- irrelevant retrieval terkendali;
- hasil repeatable;
- provenance tetap utuh;
- cost/latency masuk akal;
- model/user tetap memegang final judgment.

**FAIL** bila:
- gain hanya cherry-picked;
- noise meningkatkan;
- hasil tidak repeatable;
- provenance rusak;
- overhead menghapus benefit;
- UCG menjadi authority jawaban.

## 4. Setelah Core Gate Lulus

### P8 — Competitive Benchmarks

- **Zep:** technical benchmark — retrieval, temporal reasoning, context quality, latency, scale.
- **Mem0:** developer-experience/integration benchmark.
- **Letta:** stateful-agent architecture benchmark.
- **OMP:** interoperability study dan kemungkinan compatibility.
- **OpenAI / Anthropic / Google:** provider-neutrality benchmark/value.

### P9 — SaaS Productization

Multi-tenant isolation, identity/account binding, connectors, quotas, billing, observability, reliability, retention/export/delete, API/MCP.

## 5. Non-Goals Sekarang

- cryptographic proof of model reasoning;
- Hermes-specific execution governance in UCG core;
- hidden/internal memory injection into frontier models;
- vector DB without measured need;
- complex knowledge graph without measured need;
- SaaS billing/multi-tenancy before core proof.

## 6. Working Principle

Master plan = **peta**.  
Subplan = **boleh berubah** bila evidence baru muncul.  
Perubahan scope = **dicatat sebagai decision**, bukan diam-diam terjadi.

Strategic statement:

> UCG tidak harus mengalahkan semua pemain. UCG harus menjadi layer yang tetap berguna walaupun semua pemain tersebut sudah punya memory masing-masing.

Core mental model:

```
UCG → finds, verifies, assembles context/evidence
LLM → interprets, reasons, decides
```
