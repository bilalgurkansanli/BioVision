# BioVision

**A damage-analysis API that tells you what it does not know.**

BioVision takes a photograph of damage, decides which *domain* the photo belongs to
(vehicle, building, phone screen, parcel, …), runs a domain-specific expert model if
one exists — and, when one does not exist, says so explicitly instead of guessing.

> Status: **pre-alpha.** The API contract and the full image-ingestion pipeline are
> real — decode, HEIC, EXIF, orientation, perceptual hashing, face redaction, resize.
> The three analysis layers still run against deterministic mocks; real models arrive
> in Phase 3 (gate + router), Phase 5 (vehicle specialist) and Phase 6 (fallback) —
> see [`docs/PLAN.md`](docs/PLAN.md).
>
> All measurement tables below are intentionally empty. They are filled in only with
> numbers produced by the evaluation scripts in `backend/scripts/`, never by
> estimation. **If a cell is empty, the measurement has not been run yet.**

---

## 1. Why this project exists

Most damage-assessment demos report a single accuracy number and stay silent about
where they break. That number is unusable for anyone who has to underwrite risk.

BioVision is built around the opposite claim:

* Every confidence score the API returns is either **calibrated** (and the response
  says `calibrated: true`) or **not calibrated** (and the response says
  `calibrated: false`). There is no third state.
* Domains without a trained expert model return `specialist_model: null`,
  an empty `findings` array, and an explicit `warning`. The system never fabricates
  structured findings from a general-purpose model.
* The evaluation section below reports **per-class** performance, not an average that
  hides the weak classes.

---

## 2. Architecture

Three layers, evaluated in order. Each layer can reject the request.

```
        upload
          │
          ▼
   ┌──────────────┐   not a damage/object photo
   │ L0  Gate     │ ────────────────────────────►  422 out_of_distribution
   │  CLIP 0-shot │
   └──────┬───────┘
          │ passes
          ▼
   ┌──────────────┐
   │ L1  Router   │  which domain? (candidate labels come from a config file)
   │  CLIP 0-shot │  temperature-scaled → calibrated domain_confidence
   └──────┬───────┘
          │
     ┌────┴─────────────────────────┐
     │ specialist exists?           │
     ▼ yes                          ▼ no
┌──────────────────┐      ┌─────────────────────────┐
│ L2  Specialist   │      │ Fallback: cloud VLM     │
│  CarDD YOLO-seg  │      │  free-text description  │
│  → findings[]    │      │  → findings = []        │
│  calibrated:true │      │  calibrated:false       │
└──────────────────┘      │  warning: no_specialist │
                          └─────────────────────────┘
```

**The central architectural promise:** adding a new domain to the router is a
one-line change in `backend/src/biovision/domains/domains.yaml`. No code change,
no redeploy of model logic. A test enforces this.

### Layer summary

| Layer | Model | Runs on | Calibrated | Purpose |
|---|---|---|---|---|
| L0 Gate | CLIP/SigLIP zero-shot | CPU | — (threshold) | Reject selfies, screenshots, landscapes |
| L1 Router | CLIP/SigLIP zero-shot | CPU | yes (temperature scaling) | Assign a domain |
| L2 Specialist — vehicle | CarDD fine-tuned YOLO-seg | CPU | yes | 6-class damage segmentation |
| L2 Specialist — all other domains | *none* | — | no | Returns `null`, honestly |
| Fallback | Cloud VLM API | remote | no | Free-text description only |

---

## 3. The honesty contract

This is the part of the project that matters most.

**Domain with a specialist:**

```json
{
  "request_id": "uuid",
  "domain": "vehicle",
  "domain_confidence": 0.93,
  "domain_confidence_calibrated": true,
  "specialist_model": "cardd-yolo-seg-v1",
  "calibrated": true,
  "findings": [
    {
      "type": "scratch",
      "score": 0.81,
      "bbox": [120, 340, 260, 410],
      "area_ratio": 0.04,
      "severity": "minor",
      "severity_calibrated": false
    }
  ],
  "integrity": {
    "exif_datetime": "2026-03-14T10:22:00Z",
    "exif_gps_present": true,
    "device": "iPhone 14",
    "duplicate_of": null
  },
  "privacy": { "faces_blurred": 0, "plates_blurred": 1 },
  "timing_ms": { "gate": 60, "router": 95, "specialist": 380, "total": 610 }
}
```

**Domain without a specialist:**

```json
{
  "request_id": "uuid",
  "domain": "building",
  "domain_confidence": 0.71,
  "domain_confidence_calibrated": true,
  "specialist_model": null,
  "calibrated": false,
  "findings": [],
  "vlm_description": "A horizontal crack is visible on the wall ...",
  "warning": "no_specialist_model_for_domain"
}
```

