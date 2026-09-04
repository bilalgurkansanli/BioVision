# Open Questions

What is still blocked, and on whom. Everything answered has moved to
[`DECISIONS.md`](DECISIONS.md) with its rationale.

All ten phases are built, and everything that could be verified without your data or
your server has now been verified. Nothing below is missing code — every item here needs
either **photographs that do not exist yet** or **a machine to deploy onto**.
Each unrun measurement leaves an empty cell in the README rather than an estimate.

---

## Ordered by what unblocks the most

### 1. ~~An annotated router evaluation set~~ — **answered, 2026-08-16**

240 images: 30 per domain in each of `router_eval` and `router_calib`, plus 115
out-of-scope images in `gate_eval`. Sources, licences and the reason each was chosen
are in ADR-028; the numbers are in README sections 6, 7.1 and 7.2.

**Router: 95.0% top-1.** **Gate: 3.3% false rejects, 7.0% false accepts.**

**Calibration was measured and refused.** Temperature scaling fitted T = 1.376 on the
held-out calibration split and made ECE *worse* on the evaluation split — 0.0405 to
0.0603. The reliability diagram shows why: the router is mildly under-confident, so
lowering its confidence moves it the wrong way. `calibrate_router.py` now refuses to
write a temperature that fails this check, and **every response still carries
`calibrated: false`** — no longer because nothing was fitted, but because what was
fitted did not earn the word.

**What remains open here** is not the set but its breadth. `phone_screen` scores 100%
from one source with one photographic style; `building` is one institution's archive.
README section 7.1 states both. Photographs from a real intake would test what these
cannot.

**There is now a way to collect them.** `POST /v1/requests/{id}/corrections` records
what a user says the model got wrong, and an explicit checkbox -- off by default --
keeps that photograph past the 7-day window so the correction stays attached to
something. README section 8.0 and `0003_corrections.sql` carry the design and the three
things it deliberately does not do. **This does not answer the question**: it is a
mechanism with no rows in it, and the item stays open until there are enough of them to
measure against.

### 2. ~~A redaction evaluation set~~ — **answered, 2026-08-16**

Built from WIDER FACE's validation split rather than from your photographs: 50 images,
95 annotated faces. **Miss rate 3.2%**, five false positives. README section 5.1 carries
the number and, next to it, the filter that produced it — 1–6 faces per image, each at
least 40 px. WIDER FACE includes stadium crowds at twelve pixels a face; measuring
against those would report on a benchmark rather than on this system's intake, so the
subset is stated as part of the claim rather than buried.

Your own photographs would still be worth having, for a reason the number does not
capture: WIDER FACE is not photographs of damaged cars with a bystander in frame. It is
the closest available proxy, and it is a proxy.

### 3. VPS details — unblocks deployment and the only real latency figure

Needed: OS and distribution, whether Docker and the compose plugin are installed, whether
ports 80 and 443 are free, and how deployment happens — my access, or a script you run.

The published 372 ms p95 was measured **on a development machine**, and the README says
so. `bench_latency.py` on the VPS replaces it with a number that means something.

DNS: the A record for `api.biovision.bilalgurkansanli.com` must resolve before Caddy can
obtain a certificate, so it is worth opening early.

The image now builds and runs (2.27 GB, 9 s cold start with or without network). Its
first run found four defects that no test could have caught — see `docs/PLAN.md`, Phase 9.
What remains untested is this specific machine: DNS, certificates, reboot survival, and
whether 8 GB really holds two workers under load.

---

## Waiting on an external party

### CarDD dataset access — no longer blocking

Superseded. The specialist is trained on VehiDE (ADR-026) and the per-class table
is published. CarDD remains worth requesting only for the comparison it would
allow, not because anything waits on it.

---

## Settled

| Item | Outcome |
|---|---|
| GitHub repository | Created and pushed. `main`, private for now. AGPL obliges source only on distribution or network use — publishing becomes necessary when the API goes live. |
| `pnpm` | Installed to `%LOCALAPPDATA%\pnpm-bin`; `corepack enable` failed with EPERM. |
| Row-level security | **Verified.** `uv run python -m scripts.rls_check` stands up a local Supabase stack and runs the seven live assertions; 7/7. A hosted project is needed to deploy, no longer to check this. |
| The production image | **Builds and runs.** Four defects found and fixed on the first run. |
| Plate detector | **None in v1.** OpenCV 5 removed `CascadeClassifier`, so the planned cascade does not exist to use. Pinning back to 4.x buys a detector trained on Russian plates with no measurement on Turkish ones. Every response carries `plate_detector: null` and the README says plates are not blurred. ADR-015. |
| Vehicle specialist | **Trained.** yolo11s-seg on VehiDE, 100 epochs, evaluated on the held-out validation set. mAP@50 ranges from 0.239 (scratch) to 0.782 (glass_shatter); all seven rows are in README §7.3. |
| Face detector | **YuNet** — MIT, 230 KB, CPU-fast, integrated and working. Miss rate unmeasured, see item 2. |
