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

**Superseded (September 2026): `phone_screen` removed.** It was never going to
get a specialist, and a domain that exists only to be routed to and then
apologised for earns nothing a well-named `other` does not. Its 30 evaluation
photographs were relabelled `other` -- a cracked phone is a damaged object --
and README 7.1 was re-measured on three domains rather than left describing a
system that no longer exists. The figure moved 95.0% -> 95.8% purely because
there is one fewer wrong answer available; macro-averaged recall is unchanged at
95.0%.

**Why:** each domain costs ~75 evaluation and calibration images to source and label.
The architecture is built so a domain is a one-line addition, which makes starting
narrow cheap to reverse — the opposite of the usual scope trade-off. `parcel` remains
present as a router prompt inside `other`.

---

## ADR-034 — Overall severity is a separate zero-shot layer, not a sum of findings

**Decided:** add `overall_severity` — a whole-photograph band, zero-shot on the
CLIP already loaded, reported uncalibrated at a measured 64.5%.

**The complaint, restated correctly.** A written-off car returned one `dent` at
42%. I first read that as a framing problem and spent a day on it: 960 px
training (ADR-030), inference at 1280/1600, tiling (ADR-033), vehicle-relative
normalisation. All measured, all rejected. The user's objection cut through it —
*"it has nothing to do with wide angle; the model could not see that the car is a
write-off"*. Cropping to the car yields four findings, and four findings is not
an assessment either. **A total is not a sum of parts.** I was optimising the
wrong output.

**Why zero-shot before a trained head.** The encoder is loaded, and the image
embedding is already computed for the gate and reused by the router. This reuses
it a third time and adds a dot product against 12 cached text vectors: no new
weights, no download, no measurable latency. If that had not worked, a trained
head would have been the next step; it worked well enough to publish, and well
enough to show what a head would have to beat.

**64.5%, and the bad row is the one that matters:**

| true \ predicted | minor | moderate | severe | recall |
|---|---|---|---|---|
| minor | 80 | 2 | 0 | **98%** |
| moderate | 33 | 34 | 8 | 45% |
| severe | 8 | 37 | 46 | **51%** |

Errors are almost all one band **low** — 37 severe photographs read as moderate.
It under-calls damage, which is the direction that costs a user something. On the
reported photograph it returns `severe` at 96%, but one photograph is not a
result; the table is.

**How this is prevented from becoming a false claim.**
`overall_severity_calibrated` is typed `Literal[False]`, so it cannot be set true
without deleting that line and answering for it — a contract test asserts the
response fails to construct otherwise. The UI prints the band beside *tahmin —
kalibre edilmemiş, %64.5 doğrulukta ölçüldü*, because a prominent band with a
quiet caveat is exactly the presentation this project exists to refuse.

**The evaluation set is borrowed and weak**, and the number inherits that: 248
held-out images at a median 275×183 px, some with stock-photo watermarks, which
makes the set's CC-BY-NC-SA-4.0 declaration one this project does not rely on. It
is used to measure and never redistributed. Whole-vehicle photographs labelled by
an assessor would be the right set and do not exist here.

**Revisit if:** assessor-labelled data appears. A trained head on real labels
should beat 64.5% comfortably, and the prompts in `severity.yaml` are then a
baseline to beat rather than the answer.

---

## ADR-033 — Tiled inference is not shipped; the framing failure is published instead

**Decided:** keep whole-image inference. Publish the failure it has on wide shots,
and tell people to photograph the damage close up.

**The failure.** A user uploaded a wide shot of a written-off car and got one
finding, `dent` 42%. Cropped to the car: four, including `missing_part` and
`torn`. VehiDE is entirely close-ups, so the specialist learned one scale.

**Why §7.3 could not have caught it.** VehiDE's validation split is close-ups
too. Every published number was measured in the regime the system is best at. An
evaluation set drawn from the training distribution cannot report a distribution
failure — and §7.7 sat empty for months waiting for "the evaluation runs" to fill
it, which they were never going to do.

**The fix that looked obvious.** Slicing the image (SAHI) presents damage at the
trained scale, and turned 1 finding into 6 on that photograph. Drawing the boxes
showed 2 were invented — `missing_part` on an undamaged ambulance, `glass_shatter`
over 35% of the frame. Six is not better than one if two are fiction.

**Measured, 60 images, both framings, four confidence floors:**

