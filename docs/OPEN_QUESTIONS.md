# Open Questions

What is still blocked, and on whom. Everything answered has moved to
[`DECISIONS.md`](DECISIONS.md) with its rationale.

All ten phases are built, and everything that could be verified without your data or
your server has now been verified. Nothing below is missing code — every item here needs
either **photographs that do not exist yet** or **a machine to deploy onto**.
Each unrun measurement leaves an empty cell in the README rather than an estimate.

---

## Ordered by what unblocks the most

### 1. An annotated router evaluation set — unblocks every accuracy number

~50 images per domain. `scripts/eval_router.py` and `scripts/calibrate_router.py` have
now been **run** — against a throwaway synthetic set, purely to find out whether they
execute at all. They do, and they print exactly the tables the README publishes:
confusion matrix, per-domain accuracy, ECE before and after temperature scaling, and the
reliability diagram. No number from that run is published anywhere, and the set was
deleted.

Running them also added a floor. Twelve synthetic images produced a fitted temperature
and a file that made the API report `calibrated: true`; a fit below 100 samples is now
refused outright. ECE over twelve samples is noise, and labelling noise "calibrated" is
precisely the failure this project exists to avoid.

Until this exists, **every response carries `calibrated: false`** — correctly, because no
temperature file has been fitted. The confidence numbers shown are raw softmax outputs
and the UI labels them as such.

This is the difference between "the architecture is honest" and "the architecture is
honest *and* here is how well it performs".

### 2. A redaction evaluation set — unblocks the privacy number

30-50 photographs at `data/redaction_eval/` with face boxes as `filename,class,x,y,w,h`.
`scripts/eval_redaction.py` prints the miss-rate table.

Your own photographs sidestep the licensing question entirely, the same reasoning as the
golden set. The README currently claims faces are blurred without publishing how often
that fails — which by this project's own rule is a claim without a number.

### 3. VPS details — unblocks deployment and the only real latency figure

Needed: OS and distribution, whether Docker and the compose plugin are installed, whether
ports 80 and 443 are free, and how deployment happens — my access, or a script you run.

The published 266 ms p95 was measured **on a development machine**, and the README says
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