`findings` is **never** populated from the VLM. A free-text description is a
description, not a measurement, and the schema keeps those two things apart.

### Two flags, because they are two facts

| Field | Question it answers |
|---|---|
| `calibrated` | Is this **result** a calibrated measurement? True only when a calibrated specialist produced the findings. |
| `domain_confidence_calibrated` | Has `domain_confidence` itself been temperature-scaled? |

They are separate because a calibrated router can route to a domain that has no
specialist at all. Collapsing them into one flag would force a choice between calling
a trustworthy confidence untrustworthy, or calling a description a measurement.

### Enforced, not merely intended

These rules are pydantic model validators, not conventions in a route handler. A
response with findings and no specialist behind them **fails to construct** — it
cannot reach a client. The invariants are covered by
`tests/unit/test_schema_invariants.py`:

* findings must be empty when `specialist_model` is null;
* `calibrated` must be false when `specialist_model` is null;
* a response without a specialist must carry a `warning` explaining why;
* `vlm_description` must be null when a specialist produced the result — if a
  specialist ran, the paid fallback was never called;
* a non-zero blur count requires a named detector.

---

## 4. API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/analyze` | Analyze one image |
| `GET` | `/health` | Liveness + per-model load state |
| `GET` | `/v1/domains` | Supported domains and whether each has a specialist |
| `GET` | `/v1/requests` | The authenticated user's own request history |

### Error codes

| Code | Meaning |
|---|---|
| `413` | File exceeds the size limit (10 MB) |
| `415` | Unsupported format |
| `422` | Rejected by the gate — not a damage/object photograph |
| `429` | Rate limit exceeded |
| `503` | VLM budget exhausted — `service_degraded` |

A `503` means the fallback path is off. Requests for domains **with** a specialist
keep working; the system degrades, it does not fail.

Full generated schema: [`docs/openapi.json`](docs/openapi.json).

---

## 5. Image processing pipeline

Order is fixed and enforced in a single module (`pipeline/orchestrator.py`):

1. **Format check** — `jpg`, `png`, `webp`, `heic` (HEIC via `pillow-heif`; iPhone photos
   arrive as HEIC and rejecting them would exclude most real-world uploads).
2. **Size check** — max 10 MB.
3. **EXIF read** — capture time, GPS presence (boolean only), device — retained for the
   integrity block.
4. **EXIF-orientation rotation** — applied before any model sees the image.
5. **Perceptual hash (pHash)** — duplicate detection and VLM cache key.
6. **Face and plate blurring** — applied before storage.
7. **EXIF strip + resize** to 1280 px long edge — only this version is written to storage.
8. **Model inference.**

**The raw upload is never persisted.** Only the redacted, EXIF-stripped, resized
derivative reaches Supabase Storage — `PreparedImage` has nowhere to put the original
bytes, so this is structural rather than a habit.

Rejected inputs: animated GIF/WebP, images under 200 px, corrupt or truncated files.
Format is decided by magic bytes, never by the filename or Content-Type, and every
upload is decoded — a truncated file passes a header check and fails a decode.

Two orderings are load-bearing:

* **Orientation before everything.** Phones record rotation as metadata rather than
  rotating pixels. A model handed the raw buffer sees a sideways car, and the boxes
  it returns are in a coordinate frame the user never saw.
* **Hash before redaction.** The perceptual hash identifies the *submitted*
  photograph. Hashing afterwards would make the fingerprint depend on how many faces
  the detector happened to find, so the same image could hash differently on a second
  submission and slip past duplicate detection.

### 5.1 Redaction — what is actually redacted

| Class | Detector | Status |
|---|---|---|
| Faces | YuNet (`yunet-2023mar`, OpenCV Zoo) | Active when the checkpoint is present |
| Plates | *none* | **Not redacted in v1** |

**Plates are not blurred.** OpenCV 5 removed `CascadeClassifier`, which takes the
bundled Haar plate cascade off the table; pinning OpenCV back to 4.x to regain it
would buy a detector trained on Russian plates whose accuracy on Turkish plates has
never been measured. Under this project's own rule — a privacy guarantee needs a
number behind it — an unmeasured detector may not ship as one. Plate redaction is
deferred to Phase 5, where Ultralytics arrives for the vehicle specialist and brings
a YOLO plate detector into reach under a licence already in use here.

Until then every response carries `plate_detector: null`. The schema distinguishes
the two states that matter:

* `"face_detector": "yunet-2023mar", "faces_blurred": 0` — we looked, found none.
* `"plate_detector": null` — **we did not look.**

A non-zero blur count without a named detector fails schema validation, so a
redaction claim cannot be made without something behind it.