| Framing | Setting | Precision | Recall | F1 |
|---|---|---|---|---|
| close-up | whole image | 0.722 | 0.460 | **0.562** |
| close-up | tiled, floor 0.45 | 0.343 | 0.484 | 0.401 |
| wide | whole image | 0.584 | 0.419 | **0.488** |
| wide | tiled, floor 0.45 | 0.355 | 0.435 | 0.391 |

**+0.016 recall for −0.229 precision.** F1 falls in both framings at every floor
tested, so no threshold rescues it. Rejected.

**How the threshold was chosen — it wasn't.** The tempting move was to read a
floor off the accident photograph, where the four real findings scored 0.50–0.67
and the two inventions scored 0.34–0.36. That is fitting to the example, the same
error as tuning `router_min_confidence` on the evaluation set. The floors were
swept and all of them lost.

**Limits, since they bound the conclusion.** The wide set is padded close-ups; a
real photograph from twenty metres is also blurrier and lower in contrast, so the
measured gap is a floor on the real one. And this is precision/recall at one
operating point rather than mAP — `eval_specialist.py` still owns §7.3.

**What ships instead:** the failure, in README §7.7 with the crop table, and a
line above the file picker telling people to shoot close up. `scripts/eval_framing.py`
so the rejection can be re-checked.

**Revisit if:** wide-shot training data appears. This is a distribution gap, and
the fix is photographs of damage taken from a distance — not a decoding trick.

---

## ADR-032 — A description may sit beside a measurement, opt-in and off by default

**Decided:** allow `vlm_description` alongside `findings` when
`vlm_augments_specialist` is on. It was forbidden outright.

**Why the ban existed, and why it was the wrong rule.** The validator said a
specialist running proved the VLM had not been called. That is a *cost*
guarantee wearing an *honesty* invariant's clothes — and it was enforced in the
one place that cannot see cost, while the actual controls (sign-in, budget
ceiling, pHash cache) live in the pipeline.

**Why it matters now.** The vehicle specialist recalls 25% of dents. A written-off
car can come back as one finding: correct about that finding, and read as light
damage by anyone not holding README section 7.3. Every lever inside the model has
been measured and none moved it — training at 960 px (ADR-030), inference at
1280/1600, the confidence floor, normalising by the vehicle. The remaining
improvement is not in the detector.

**What the contract still forbids**, and this is the part that was always the
honesty rule: **a specialist that found nothing cannot return prose.** Empty
findings plus text reads as an answer while being the absence of one. That
validator stays, with a message that now says what it protects.

**What replaces the cost guarantee:** the setting (off by default), the existing
sign-in requirement, and the monthly budget — each with a contract test, including
one asserting an anonymous caller still gets the measurement and no description.
A test also asserts the description changes neither the findings nor the
calibration flags: text beside a measurement, never instead of it.

**The honest limit.** This is not switched on. No VLM key is configured, so today
it changes nothing at runtime. It is also not a fix for the detector — it makes a
thin result *legible*, not *correct*, and a reader who trusts the prose over the
findings has been misled by presentation rather than by the schema.

---

## ADR-031 — Severity starts from the damage class, because area measured the photographer

**Decided:** derive `severity` from the damage class, and let `area_ratio` raise a
band but never lower one. It was thresholds over `area_ratio` alone.

**The defect.** `area_ratio` divides damaged pixels by the whole image. Measured on
one VehiDE photograph, re-framed and nothing else changed:

| Framing | `area_ratio` | Severity |
|---|---|---|
| as shot | 0.2335 | severe |
| padded by 40% | 0.0996 | severe |
| padded by 100% | **0.0077** | **minor** |

Thirty-fold on the same car. The system was reporting the photographer's distance
as a property of the damage.

**How it surfaced.** By running the thing and looking at it. A wide shot of a
written-off car — ambulance and police in frame, which is what a claim photograph
actually looks like — came back `minor`. Every unit test passed; they pinned the
thresholds, and the thresholds were doing exactly what they said. What nothing
checked was whether the input to those thresholds meant what the output claimed.

**Why not normalise by the vehicle instead**, which was the first idea: a COCO
detector found no vehicle in 3 of 6 VehiDE photographs, and none at all in the
one above at any framing. Damage photographs are close-ups of a bumper, not
portraits of a car. A normaliser that is absent half the time silently falls back
to the broken behaviour, which is worse than not having it.

