# Open Questions

What is still blocked, and on whom. Everything answered has moved to
[`DECISIONS.md`](DECISIONS.md) with its rationale.

All ten phases are built. Nothing below is missing code — every item here is a
**measurement that has not been run** or an **environment that does not exist yet**.
That distinction is the point: the code paths are tested, and each unrun measurement
leaves an empty cell in the README rather than an estimate.

---

## Ordered by what unblocks the most

### 1. A Supabase project — unblocks the largest single gap

Everything is written: the schema, the RLS policies, the retention job, the token-scoped
repository, and `tests/integration/test_rls_live.py`, which asserts the policies directly
against Postgres with no API in the path. It is skipped without a project.

**Until it runs, "one user cannot read another's data" is a design, not a demonstration.**
That is the strongest claim in the README and the weakest evidence behind it. It also
unblocks Google sign-in and the history page, which currently degrade to "sign-in is not
configured in this environment".

Needs: a free-tier project, the two migrations applied, Google OAuth enabled, and four
values in `.env`. Roughly fifteen minutes, and nothing external.

### 2. An annotated router evaluation set — unblocks every accuracy number

~50 images per domain. `scripts/eval_router.py` and `scripts/calibrate_router.py` are
written and print exactly the tables the README publishes: confusion matrix, per-domain
accuracy, ECE before and after temperature scaling, and the reliability diagram.

Until this exists, **every response carries `calibrated: false`** — correctly, because no
temperature file has been fitted. The confidence numbers shown are raw softmax outputs
and the UI labels them as such.

This is the difference between "the architecture is honest" and "the architecture is
honest *and* here is how well it performs".

### 3. A redaction evaluation set — unblocks the privacy number

30-50 photographs at `data/redaction_eval/` with face boxes as `filename,class,x,y,w,h`.
`scripts/eval_redaction.py` prints the miss-rate table.

Your own photographs sidestep the licensing question entirely, the same reasoning as the
golden set. The README currently claims faces are blurred without publishing how often
that fails — which by this project's own rule is a claim without a number.

### 4. VPS details — unblocks deployment and the only real latency figure

Needed: OS and distribution, whether Docker and the compose plugin are installed, whether
ports 80 and 443 are free, and how deployment happens — my access, or a script you run.

The published 266 ms p95 was measured **on a development machine**, and the README says
so. `bench_latency.py` on the VPS replaces it with a number that means something.

DNS: the A record for `api.biovision.bilalgurkansanli.com` must resolve before Caddy can
obtain a certificate, so it is worth opening early.

The image has also never been built — Docker Desktop was unavailable here. That is a
plausible source of first-deployment surprises.

---

## Waiting on an external party

### CarDD dataset access — blocks the vehicle specialist only

Access requested, not yet granted. The specialist plugs into an interface that already
exists and is already tested against a mock, so nothing waits on it structurally: with no
checkpoint, the vehicle domain reports `specialist_model: null` — the same honest answer
every other domain gets.

If access is refused or arrives too late, the fallback stated in ADR-003 stands: ship the
architecture with no specialist and let the honesty behaviour be the demonstration. It is
a weaker demo but not a broken one.

---

## Settled

| Item | Outcome |
|---|---|
| GitHub repository | Created and pushed. `main`, private for now. AGPL obliges source only on distribution or network use — publishing becomes necessary when the API goes live. |
| `pnpm` | Installed to `%LOCALAPPDATA%\pnpm-bin`; `corepack enable` failed with EPERM. |
| Plate detector | **None in v1.** OpenCV 5 removed `CascadeClassifier`, so the planned cascade does not exist to use. Pinning back to 4.x buys a detector trained on Russian plates with no measurement on Turkish ones. Every response carries `plate_detector: null` and the README says plates are not blurred. ADR-015. |
| Face detector | **YuNet** — MIT, 230 KB, CPU-fast, integrated and working. Miss rate unmeasured, see item 3. |