Redaction is a mosaic, not a Gaussian blur. A blur is a convolution and is at least
partly invertible; downsampling to blocks and scaling back up genuinely discards the
information.

#### Measured miss rate

| Class | Detector | Annotated boxes | Recall | Miss rate | False positives |
|---|---|---|---|---|---|
| face | `yunet-2023mar` | | | | |
| plate | *not redacted* | | n/a | n/a | n/a |

Produced by `backend/scripts/eval_redaction.py`. **Empty because it has not been
run** — the annotated set does not exist yet. Recall is the metric that matters: a
missed face is a privacy failure, while a false positive only mosaics some bodywork.

---

## 6. Calibration

A softmax output is not a probability. A "93% confidence" claim only means something
after calibration, so the router is calibrated on a held-out validation split using
**temperature scaling**.

| Metric | Before calibration | After calibration |
|---|---|---|
| ECE (Expected Calibration Error) | _TBD_ | _TBD_ |
| Router top-1 accuracy | _TBD_ | _TBD_ |
| Mean confidence vs. accuracy gap | _TBD_ | _TBD_ |

Reliability diagram: `docs/assets/reliability_router.png` *(not generated yet)*

Any output produced without a loaded temperature parameter returns
`calibrated: false`. The flag is derived from runtime state, not hard-coded.

---

## 7. Evaluation

### 7.1 Router — confusion matrix

Test set: ~50 images per domain, disjoint from the calibration split.

| true \ predicted | vehicle | building | phone_screen | other |
|---|---|---|---|---|
| vehicle | | | | |
| building | | | | |
| phone_screen | | | | |
| other | | | | |

Matrix image: `docs/assets/confusion_matrix_router.png` *(not generated yet)*

### 7.2 Gate — out-of-distribution rejection

| Metric | Value |
|---|---|
| True-positive rate (valid photos accepted) | _TBD_ |
| False-accept rate (selfies/screenshots accepted) | _TBD_ |
| Chosen threshold | _TBD_ |

### 7.3 Vehicle specialist — per-class performance (CarDD test split)

Reported per class, deliberately. The literature consistently finds `dent`,
`scratch` and `crack` to be the hard classes; if our numbers show the same, that is
a correct result, not a defect to be hidden.

| Class | mAP@50 | mAP@50-95 | Precision | Recall | Notes |
|---|---|---|---|---|---|
| dent | | | | | |
| scratch | | | | | |
| crack | | | | | |
| glass shatter | | | | | |
| lamp broken | | | | | |
| tire flat | | | | | |
| **all** | | | | | |

### 7.4 Latency (production VPS, 4 vCPU / 8 GB, CPU only)

| Stage | p50 (ms) | p95 (ms) |
|---|---|---|
| Preprocess | | |
| Gate | | |
| Router | | |
| Specialist | | |
| VLM fallback | | |
| **End-to-end** | | |

Not yet measured on the production VPS. For calibration of expectations only: on a
development machine, ingesting a 2400x1800 JPEG — decode, EXIF, orientation, pHash,
face detection, resize, re-encode — takes roughly 320 ms. That is a single sample on
different hardware, not a p50, and it does not go in the table.

The preprocess row matters more than it looks: it is pure CPU work that runs on
every request including the ones the gate rejects, and it is the part of the budget
the queue decision in section 9 is measured against.

### 7.5 Severity thresholds — published, not measured

`severity` is a fixed-threshold heuristic over `area_ratio`. CarDD carries no
severity ground truth, so there is nothing to calibrate against and no honest
accuracy to report for this field.

| Band | Condition | Calibrated |
|---|---|---|
| `minor` | `area_ratio < 0.02` | no |
| `moderate` | `0.02 <= area_ratio < 0.08` | no |
| `severe` | `area_ratio >= 0.08` | no |

Every finding carries `severity_calibrated: false`. The thresholds live in one place
(`models/severity.py`) and a unit test pins them to the numbers in this table, so the
code and the documentation cannot drift apart. **No accuracy claim in this README
covers `severity`.**

### 7.6 Golden set

20 hand-picked images with expected outputs are committed under
`backend/tests/golden/`. Any model swap or threshold change that alters these
outputs fails CI. This is the regression tripwire for the whole system.

### 7.7 Known failure modes

_To be filled from the evaluation runs — this section is expected to be non-empty._

---

## 8. Cost

| Item | Value |
|---|---|
| Cost per request — vehicle path (no VLM) | _TBD_ |
| Cost per request — fallback path (VLM) | _TBD_ |
| VLM cache hit rate on the eval set | _TBD_ |
| Monthly VLM budget ceiling | _TBD_ |

Controls in place:

