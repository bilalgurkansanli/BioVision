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