**What this costs in honesty.** The class-to-band mapping — missing part is
severe, scratch is minor — is claims-handling intuition, and it is a larger
judgement call than a numeric threshold was. Nobody has measured whether an
assessor agrees. So the reasoning is published beside the table, `severity_calibrated`
stays false, and no accuracy claim covers this field. Trading a precise-looking
number that was wrong for an arguable rule that is defensible is the right trade
here, but it is a trade.

**What it does not fix.** The specialist finds 25% of dents. Severity now
describes what was found correctly; it still says nothing about what was missed,
and on a wrecked car that is most of it. Two different defects, and only one of
them is closed.

**Revisit if:** severity ground truth appears — an assessor labelling a few
hundred photographs would turn this from a judgement call into something with an
error rate.

---

## ADR-030 — The specialist stays at 640 px; the resolution hypothesis was wrong

**Decided:** keep `vehide_yolo_seg.pt` at 640 px. Do not ship the 960 px model.

**The hypothesis.** `scratch` scored 0.239 mAP@50 with **six times** the training
data of `glass_shatter` at 0.782. More data producing a worse class pointed at
the damage rather than the dataset: a scratch is thin and low-contrast, and
downscaling a 1.7-megapixel photograph to 640 px destroys exactly that. If
resolution were the ceiling, more pixels would lift `scratch` specifically.

**The test.** 40 epochs at 960 px, warm-started from the 640 px checkpoint, same
split, same seed, same augmentation. 38 epochs ran before early stopping, 5.4
hours on a T4.

**The result.** `scratch` moved by **−0.001**. Overall mAP@50 moved by +0.001.
The hypothesis failed at precisely the point it predicted, which is the useful
kind of failure.

`punctured` gained 0.058 and `glass_shatter` lost 0.041 — but the run changed
resolution *and* halved the batch from 16 to 8, because 960 px activations are
roughly 2.25× the memory and 16 does not fit a T4. Two variables moved, so
neither class-level change is attributable. Stating that is better than an
explanation that happens to fit.

**Why not ship it anyway.** Inference at 960 px costs roughly double; the
specialist is already 113 ms of a 312 ms p50 request on a CPU-only VPS. Paying
that for +0.001 is paying for noise. A model trained at 960 and run at 640 is
worse than either done consistently, so adopting it would also mean changing
`IMGSZ` in the specialist — a real change for no measured gain.

**What it rules out, which is the point.** The ceiling on `scratch` is not
resolution. That leaves annotation quality, and the ordering in README section
7.3 already argued it: a scratch's boundary is a judgement call for the person
drawing the polygon, and retraining cannot recover a label that was ambiguous
when it was made. **Fixing `scratch` means re-annotating, not re-training.** This
run is what makes that a conclusion rather than a guess.

**Revisit if:** someone re-annotates the `scratch` class, or a dataset appears
with tighter guidelines for thin damage. Not on more epochs or more pixels —
those have now been measured.

---

## ADR-029 — The fitted temperature is not loaded, because it made ECE worse

**Decided:** fit temperature scaling, measure it on held-out data, and **do not
write the file** when the measurement says it did not help. `calibrate_router.py`
refuses; `--force` overrides it and prints why you should not.

**What happened.** T = 1.376 fitted on 120 calibration images. On the 120
evaluation images the fit never saw, ECE went from **0.0405 to 0.0603** — worse.
Accuracy was identical at 95.0%, as it must be: temperature scaling is monotonic
and cannot reorder classes.

**Why it failed, which is the part worth keeping.** The reliability diagram shows
the bars *above* the diagonal — at 68% claimed confidence the router is right 100%
of the time. It is mildly **under**-confident, and a temperature above 1 lowers
confidence further. The fit still chose T > 1 because temperature scaling
minimises negative log-likelihood, not ECE. On a router this well separated the
two objectives disagree, and optimising the one that is easy to optimise moved the
one that gets published in the wrong direction.

**Why this is not a bug to fix.** The obvious response is to fit against ECE
directly. That would be fitting to the metric being reported — the same error as
tuning a threshold on the evaluation set, wearing a more respectable hat. The
router's raw confidences are already reasonable; that is a smaller claim than
"calibrated", and it is the one the evidence supports.

