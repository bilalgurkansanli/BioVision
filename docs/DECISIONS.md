# Decision log

One entry per decision that is expensive to reverse. Each records what was decided,
why, and what would make us revisit it. Questions still open live in
[`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md).

---

## ADR-001 — Single repository

**Decided:** backend, frontend, infra and docs live in one repository.

**Why:** the response schema is authored in Python and consumed in TypeScript. In one
repo a schema change and its consumer land in the same commit and CI fails the pair
together; across two repos, contract drift is silent — the exact failure this project
claims to prevent. Vercel builds from a subdirectory, so deployment is not coupled.
No monorepo tool (Turborepo/Nx/workspaces): Python and TypeScript share no package
manager, so such a tool would add configuration without removing any.

**Revisit if:** the frontend needs a non-AGPL license or a separate contributor set.

---

## ADR-002 — Four domains in v1

**Decided:** `vehicle`, `building`, `phone_screen`, `other`. `parcel` dropped.

**Why:** each domain costs ~75 evaluation and calibration images to source and label.
The architecture is built so a domain is a one-line addition, which makes starting
narrow cheap to reverse — the opposite of the usual scope trade-off. `parcel` remains
present as a router prompt inside `other`.

---

## ADR-003 — Train the vehicle specialist ourselves

**Decided:** fine-tune YOLO-seg on CarDD on a free Colab T4 rather than adopting a
public checkpoint. The split and its seed are pinned in
`notebooks/train_cardd_yolo.ipynb`; the dataset is not redistributed.

**Why:** a public checkpoint has an unknown train/test split. Any leakage between it
and our evaluation split would make the per-class mAP table unverifiable — and that
table is the project's headline claim. An unverifiable specialist is worse than no
specialist, because it converts the honest answer into a confident wrong one.

**Consequence:** Phase 5 is blocked on the CarDD access request. Every other phase is
independent of it and proceeds regardless.

---

## ADR-004 — Claude Haiku 4.5 for the fallback, capped at $5/month

**Decided:** `claude-haiku-4-5-20251001`. Hard ceiling of 5 USD per month as a
literal constant in `budget.py`. Warning logged at 80%; at 100% the VLM is disabled
and fallback requests return `503 service_degraded`.

**Why:** vision-capable, inexpensive, one well-documented SDK. The client sits behind
the `VLMClient` protocol, so switching providers is a one-file change.

**Note:** a ceiling that degrades the service is the point. The specialist path keeps
returning 200 when the budget is gone.

---

## ADR-005 — Images are referenced by manifest, not committed

**Decided:** evaluation and calibration images are recorded in `manifest.csv`
(source URL, license, SHA-256) and fetched locally. The 20 golden-set images are the
exception: photographed by the author, committed, and covered by the project license.

**Why:** committing third-party photographs to a public AGPL repository is a
licensing problem, not a technicality. The golden set has to be committed because it
must run in CI without a network fetch — so it must be material we own outright.

**Recorded in:** [`NOTICE.md`](../NOTICE.md). The AGPL text in `LICENSE` is left
verbatim; asset licensing belongs in a NOTICE file, which is the convention and
avoids editing the license itself.

---

## ADR-006 — Redaction is measured and published, not asserted

**Decided:** faces via YuNet; plate detector still to be selected. Both are measured
on a small test set and their **miss rate is published in the README**. If no
trustworthy plate detector is found, plates are not blurred and the response says so.

**Why:** the KVKK claim is only as strong as the detector behind it. `Privacy` carries
`face_detector` / `plate_detector` fields where `null` means "no redaction of that
class was applied", and a schema validator rejects a non-zero blur count without a
named detector. Claiming protection that did not run would be the same failure the
project exists to avoid.

---

## ADR-007 — Anonymous demo access, no VLM

**Decided:** `/v1/analyze` is open to anonymous callers at 20 requests per IP per
day. Anonymous traffic may use the specialist path but never the VLM. Sign-in is
required for history and for the fallback description.

**Why:** an executive opening the demo link should not hit a sign-in wall. Splitting
VLM access by authentication is what makes a public link safe to publish: anonymous
traffic cannot spend the monthly budget regardless of volume.

---

## ADR-008 — Seven-day retention, deletion endpoints in v1

**Decided:** blurred derivatives and their rows are deleted after 7 days. Per-request
and delete-everything endpoints ship in v1.

**Why:** a retention claim without a stated period and a deletion path is marketing.

---

## ADR-009 — A weak routing decision does not run a specialist

**Decided:** when the router's top confidence is below threshold, return
`domain: "unknown"`, no specialist, and `warning: low_domain_confidence`.

**Why:** running a specialist on a guessed domain and reporting confident findings for
it is the precise failure mode this project exists to avoid. The threshold comes from
Phase 4 calibration, not from hand-tuning.

---

## ADR-010 — `calibrated` and `domain_confidence_calibrated` are separate fields

**Decided:** two boolean fields, not one.

* `calibrated` — is this *result* a calibrated measurement? True only when a
  calibrated specialist produced the findings.
* `domain_confidence_calibrated` — has `domain_confidence` itself been
  temperature-scaled?

**Why:** implementing ADR-009 surfaced a genuine conflict. The original API contract
shows `calibrated: false` for a domain with no specialist, but a Phase-4 router is
calibrated even for such domains — so under one flag we would have to either call a
trustworthy confidence untrustworthy, or call a description a measurement. They are
two different facts and now have two fields. The original contract's examples remain
valid unchanged.

---

## ADR-011 — Severity is a published, uncalibrated heuristic

**Decided:** `severity` is derived from `area_ratio` by fixed thresholds (moderate at
2%, severe at 8%), defined once in `models/severity.py`, reproduced in the README,
and stamped `severity_calibrated: false` on every finding.

**Why:** CarDD carries no severity ground truth, so there is nothing to calibrate
against and no honest accuracy to report. A unit test pins the thresholds so the code
and the README cannot drift apart. No accuracy claim in this project covers this
field.

---

## ADR-012 — Specialist names must exist in code

**Decided:** `domains.yaml` may only reference names listed in
`models/specialists.KNOWN_SPECIALISTS`. An unknown name is a fatal startup error, in
the mock backend as well as the real one.

**Why:** found while writing the extensibility test. The mock backend originally built
a stand-in for whatever the YAML said, so a typo like `vehicle_yolo_` would produce a
domain that reports "no specialist available" forever — a wrong answer wearing the
costume of an honest one. The easier a one-line edit is, the more important it is that
its typo mode is loud.

---

## ADR-015 — Plate redaction deferred to Phase 5

**Decided:** v1 redacts faces (YuNet) and does **not** redact plates. Every response
carries `plate_detector: null`, and the README states plainly that plates are not
blurred.

**Why:** the plan assumed OpenCV's bundled Haar plate cascade would be available.
OpenCV 5 removed `CascadeClassifier` entirely, so it is not. The alternatives were
pinning OpenCV back to 4.x, or shipping without plate redaction.

Pinning back would buy a detector trained on Russian plates whose accuracy on Turkish
plates has never been measured — and ADR-006 says a privacy guarantee needs a number
behind it. An unmeasured detector shipped as a guarantee is worse than an absent one,
because the absent one is visible in the response.

Phase 5 brings Ultralytics for the vehicle specialist, which puts a YOLO plate
detector within reach under a licence this project already complies with. The
`Redactor` takes an optional plate detector today, so this is a constructor argument
rather than a rewrite.

**Revisited at Phase 5 — still not shipped.** Ultralytics arrived as planned, but a
YOLO plate detector needs a *checkpoint*, and there is no plate checkpoint whose
training data and accuracy we can vouch for. Training one needs an annotated plate
dataset we do not have, and CarDD does not contain plate boxes.

So the position is unchanged and now has a second confirmation behind it: **plates are
not redacted in v1.** `plate_detector` stays `null`, the README says so plainly, and
the schema still refuses a blur count without a named detector. Moving this to v2 with
its own annotated set is the honest resolution; quietly shipping an unmeasured
detector to close the gap is not.

---

## ADR-016 — Perceptual hash implemented, not imported

**Decided:** `pipeline/phash.py` implements DCT-based pHash directly rather than
depending on `imagehash`.

**Why:** `imagehash` depends on scipy solely for its DCT, which adds roughly 40 MB to
an image that is already deploying to a small VPS. OpenCV is already a dependency and
`cv2.dct` computes the same transform. pHash is short and well specified, and the
implementation is pinned by tests covering the properties that actually matter:
stability across re-encoding, format changes, resizing and brightness shifts, and
separation between distinct photographs.

---

## ADR-017 — Mosaic rather than Gaussian blur

**Decided:** redacted regions are downsampled to blocks and scaled back up.

**Why:** a Gaussian blur is a convolution and is at least partly invertible, so
"blurred" personal data can be recoverable. Mosaicking genuinely discards the
information. A test asserts that every pixel within a block is identical, which a
blur would not satisfy.

---

## ADR-018 — One CLIP encoder, shared by both zero-shot layers

**Decided:** the gate and the router hold the same `ClipEncoder` instance, and the
encoder caches the image embedding for the duration of a request (keyed by perceptual
hash).

**Why:** two reasons, one about memory and one about latency.

Memory: each worker holds its own copy of every model, and the encoder is the largest
single allocation. Measured at ~1.1 GB resident per worker with one encoder. Two
encoders per worker, times two workers, would be most of the 8 GB box before YOLO
arrives in Phase 5.

Latency: the gate and the router are different questions asked of the *same*
embedding. The first benchmark showed each layer encoding the image separately —
gate 108 ms, router 101 ms — for an identical result. Caching brought end-to-end from
~346 ms to ~242 ms. The measurement is what found this; it was not visible in review.

The cache is a single entry stored as one tuple, so a concurrent overwrite cannot pair
a key with another request's embedding.

---

## ADR-019 — ViT-B/32 rather than a larger backbone

**Decided:** `ViT-B-32` / `laion2b_s34b_b79k` via open_clip.

**Why:** the smallest CLIP variant with usable zero-shot behaviour — ~600 MB, ~108 ms
per image encode on CPU. Larger backbones score better on zero-shot benchmarks and do
not fit a latency budget that has to stay under 3 s end-to-end to justify staying
synchronous (ADR-013). Both layers sit behind protocols, so swapping in SigLIP is a
constructor change if Phase 4 shows the routing accuracy is not good enough.

**Revisit if:** Phase 4's confusion matrix shows the router failing in ways a better
encoder would fix, and the latency budget still has room.

---

## ADR-020 — The description cache matches near, not exact, at 4 bits

**Decided:** a cached description is reused when the perceptual hashes are within 4
bits, not only when they are identical.

**Why:** the first implementation matched exactly and a test caught that it missed
re-encoded copies — the case the cache exists for. Measured after full ingestion
(resize + JPEG re-encode):

* same photograph at JPEG quality 95 / 60 / 40 and PNG: **0-2 bits apart**
* different photographs: **18-30 bits apart**

4 sits inside that gap with room on both sides. The asymmetry is deliberate: a false
match serves one photograph's description for another, which is a correctness bug,
while a miss costs $0.0028. When in doubt the threshold tightens rather than widens.

**Revisit at:** the golden set. These numbers come from synthetic fixtures; real
photographs may separate less cleanly.

---

## ADR-021 — The monthly budget is divided by the worker count

**Decided:** each worker's ceiling is `monthly_limit / workers`.

**Why:** the counter lives in process memory, so two workers would each spend the
full $5 and the month would cost $10 — a ceiling that does not hold is not a ceiling.
Dividing makes the total correct however the traffic is distributed.

**Cost:** a busy worker cannot borrow an idle worker's slice, so the effective limit
is slightly conservative under uneven load. Acceptable while the counter is in-memory;
Phase 7 moves it to Postgres and removes the need for the split.

---

## ADR-022 — Authorisation lives in Postgres, not in handlers

**Decided:** every Supabase call is issued under the caller's own access token, and
no handler filters by `user_id`. Row-level security scopes reads and deletes. The
service-role key appears only in the retention job, never on a request path.

**Why:** a WHERE clause is something a future refactor can drop, and the bug is
silent — the endpoint keeps working and starts returning other people's rows. An RLS
policy denies the query outright, so the API can have that bug and still not leak.
`list_for_user` deliberately sends no `user_id` filter, so nobody reads the code and
concludes the filter is what provides the isolation.

**Consequence:** the `CurrentUser` object carries the raw token, not just an id.
Reaching for the service-role key on a request path would make every policy in the
database decorative.

**Not yet demonstrated.** The API-side tests prove the API does not undermine RLS;
they cannot prove the policies are correct. `test_rls_live.py` does, against a real
project, and has not run yet.

---

## ADR-023 — A cross-user delete returns 404, not 403

**Decided:** an analysis belonging to someone else is reported as absent.

**Why:** 403 confirms the id exists, which is a small information leak that costs
nothing to avoid. Under RLS the row is genuinely invisible to the caller, so "not
yours" and "not there" are the same fact — 404 is the accurate answer, not a
euphemism.

---

## ADR-024 — Anonymous analyses are never stored

**Decided:** an unauthenticated analysis is returned and forgotten. No row, no image.

**Why:** nobody could ever retrieve or delete it. Keeping the image would be
collecting personal data with no owner, no access path, and no deletion path —
retention and deletion promises that could not be honoured because there is nobody to
honour them to.

---

## ADR-025 — CarDD-derived weights are not published until the PIC Lab authorises it

**Decided:** the fine-tuned vehicle checkpoint is **not** put on a GitHub release, and
`fetch_weights.py` does not offer to download it. Whoever wants it trains it themselves
from their own CarDD copy, using the committed notebook. The deployment step copies the
file to the server by hand.

**Why:** the CarDD licence, read rather than assumed, says the user "shall not, transfer
in any way, permanently or temporarily, distribute or broadcast all or part of the
dataset to third parties without prior authorization of the PIC Lab." Whether a set of
weights fine-tuned on the data counts as "part of the dataset" is not addressed. The
licence predates the question.

Publishing a 20 MB checkpoint on a public repository is not reversible — it can be
mirrored within hours — so the asymmetry decides it. Asking costs one line in the access
email; guessing wrong costs a licence violation against a research lab whose data the
project depends on, in a repository that exists to demonstrate care.

**Also from reading the licence:** commercial use requires prior authorisation, and
"testing commercial systems" is named explicitly. Demonstrating this project as a
portfolio piece is not commercial use, but deploying it as, or inside, a working
insurance product would be — and that is exactly the direction the project points. The
authorisation to ask for is therefore both: redistribution of derived weights, and any
commercial evaluation.

**Revisit when:** the PIC Lab answers. If they authorise redistribution, publish the
checkpoint as a release artifact with the citation attached and update
`fetch_weights.py`. If they decline or do not answer, this stands.

**Consequence for the README:** the per-class mAP table can still be published — metrics
are measurements about the data, not the data — with the required citation. Anyone
reproducing them needs their own CarDD access, which the licence intends.

---

## ADR-013 — Synchronous request handling, no queue

**Decided:** no broker, no worker pool, no job state in v1.

**Why:** a queue adds a broker, a worker pool, job state, client-side polling, and a
second failure surface — in exchange for nothing at this load.

**Revisit if:** end-to-end p95 exceeds 3 s, or sustained concurrent requests exceed
2x the worker count. Section 7.4 of the README is the instrument.

---

## ADR-014 — At most two uvicorn workers

**Decided:** two. Enforced by a memory limit in `docker-compose.prod.yml`.

**Why:** each worker loads its own full copy of CLIP and YOLO. Two fit in 8 GB; four
exhaust RAM and take the machine down. This is a hardware fact, not a throughput knob,
and the comment saying so is repeated at every place workers are configured.
