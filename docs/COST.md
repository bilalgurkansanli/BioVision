# Cost

Per-request cost, derived rather than guessed, and the mechanisms that keep the
monthly total under a fixed ceiling.

---

## The shape of the bill

Only one thing in BioVision costs money per request: the fallback VLM. Everything
else — image processing, the gate, the router, the vehicle specialist — runs on a
VPS that costs the same whether it serves zero requests or ten thousand.

That produces a useful property: **the expensive path is the one that runs rarely,
by construction.** Vehicle photographs, the primary use case, have a specialist and
therefore never reach the VLM. There is no code path from the specialist branch to
the paid API, and a schema validator rejects a response carrying both a
`specialist_model` and a `vlm_description`.

| Path | Marginal cost |
|---|---|
| Vehicle (specialist runs) | **$0** |
| Gate rejection (422) | **$0** |
| Low confidence → `unknown` | **$0** |
| Anonymous caller, any domain | **$0** — anonymous traffic cannot reach the VLM |
| Repeated image (cache hit) | **$0** |
| Authenticated fallback, first time | see below |

---

## Deriving the per-request cost

Model: **Claude Haiku 4.5** (`claude-haiku-4-5`) at list prices — **$1.00 per
million input tokens, $5.00 per million output tokens**.

**Input.** Claude bills an image at roughly `width × height / 750` tokens. The
stored derivative is bounded at 1280 px on the long edge, so a 4:3 photograph is
1280×960:

```
image:   1280 × 960 / 750  ≈  1,638 tokens
prompts: system + user     ≈    150 tokens
                              ─────────────
total input                ≈  1,790 tokens
```

**Output.** Capped at 400 tokens; a two-to-three sentence description lands around
200.

```
input:   1,790 × $1.00 / 1,000,000  =  $0.00179
output:    200 × $5.00 / 1,000,000  =  $0.00100
                                      ─────────
per fallback request                =  $0.00279
```

**≈ $0.0028 per described image.** Output tokens are five times the price of input
but there are far fewer of them, so the image dominates — which is why the 1280 px
bound is a cost control as much as a storage one.

| Item | Value |
|---|---|
| Cost per request — vehicle path (no VLM) | **$0.00** |
| Cost per request — fallback path | **≈ $0.0028** |
| Monthly ceiling | **$5.00** |
| Fallback requests the ceiling buys | **≈ 1,790** |

**These are derived from list prices and the token formula, not measured against an
invoice.** They will be replaced with observed figures once the VLM has served real
traffic. The measured cache hit rate — the number that decides how far the ceiling
actually stretches — needs traffic to exist at all, and is left empty until then.

| Measured | Value |
|---|---|
| Observed mean cost per fallback request | _not yet measured_ |
| Cache hit rate | _not yet measured_ |
| Fallback share of total requests | _not yet measured_ |

---

## The four controls

**1. The VLM is unreachable from the specialist path.** Not a policy — there is no
call site. The common case is free.

**2. Anonymous callers never reach it.** `/v1/analyze` is open at 20 requests per
IP per day so the demo link works without a sign-in wall, but the fallback requires
authentication. A published link cannot spend the budget regardless of traffic.

**3. A perceptual-hash cache.** A photograph already described is answered from
memory. The key is the pHash *and the response language* — without the language a
cached Turkish description would be served to a request that asked for English,
which is a correctness bug wearing the costume of a saving.

Matching is near, not exact, within a measured threshold. After full ingestion
(resize + JPEG re-encode), the same photograph at different qualities lands 0–2
bits apart while different photographs sit 18–30 bits apart. The threshold is **4
bits** — inside that gap with room on both sides, and deliberately far below the
nearest observed cross-image distance, because a false match serves the wrong
description while a miss only costs $0.0028.

**4. A hard monthly ceiling.** $5.00. At 80% a warning is logged; at 100% the VLM
is switched off and fallback requests return `503 service_degraded`. The specialist
path keeps returning 200 — the service degrades, it does not fail.

The ceiling is divided by the worker count, because the counter lives in process
memory and two workers would otherwise each spend the full $5. The cost of that
split is that a busy worker cannot borrow an idle one's slice; Phase 7 moves the
counter to Postgres and removes the need for it.

---

## Fixed monthly cost

| Item | Cost |
|---|---|
| VPS (4 vCPU / 8 GB / 100 GB) | your existing plan |
| Vercel (frontend) | $0 — hobby tier |
| Supabase | $0 — free tier |
| VLM ceiling | ≤ $5.00 |

The marginal cost of the primary use case is zero, and the one path that costs
money has a ceiling that cannot be exceeded.
