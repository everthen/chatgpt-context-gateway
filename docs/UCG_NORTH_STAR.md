# Tujuan Saat Ini & Selanjutnya — UCG

Status: NORTH STAR / CURRENT PRODUCT GATE
Date: 2026-10-07

## Current Core Goal

> **Buktikan apakah UCG membuat LLM benar-benar lebih mampu mengingat kembali context yang relevan, dengan lebih sedikit noise, dibanding native memory/context saja.**

Ini adalah gate utama sebelum UCG diperluas menjadi produk SaaS yang lebih luas.

UCG tidak dimaksudkan untuk menggantikan native memory LLM. Model tetap menjadi pihak yang menilai relevansi, merekonsiliasi konflik, melakukan reasoning, dan membuat keputusan akhir.

UCG menyediakan context/evidence substrate yang dapat dipanggil kembali saat diperlukan.

## Core Capability: Context Rehydration

UCG harus mampu membantu LLM:

1. mempertahankan continuity pada sesi chat panjang ketika context lama mulai sulit dijangkau;
2. merehidrasi context dari sesi A/B/C ke sesi baru berdasarkan trigger user atau kebutuhan yang terukur;
3. membawa context/evidence dari model/provider A ke model/provider B secara provider-neutral;
4. menggabungkan native LLM memory + UCG, tanpa menjadikan UCG sebagai hakim tunggal;
5. menjaga relevance, chronology, freshness, provenance, dan evidence identity.

Model mental:

```
Native LLM Memory
        +
       UCG
        |
        v
   LLM reasoning
        |
        v
  Final decision
```

## Automatic Recall Is a Hypothesis, Not a Requirement

Mode user-triggered recall adalah baseline yang aman.

Automatic / model-triggered recall hanya boleh dipromosikan menjadi core capability jika benchmark menunjukkan bahwa ia:

- meningkatkan recall/relevance;
- tidak meningkatkan irrelevant-context noise secara material;
- tidak menurunkan answer quality;
- memiliki biaya/latency yang masuk akal.

Candidate modes:

- explicit user trigger;
- assisted/model-triggered recall;
- gated/automatic recall.

Jangan menganggap automatic recall lebih baik sebelum dibuktikan.

## Primary Evaluation

Bandingkan minimal:

- native memory/context only;
- native memory/context + UCG.

Ukur:

- context recall;
- relevance / precision;
- completeness;
- chronology;
- conflict handling;
- provenance;
- false retrieval / irrelevant-context rate;
- answer quality;
- token cost;
- latency;
- cross-session continuity;
- cross-model continuity.

### Critical quality principle

> **Context tambahan yang tidak relevan dapat menurunkan kualitas jawaban.**

Karena itu, keberhasilan UCG bukan "mengambil sebanyak mungkin memory", tetapi **mengambil context yang tepat untuk reasoning saat ini**.

## Product North Star

> **UCG = Universal Context & Evidence Layer for AI.**

UCG harus tetap berguna walaupun ChatGPT, Claude, Gemini, Perplexity, dan agent frameworks masing-masing sudah memiliki native memory.

UCG bukan sekadar "another memory API".

Nilai utamanya adalah:

- cross-provider context;
- evidence-first memory;
- context rehydration;
- provenance;
- freshness;
- portable context/evidence;
- model/provider neutrality.

## Architecture Boundary

UCG boleh memiliki intelligence/agents sendiri apabila eksperimen membuktikan bahwa hal tersebut membuat context/evidence lebih:

- portable;
- fresh;
- reliable;
- traceable;
- useful.

Tetapi intelligence yang hanya mengatur execution governance khusus Hermes tetap berada di Hermes kecuali terbukti sebagai primitive universal UCG.

## Gold Rule

Setiap fitur baru harus lolos pertanyaan:

```
FEATURE
   |
   v
Apakah membuat context/evidence
lebih portable, fresh, reliable,
traceable, atau useful?
   |
  YES -> KEEP / benchmark
   |
   NO -> jangan masukkan core
```

Filter tambahan:

> Apakah fitur ini membuat UCG lebih berguna bagi ChatGPT + Claude + Gemini + Perplexity + custom agents secara provider-neutral?

Jika ya: kandidat "gurih".

Jika hanya membuat Hermes lebih canggih: pindahkan ke Hermes.

## Next Gate After Core Proof

**Jangan lompat ke competitive bake-off atau SaaS packaging sebelum core gate di atas terbukti.**

Setelah core proof lulus:

1. **Zep bake-off** — benchmark teknis retrieval/memory/temporal/context quality.
2. **Mem0 DX** — benchmark developer experience, API, SDK, onboarding, integration.
3. **OMP compatibility** — teliti dan, bila masuk akal, dukung interoperabilitas Open Memory Protocol; jangan melawan interoperability.
4. **SaaS** — multi-tenant productization, account/project isolation, connectors, billing, operational hardening.

Framing kompetitif:

- OMP = interoperability/portable-memory protocol to study/support.
- Zep = technical benchmark.
- Mem0 = developer-experience/integration benchmark.
- Letta = stateful-agent architecture benchmark.
- OpenAI / Anthropic / Google = alasan provider-neutrality UCG bernilai.

## Final Strategic Statement

> **UCG tidak harus mengalahkan semua pemain. UCG harus menjadi layer yang tetap berguna walaupun semua pemain tersebut sudah punya memory masing-masing.**

The project is currently in:

```
CORE BUILD
   ->
CONTEXT REHYDRATION
   ->
BENCHMARK / PROVE
   ->
ONLY THEN:
Zep bake-off + Mem0 DX + OMP compatibility + SaaS
```
