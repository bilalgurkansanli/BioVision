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

## Answered during Phase 2

### Q5b — which plate detector → **none in v1**

Faces: **YuNet**, integrated and working (MIT, 230 KB, CPU-fast).

Plates: none. The plan assumed OpenCV's bundled Haar plate cascade; **OpenCV 5
removed `CascadeClassifier` entirely**, so it does not exist to use. Pinning OpenCV
back to 4.x would buy a detector trained on Russian plates with no measurement on
Turkish ones — and your own rule was that a privacy guarantee needs a number behind
it. Deferred to Phase 5, where Ultralytics arrives anyway. Full reasoning in
[`DECISIONS.md`](DECISIONS.md) ADR-015.

Every response now carries `plate_detector: null` and the README says plates are not
blurred.

---

## Needed for the redaction miss-rate table

`scripts/eval_redaction.py` is written and prints the table the README publishes, but
there is no annotated set to run it against. It needs perhaps 30-50 photographs at
`data/redaction_eval/` with face boxes annotated as `filename,class,x,y,w,h`.

Your own photographs would work and would sidestep the licensing question entirely —
the same reasoning as the golden set. Until this exists the README carries an empty
table marked "not run", which is the honest state but not a good one to demo.

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