* The VLM is called **only** on the fallback path. Vehicle photos never reach it.
* pHash cache: an image already analyzed is served from Supabase, not re-sent to the API.
* Per-user daily request limit.
* A global monthly VLM spend counter. When it is exhausted the VLM is disabled and the
  API returns `503 service_degraded` — the specialist path stays up.

---

## 9. Scope

**In v1:** three-layer pipeline · vehicle specialist · VLM fallback · router
calibration · OOD rejection · EXIF + pHash integrity checks · face/plate blurring ·
Google sign-in · rate limiting · Next.js frontend · Docker deployment · test suite.

**Deferred to v2:** queue/worker architecture · specialists for non-vehicle domains ·
repair-cost estimation · multi-image upload · mobile app · self-retraining.

### On the absence of a queue

This is a decision, not an omission. Synchronous request handling is the correct
choice while end-to-end p95 stays under ~3 s and concurrency stays low: a queue adds
a broker, a worker pool, job state, polling or websockets on the client, and a second
failure surface — in exchange for nothing at this load.

The migration trigger is stated in advance: **when end-to-end p95 exceeds 3 s, or
sustained concurrent requests exceed 2× the worker count, BioVision moves to a queue.**
Section 7.4 is what tells us whether we are there.

---

## 10. Setup

The backend runs against a **mock model backend** by default: deterministic
stand-ins that satisfy the same interfaces as the real models. Nothing is
downloaded, nothing reaches the network, and the app boots in well under a second.
That is what lets the whole test suite run in CI without 2 GB of checkpoints — a
test suite that needs a GPU stops being run.

```bash
cd backend && uv sync && uv run uvicorn biovision.main:app --reload
```

Then:

```bash
curl -s http://localhost:8000/health
```

```bash
curl -s -F image=@photo.jpg http://localhost:8000/v1/analyze
```

Interactive docs at `http://localhost:8000/docs`.

### Whole stack

```bash
docker compose up --build
```

### Checks

```bash
cd backend && uv run ruff check . && uv run mypy && uv run pytest
```

### Frontend

Arrives in Phase 8. `pnpm` is installed via `corepack enable`.

### Model weights

Optional. Everything runs without them; features they back report themselves as
disabled rather than pretending.

```bash
cd backend && uv run python scripts/fetch_weights.py
```

Each artifact is verified against a pinned SHA-256, so a silently changed upstream
file is a loud failure rather than an unreproducible change in behaviour. Currently
this fetches the YuNet face detector (230 KB, MIT). Without it, `/health` reports
`redaction:face` as not ready and every response carries `face_detector: null`.

### Configuration

Copy `backend/.env.example` to `backend/.env`. Every setting is read through
`config.py` — nothing in the codebase touches `os.environ` directly. `.env` is
gitignored and CI fails if one is ever committed.

### Worker count

The backend runs with **at most 2 uvicorn workers**. Each worker loads its own copy of
CLIP and YOLO into RAM; on an 8 GB box, 4 workers exhaust memory and the machine dies.
This constraint is repeated as a comment at every place workers are configured.

---

## 11. Tech stack

| Concern | Choice |
|---|---|
| Backend | Python + FastAPI, Docker |
| Python packaging | `uv` |
| Frontend | Next.js (App Router) + TypeScript, `pnpm` |
| Frontend hosting | Vercel → `biovision.bilalgurkansanli.com` |
| Backend hosting | Self-managed VPS (4 vCPU / 8 GB / 100 GB) → `api.biovision.bilalgurkansanli.com` |
| Reverse proxy | Caddy (automatic HTTPS) |
| Gate + Router | CLIP / SigLIP zero-shot, CPU |
| Vehicle specialist | CarDD fine-tuned YOLO segmentation (pre-trained checkpoint) |
| Fallback | Cloud VLM API (small model) |
| Auth / DB / Storage | Supabase (Postgres + Google OAuth + Storage + RLS) |
| Request handling | Synchronous |
| Quality gates | `ruff`, `mypy`, `pytest` |

PyTorch is installed from the **CPU-only** wheel index. The server has no GPU, and
CUDA libraries would add gigabytes to the image for no benefit.

---

## 12. License

**AGPL-3.0.** Ultralytics YOLO is AGPL-3.0, and BioVision links against it, so the
whole work is distributed under the same terms. If you deploy a modified version as a
network service, you must offer the modified source to its users.

See [`LICENSE`](LICENSE) for the license text and [`NOTICE.md`](NOTICE.md) for asset
licensing — golden-set photographs, evaluation-image manifests, model weights, and
the CarDD dataset, which is **not** redistributed by this repository.

---

## 13. Author

Bilal Gürkan Şanlı — [bilalgurkansanli.com](https://bilalgurkansanli.com)
