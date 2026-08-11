# Open Questions

Decisions still waiting on the project owner, or on an external party. Everything
answered has moved to [`DECISIONS.md`](DECISIONS.md) with its rationale.

---

## Waiting on an external party

### CarDD dataset access — blocks Phase 5 only

Access requested. Until it arrives, the vehicle specialist cannot be trained and the
per-class mAP table stays empty. Phases 2, 3, 4, 6, 7, 8 and 9 are all independent of
it and proceed regardless — the specialist plugs into an interface that already exists
and is already tested against a mock.

If access is refused or arrives too late, the fallback is stated in ADR-003: ship the
architecture with no specialist and let the honesty behaviour itself be the
demonstration.

### GitHub repository

Not yet created. Local commits are accumulating on `main`. When you create
`biovision` as a public repository, the remote can be added and pushed. I have not
created it or pushed anything — that is an outward-facing action and yours to take.

---

## Needs a decision from me, reported back to you

### Q5b — which plate detector

You approved the "measure and publish the miss rate" variant, and picking the detector
is my call. Faces are settled: **YuNet** (OpenCV Zoo, permissive, CPU-fast).

Plates are the harder half. I will evaluate candidates during Phase 2 and report back
with the miss rate rather than picking silently, because the outcome changes what the
README may claim. If nothing clears a usable bar, the honest result is that plates are
not blurred, `plate_detector` stays `null` in every response, and the README says so —
the schema already enforces that a non-zero blur count requires a named detector, so
this cannot be fudged.

---

## Needed before Phase 9

### VPS details

You are collecting these. The list: OS and distribution, whether Docker and the
compose plugin are installed, whether ports 80 and 443 are free, and how deployment
happens — my access, or a script you run.

DNS: you are opening the A record for `api.biovision.bilalgurkansanli.com` today, which
takes propagation off the critical path. Caddy needs that record resolving before it
can obtain a certificate.

---

## Environment

`pnpm` is not installed on this machine. `corepack enable` is approved and will run at
the start of Phase 8.