**What the system says instead:** `domain_confidence_calibrated: false`, on every
response, derived from the absence of the file rather than hard-coded. The flag
was already correct before this measurement and stays correct after it — but for a
different reason, and README section 6 states which.

**Revisit if:** the evaluation set grows past a few hundred images per domain, or
intake photographs replace the current clean sources. Under-confidence measured
over 120 images across four visually distinct domains may not survive either.

---

## ADR-028 — The router evaluation set is assembled per file, and looked at

**Decided:** build the router and gate evaluation sets from Wikimedia Commons and
one Kaggle dataset, resolving the licence **per file** rather than per collection,
and inspect every set visually before measuring anything with it.

**Why per file.** Commons is a collection, not a corpus. Sixty photographs pulled
from three cracked-screen categories carried **seven different licences** — CC
BY-SA 4.0, CC BY-SA 2.0, CC0, CC BY-SA 3.0, CC BY 2.0, CC BY 3.0, CC BY 4.0. One
`--license` flag for the batch would have been a convenient fiction in a file
whose entire purpose is that a reader can check it. `fetch_commons.py` therefore
asks the API for each file's licence and author, records both, and **skips any
file whose licence it cannot resolve**. A missing licence is not a small gap in a
manifest; it is a claim nobody can check.

**Why looked at.** Three defects were invisible in metadata and obvious on sight:

| Set | What the metadata said | What the images were |
|---|---|---|
| `phone_screen` (Commons) | 74 files in cracked-screen categories | included a Kraków market square; 25 of 74 were one OnePlus in one session |
| `other` (Commons "Damaged objects") | ~700 files, clean licences | museum conservation: water-stained postcards, archaeological finds, restorers at work, undamaged chopping boards |
| `building` (Commons RCE) | 261 usable files | genuine, but many are one building from several angles |

So `contact_sheet.py` exists, and each set is tiled and viewed before use. An
evaluation set nobody has looked at measures whatever happens to be in it and
reports the result as though it measured what the label claims.

**What this changed.** `phone_screen` moved to DataCluster's Kaggle set — 300 real
handheld photographs of cracked phones, which is what the system actually
receives. `other` was rebuilt from specific object categories instead of the
conservation tree. `building` kept Commons, with grouping (below).

**Grouping, because disjointness is not independence.** The building archive
photographs one facade from six angles. Splitting those files randomly puts three
angles in the evaluation split and three in calibration: the splits share no
file, pass the disjointness assertion, and are still not independent.
`sample_router_set.py` gained `--group-regex`, which keeps one subject's
photographs on one side of the cut.

**Revisit if:** a licence-clean dataset appears whose images are ordinary phone
photographs of damaged buildings. The Commons building set is one institution,
one country, one era, and README section 7.1 says so next to the number.

---

## ADR-026 — VehiDE replaces CarDD as the training set

**Decided:** train the vehicle specialist on **VehiDE** (13,945 images, 8 damage types,
IEEE KSE 2023) rather than CarDD. Apply for CarDD anyway; if it arrives, train on both
and publish the comparison.

**Why, in order of weight:**

1. **Its annotation guidelines come from an insurance company's claim standards**, not
   from an academic labelling pass. It even defines a priority rule for overlapping
   damage — which dents, scratches and cracks do constantly. For a system built to be
   shown to an insurer, that provenance is worth more than any other difference here.
2. **Three and a half times the data.** 13,945 images and 32,000+ instances against
   CarDD's 4,000 and 9,000.
3. **No gate.** Kaggle, direct download, today. CarDD is a signed form, an email, and
   an unknown wait.
4. **The licence question dissolves.** Kaggle states Apache 2.0, which would make
   ADR-025 — the decision not to publish CarDD-derived weights — moot.

**What is worse about it, stated plainly:**

* **The Apache 2.0 label is the uploader's claim, not the authors'.** The Kaggle account
  is not the paper's authors (Huynh et al., HCMUTE). The original publication is behind
  IEEE's paywall and the lab page says nothing. Downloading is fine; **publishing weights
  trained on it needs one line of confirmation from the authors first.** Having read
  CarDD's licence rather than assuming it, doing less here would be inconsistent.
* **Lower resolution.** CarDD's images average 684k pixels against roughly 50k for the
  datasets it was benchmarked against. VehiDE says "high-resolution" without a number.
  Thin scratches are exactly what resolution buys, so this is measured before training,
  not assumed.
