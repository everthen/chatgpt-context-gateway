# UCG Selection Downstream Gate v0.1

## Fresh rerun

This gate reruns the observed contrastive cases through the live 9Router OpenAI-compatible endpoint rather than the retired benchmark-specific route.

- answer model: `ag/gemini-3.8-flash`
- judge model: `ag/claude-sonnet-4-6`
- transport: `http://127.0.0.1:20128/v1/chat/completions`
- answer generations: 9/9 successful
- blind judge cases: 3/3 successful
- cases: NS-04, XP-02, XP-04

The same dedicated UCG benchmark API key was allow-listed for the model set.

## Bundle arms

| Case | Weak | Observed strong | Selection reference |
|---|---|---|---|
| NS-04 | `ns04.gold` | `ns04.dist1 + ns04.gold` | `ns04.gold + ns04.dist1` |
| XP-02 | `xp02.claude + xp02.openai` | `xp02.claude + xp02.dist + xp02.openai` | `xp02.openai + xp02.claude + xp02.dist` |
| XP-04 | `xp04.gold` | `xp04.dist + xp04.gold` | `xp04.gold + xp04.dist` |

For NS-04 the deterministic reference selector uses the synthetic fixture relation mapped to the real downstream key `ns04.dist1`.

## Blind-judge result

The judge used the same within-run formula as the existing answer-quality harness:

`0.25*claim_coverage + 0.40*factual_correctness + 0.25*groundedness + 0.10*abstention_correctness`

Observed means:

- weak: **0.9583**
- observed strong: **0.8000**
- selection reference: **0.9083**

These are diagnostic within-run numbers only. They should not be compared to earlier answer-quality experiments that used a different judge/scoring artifact.

### Case findings

#### NS-04

All three bundles scored 1.0.

Interpretation: this case is not discriminative under the current answer prompt. The answer model can answer correctly from the direct gold evidence and ignore the contrastive alternative.

This does NOT invalidate the observed downstream evidence from the earlier Sonnet-answer experiment where `ns04.gold` scored 0.775 and `ns04.dist1 + ns04.gold` scored 1.0. It means the fresh Gemini-answer setup did not reproduce that sensitivity.

#### XP-02

- weak: **1.0**
- observed strong: **0.675**
- selection reference: **1.0**

The selection reference bundle was fully correct in the fresh run.

Important nuance: adding `xp02.dist` can hurt a naive answer consumer when the model treats contrastive evidence as ordinary positive evidence. The selection layer is therefore not enough by itself; the answer consumer needs relation/role semantics.

#### XP-04

- weak: **0.875**
- observed strong: **0.725**
- selection reference: **0.725**

The selected bundle correctly contains the wrong-account boundary evidence, but the current answer model can still cite `xp04.dist` as factual authority. The blind judge correctly penalizes that behavior under the present scoring contract.

A refined prompt that marked `xp04.dist` as control-only caused the model to stop citing it, but the judge then exposed a second micro-seam: the positive account-isolation claim itself must be grounded in valid main-account evidence.

## Architectural conclusion

The selection layer needs an explicit distinction between:

1. **answer-visible evidence** — may support/cite substantive answer claims;
2. **control/boundary evidence** — retained for selection/audit/rejection semantics, but not automatically answer-visible;
3. **selection relations** — explain why control evidence exists and what it constrains.

This suggests the next ContextBundle contract should expose separate lanes rather than a flat evidence list.

Conceptually:

```text
ContextBundle
├── answer_context[]
├── control_context[]
└── epistemic_relations[]
```

For XP-04:

```text
answer_context:
  xp04.gold

control_context:
  xp04.dist  # wrong-account boundary; not answer authority

relation:
  xp04.gold --required_boundary_contrast--> xp04.dist
```

For contrastive design cases such as XP-02, some contrastive evidence may remain answer-visible, but it must carry a role that tells the downstream model it is a rejected/alternative claim rather than positive authority.

## Decision

**PARTIAL PASS — deterministic selection is promising, but downstream consumption semantics are now the binding seam.**

Confirmed:

- live downstream generation works again through 9Router;
- selection reference reproduces the stronger XP-02 bundle and preserves the required contrast;
- account-isolation evidence can be retained without being allowed to serve as positive answer authority, provided the ContextBundle distinguishes control from answer evidence.

Not proven:

- a universal answer-consumer contract across all contrastive roles;
- NS-04 discriminative benefit under the current answer-model prompt;
- production ContextBundle multi-lane integration.

## Next gate

Implement and test a multi-lane ContextBundle contract:

`answer_context + control_context + epistemic_relations`

Then rerun XP-02 and XP-04 with the same answer model and judge.

Do not wire this directly into production retrieval yet.