* **VIA, not COCO.** A VIA-to-YOLO converter is needed. The COCO one is written and
  rehearsed; this is half a day on top.

**Rejected, and why:**

| Dataset | Reason |
|---|---|
| CDD (Panboonyuen, 12,000 images, 26 damage + 7 **fake-damage** types) | The strongest set on paper and the fake-damage classes are directly interesting for fraud. **It is private** — access is restricted by a licensing agreement with THAIVIVAT Insurance. Only the public CarDD copy is downloadable from that repository. |
| CrashCar101 | Semantic masks, not instances. Findings are a list; semantic segmentation cannot say how many. |
| `moondream/car_part_damage` | Car *parts*, not damage types. Licence "unknown". |
| Roboflow CC BY 4.0 sets | Too small (908-4,303), or a single "Damage" class, or types mixed with locations. |

**The unauthorised copies are not an option.** CarDD is mirrored on HuggingFace and
behind a Google Drive link in a public research repository, both without the signed
form its licence requires. Taking that route would be faster and would quietly discard
the thing this project is for. A system whose selling point is stating what it cannot
do cannot be built on data obtained by ignoring what its owners said.

---

## ADR-003 — Train the vehicle specialist ourselves

**Decided:** fine-tune YOLO-seg on CarDD on a free Colab T4 rather than adopting a
public checkpoint. The split and its seed are pinned in
`notebooks/train_vehide_yolo.ipynb`; the dataset is not redistributed.

**Why:** a public checkpoint has an unknown train/test split. Any leakage between it
and our evaluation split would make the per-class mAP table unverifiable — and that
table is the project's headline claim. An unverifiable specialist is worse than no
specialist, because it converts the honest answer into a confident wrong one.

**Consequence:** Phase 5 is blocked on the CarDD access request. Every other phase is
independent of it and proceeds regardless.

### The alternatives, surveyed

CarDD's own repository has few stars, which is a fair thing to notice and the wrong
thing to measure. It is a dataset published in *IEEE T-ITS*, not a library — nobody
stars a dataset they obtained by signing a form. The survey below is what actually
decided it.

Three requirements do the eliminating, and all three come from decisions already made
elsewhere in this project:

1. **Instance polygons, not boxes.** `area_ratio` is computed from the mask because a
   bounding box overstates a thin diagonal scratch by a large factor — the failure
   `vehicle_yolo.py` guards against by name. A box-only dataset cannot produce the
   number the severity band is derived from.
2. **Damage *types*, consistently.** `DamageType` is a closed set of six kinds of
   damage. A taxonomy that mixes kinds with locations — "dent" alongside "damage door"
   — cannot populate it without inventing a mapping.
3. **Separable instances.** Findings are a list. Semantic segmentation says which
   pixels are damaged, not how many distinct damages there are.

| Dataset | Images | Classes | Annotation | Licence | Verdict |
|---|---|---|---|---|---|
| **CarDD** (Wang et al., T-ITS 2023) | 4,000 | 6, all damage types | Instance polygons | Form; research free, commercial by permission, no redistribution | **Chosen.** The only one meeting all three requirements. |
| CDD (Panboonyuen, 2025) | 12,000 | 26 damage + 7 fake-damage + 61 parts | Instance polygons (COCO) | Non-commercial, on request | The strongest rival, and the fake-damage classes are directly interesting for insurance. Rejected for now: same access friction, a stricter commercial clause, and 94 classes would replace the six-class contract wholesale. Worth applying for in parallel. |
| CrashCar101 (WACV 2024) | 101,050 | 5 damage + parts | **Semantic** masks, synthetic | Contact form on HuggingFace | Fails requirement 3 outright. Synthetic, so a sim2real gap on top. Its scale makes it a good *supplement* to real data, which is what its own paper reports. |
| Roboflow `sinfo/car-damage-segmentation` | 4,303 | **1** — "Damage" | Instance | CC BY 4.0, direct download | Fails requirement 2 completely: it can say damaged, never how. Its own published model scores **mAP@50 of 4.4%**, which says something about the annotations. |
| Roboflow `car-damage-severity/VehicleDamageDetection` | 2,249 | 12, mixed | Instance | CC BY 4.0, direct download | Fails requirement 2: `dent` sits beside `damage door` and `damaged hood`. No `scratch` class at all. |
| Roboflow `cardamage/Car-Damage` | 908 | 11, all damage types | Instance | CC BY 4.0, direct download | Closest of the frictionless options — the taxonomy is at least consistent. Too small at 908 images, four separate glass-crack classes, and a misspelt class name that does not inspire confidence about the annotation pass. |
| CDD (Baig et al., 2025) | 2,241 | 1 — dent | **Boxes** | Open, Zenodo | Fails requirement 1. |
| CDD (Li et al., 2018) | 2,170 | 3 | **Boxes** | Author contact | Fails requirement 1. |

**What the survey changed:** nothing about the decision, and one thing about the plan.
The frictionless CC BY 4.0 options are real and would let a specialist ship this week,
but each would force a different `DamageType` and then a second migration when CarDD
arrives — paying for the contract twice to shorten a wait measured in days. The
Panboonyuen set is genuinely competitive and is now worth applying for **alongside**
CarDD rather than instead of it.

**Revisit if:** CarDD access is refused or takes weeks. Then
`cardamage/Car-Damage` (908 images, consistent types, CC BY 4.0, instant) becomes the
pragmatic fallback, with the class count cut to what it can actually support and the
README saying plainly that it is a smaller and weaker basis than intended.

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

## ADR-027 — The session lives in localStorage, and the CSP is what protects it

**Decided:** keep supabase-js's default session storage (`localStorage`) and treat
a strict Content-Security-Policy as the control that makes it acceptable, rather
than moving the session into httpOnly cookies.

**Why not cookies, which are the safer default:** the API is a separate origin
(`api.biovision...` against `biovision...`), so the browser must attach a bearer
token to each call itself. An httpOnly cookie is by definition unreadable to the
code that would have to attach it. Making cookies work would mean proxying every
API call through Next.js — an extra hop on every request, a second place for the
contract to drift, and a Vercel function in the path of a 250 ms inference call.

**What this costs, stated plainly:** a cross-site scripting bug in this app would
expose an access token, and with it a user's analysis history.

**And the first version of this ADR overstated the defence.** It claimed
`script-src 'self'` with no `unsafe-inline`. Deploying that policy and opening the
site showed it does not work: Next emits inline bootstrap and RSC-payload
scripts, so hydration never runs. Every page rendered and nothing on it
functioned — worse than no policy at all. Three options were measured:

| Approach | Result |
|---|---|
| `script-src 'self'` alone | Hydration blocked. React error #412. Site inert. |
| Experimental SRI hashes | Covers some inline scripts, not all. Violations continued. |
| Per-request nonces | Works, and forces every page dynamic — no static prerender, no CDN caching, a server render per visit. |

Nonces are the right answer for an app that renders user-generated markup. This
one renders none, and the exposure it actually has is the token. So the policy
allows `unsafe-inline` for scripts and puts the weight on the directive that
addresses that exposure directly:

* **`connect-src` names exactly two upstreams.** Injected script or not, nothing
  can be sent anywhere but our API and the Supabase project. This is what stands
  between an XSS bug and a stolen token leaving the browser.
* `frame-ancestors 'none'` and `X-Frame-Options: DENY`;
* `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`;
* one `dangerouslySetInnerHTML` in the entire app, serialising a module-level
  constant that no request can influence;
* token rotation and short expiry left on, so a stolen token expires.

The honest summary: script injection is not prevented, exfiltration is. That is
a weaker guarantee than this ADR first claimed, and it is what the measurement
supports.

**Revisit when:** user-generated content appears anywhere in the DOM — at that
point `unsafe-inline` stops being defensible and the nonce cost has to be paid.
Also when the app grows a server-rendered page that needs the session. Either change moves the
balance, and at that point `@supabase/ssr` with a proxy route is the answer.

---

## ADR-025 — Derived weights are not published until the dataset's authors confirm it

**Superseded in scope by ADR-026** (the training set is now VehiDE), but the
decision and its reasoning carry over unchanged. VehiDE is labelled Apache 2.0 on
Kaggle by an uploader who is not the paper's authors; a permissive-looking label
from a third party is weaker evidence than CarDD's explicit prohibition, not
stronger. The asymmetry below is what decides both cases.

The original entry, about CarDD:

## ADR-025a — CarDD-derived weights are not published until the PIC Lab authorises it

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
