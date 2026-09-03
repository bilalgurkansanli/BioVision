# Notebooks

## `train_vehide_yolo.ipynb` — the vehicle specialist

Fine-tunes YOLO segmentation on **VehiDE** for the vehicle specialist, on a free
Colab T4.

We train this ourselves rather than adopting a public checkpoint because a public
checkpoint has an unknown train/test split. Any leakage between it and our evaluation
split would make the per-class mAP table unverifiable — and that table is this
project's headline claim. See [`../docs/DECISIONS.md`](../docs/DECISIONS.md) ADR-003,
and ADR-026 for why VehiDE rather than CarDD.

---

## Getting VehiDE

**In Colab, from Kaggle — this is the fast path.** Colab's connection beats a
domestic upload by a wide margin; 2.3 GB over a home link is an hour you do not
need to spend. The notebook's cell 2 does it for you and asks for a
`kaggle.json` (kaggle.com → Settings → API → Create New Token).

**Or from Drive**, if you would rather upload once and keep it: put the
extracted dataset at `MyDrive/datasets/vehide/` and set `USE_KAGGLE = False`.

Either way the archive nests its directories twice — `image/image/` and
`validation/validation/` — and the notebook expects exactly that, because
assuming otherwise produced a run reporting "2,324 images missing" before anyone
looked at the tree.

### One licence question to settle before publishing anything

Kaggle labels the dataset Apache 2.0, but that label was applied by the uploader,
not by the authors (Huynh et al., HCMUTE, IEEE KSE 2023). Downloading and training
is fine. **Publishing a checkpoint trained on it needs one line of confirmation
from the authors first** — `cvis.hcmute.edu.vn` lists their contact. Having read
CarDD's licence rather than assuming it, doing less here would be inconsistent.

---

## What is actually in it

Measured with `uv run python -m scripts.inspect_vehide`, not taken from the
dataset card:

| | Published | Counted |
|---|---|---|
| Images | 13,945 | **13,945** |
| Instances | 32,000+ | **36,081** |
| Damage classes | 8 | **7** (the eighth is `non-damaged`, which carries no regions) |
| Degenerate polygons | — | **0** |
| Mean resolution | "high" | **1,714,161 px** — 2.5× CarDD's 684k |

Class distribution, and the Vietnamese names as they appear in the annotations:

| VehiDE | Meaning | Instances | Share | `DamageType` |
|---|---|---|---|---|
| `tray_son` | paint scratch | 14,647 | 40.6% | `scratch` |
| `mop_lom` | dent | 5,681 | 15.7% | `dent` |
| `rach` | torn | 5,509 | 15.3% | `torn` |
| `mat_bo_phan` | lost part | 2,818 | 7.8% | `missing_part` |
| `be_den` | broken lights | 2,782 | 7.7% | `lamp_broken` |
| `thung` | punctured | 2,423 | 6.7% | `punctured` |
| `vo_kinh` | broken glass | 2,221 | 6.2% | `glass_shatter` |

`scratch` is 40% of the data and the other six share the rest. Expect the
per-class table to reflect that, and publish it anyway.

**`DamageType` was changed to match this** rather than the reverse (ADR-026).

---

## The split

**VehiDE's own validation set becomes our test set**, held out entirely. Its
training set is divided 82/18 into train and val for early stopping.

| Split | Images | Source |
|---|---|---|
| train | 9,530 | VehiDE train |
| val | 2,091 | VehiDE train |
| test | 2,324 | **VehiDE val, never trained on** |

Pooling everything and reshuffling would buy a slightly larger training set and
a number nobody can compare against anything else published on this dataset.

---

## Where to run it: Kaggle, not Colab

The notebook runs on both and detects which one it is on. But on a free account
the choice matters, and it is not about the GPU:

| | Kaggle | Colab (free) |
|---|---|---|
| Weekly GPU | **30 h, stated** | 15–30 h, variable and undisclosed |
| Session limit | 9 h | 12 h |
| Idle disconnect | — | **~90 min** |
| Browser must stay open | **no** — runs in the background | yes |
| This dataset | **already there**, mounted read-only | 2.3 GB to download first |
| Output survives session | yes, downloadable | only if written to Drive |

**Measured cost of this run:** 596 iterations per epoch at batch 16. That is
roughly 2.8 min/epoch on a T4 and 2.0 on a P100 — so 100 epochs is 4.7 h or
3.3 h, and an early stop near 60 is 2.8 h or 2.0 h.

Those fit inside either platform's session limit. The problem on free Colab is
not the ceiling, it is the **90-minute idle disconnect with no background
execution**: a three-hour run needs the tab open and the machine awake for three
hours, and a closed laptop lid ends it. Kaggle runs it detached, and the dataset
is already on the platform so nothing is downloaded at all.

The notebook measures its own pace before committing: it trains two epochs,
reports minutes per epoch, projects the full run, and warns if the projection
exceeds the session limit. A measured estimate rather than the one above.

If a session does die, nothing is lost beyond the current epoch — Ultralytics
writes `last.pt` every epoch to the persistent directory. Resume with:

```python
YOLO(RUNS / "vehide_seg/weights/last.pt").train(resume=True)
```

### Settings

| Setting | Value | Why |
|---|---|---|
| `MODEL` | `yolo11s-seg.pt` | Measured on CPU at the production thread count: 139 ms median per image at 640 px against 483 ms for `yolo11m-seg`. The medium model pushes a request past a second on the VPS and would force a queue this design does not have. |
| `IMGSZ` | 640 | A real downscale from VehiDE's 1.7M px average. 960 roughly doubles inference cost (319 ms) and is the fallback **if the `scratch` row disappoints** — thin damage is what resolution buys. Retrain at 960 rather than running a 640-trained model at 960. |
| `SEED` | 20260311 | Pinned, with `deterministic=True`. The split is fingerprinted too. |
| `EPOCHS` | 100, `patience=20` | Early stopping usually ends it well before the ceiling. |
| `BATCH` | 16 | Raise it if the GPU has memory to spare; it is the cheapest way to shorten the run. |

### Rehearsed against the real data

The whole data path was executed against the actual 2.3 GB download before any
GPU time was spent, and it found three things that would each have cost a run:

* **`inspect_via` raised `NameError` on its first call.** Its helper lived in a
  COCO cell that no longer exists. Moving cells around does not preserve what
  they depended on.
* **One training image leaked into the test set.** Integer rounding at 82/18
  leaves a remainder, and `split_dataset` assigns the remainder to `test`. One
  image changes no score, but "the test set was never trained on" is either true
  or it is not.
* **Then the fix for that threw the image away.** Deleting the directory removed
  the remainder along with it. It now moves into `train`, and the cell says how
  many it moved.

Final state, measured: 9,530 + 2,091 + 2,324, **zero overlap between training
and test**, every coordinate normalised, class order matching `CLASSES`.

Nothing is dropped silently anywhere in the conversion: unmapped classes,
non-polygon shapes, images with no usable region and missing files are all
counted and printed, with a warning past 5%.

---

## After training

1. Download `best.pt` → `backend/weights/vehide_yolo_seg.pt`. On Kaggle:
   Save Version, then take it from the Output tab. On Colab the last cell
   downloads it for you.
2. Restart the API. `/health` lists the new component; the vehicle domain starts
   measuring. **No code change** — the specialist is loaded by filename.
3. Paste the per-class table from the evaluation cell into README section 7,
   **verbatim, including the classes that perform badly**, with the citation.
4. Record the split fingerprint the notebook prints alongside the metrics. If it
   ever differs, the numbers are not comparable to the published ones.
5. Run the golden set: `uv run python -m scripts.update_golden`, inspect the diff,
   and commit the expected outputs.

**`calibrated` stays `false` after all this.** The response will carry
`specialist_model: "vehide-yolo-seg-v1"` and real findings, but segmentation
confidences are not calibrated and `severity` is a rule over area ratio rather than
a fitted model — which `severity_calibrated: false` already reports. "I measured
this" and "I have calibrated how sure I am" remain two separate claims.

### Requirements the notebook satisfies, so the numbers mean something

* the train/validation/test split and its **random seed** are pinned, and the split
  is fingerprinted;
* the dataset is **never** committed or redistributed here;
* the Vietnamese-to-`DamageType` mapping is written out term by term, with counts,
  so it can be checked rather than trusted;
* per-class metrics are printed as markdown and pasted into the README verbatim,
  including the classes that perform badly;
* the checkpoint is **not** published until the authors confirm the licence.

---

## Citation

> N. T. Huynh, N. N. D. Tran, A. T. Huynh, V.-D. Hoang and H. D. Nguyen, "VehiDE
> Dataset: New dataset for Automatic vehicle damage detection in Car insurance,"
> *2023 15th International Conference on Knowledge and Systems Engineering (KSE)*,
> IEEE, 2023. doi:10.1109/KSE59128.2023.10299490


---

## `train_metu_crack.ipynb` — the konut crack patch classifier

Trains a binary **patch** classifier on METU/Özgenel: given a 227×227 crop of a
building surface, is there a crack in it. Generated by
`backend/scripts/build_konut_notebook.py` — edit the generator, not the JSON.

### Why a patch classifier

Measuring the zero-shot konut router showed its failure was **spatial dilution**,
not encoder weakness: a hairline crack is a fraction of a percent of a frame, and
one global embedding of a photograph that is 99% intact wall is an embedding of
an intact wall. Cutting the frame into tiles moved the same weights by a wide
margin (README 7.11). So the right granularity is a patch — and METU/Özgenel
*is* 40,000 labelled patches. The dataset and the finding agree.

### Why not the datasets that looked better

Two Roboflow projects carry exactly the class list this product needs — `crack,
stain, mold, damp, peeling_paint, water_seepage` — and label themselves MIT and
Public Domain. **Both were opened and looked at before either was used, and
neither licence is the uploader's to grant:**

| project | label | what the filenames actually are |
|---|---|---|
| `building-damage-insurance` (5,178) | "MIT" | more than half are `istockphoto-<id>-612x612.jpg` — **iStock previews**, scraped at the free size |
| `property-defect-issues` (604) | "Public Domain" | `download.jpg`, `download (1).jpg` … `images (23).jpg` — **Google Images default download names**, plus a chimney-sweep company's website image and a damp-proofing contractor's job photograph |

Getty's photographs do not become MIT because somebody typed MIT. So the classes
this product most needs stay untrained, and what gets trained is the one dataset
whose licence survives reading.

### The dataset

**Özgenel, Ç.F. & Gönenç Sorguç, A. (2018)**, *Performance Comparison of
Pretrained Convolutional Neural Networks on Crack Detection in Buildings*, ISARC
2018, Berlin. Mendeley `5y9wdsg2zt`, **CC BY 4.0** — verified against Mendeley
directly, not taken from a mirror's card. 40,000 patches at 227×227, 20k cracked
and 20k not, from **458 parent photographs** at 4032×3024, no augmentation.

Usefully, it is Turkish: the parents are METU campus buildings in Ankara.

CC BY requires attribution, so that citation travels into the README, the model
card and the response metadata. It is a licence condition, not a courtesy.

### The split, and the leak it exists to prevent

**40,000 patches from 458 photographs is ~87 patches per photograph.** A
patch-level split puts crops of the *same wall* in both train and test, and the
resulting accuracy measures memorisation of 458 walls rather than recognition of
cracks. At that ratio it is not a rounding error, it is most of the score — and
the published 97–99% figures for this dataset are, as far as their papers say,
patch-level.

The parent is not in the filenames, so it is recovered by clustering on colour
statistics with **k fixed at 458, the known parent count** — a fact from the
dataset description rather than a tuned number. This is approximate and the
notebook says so. What it is worth is then **measured**: the same trained model
is evaluated on held-out clusters and on patches from clusters it trained on, and
the gap between those two numbers is this dataset's leakage.

### What it must print before anything ships

1. The **out-of-distribution false-alarm rate first** — 15 reviewed intact
   residential interiors, a different source entirely. It cannot measure recall.
   It measures the failure a claimant actually meets, which is the one the
   vehicle specialist shipped for a release (7.10) and the one the public crack
   checkpoint failed at 64% (7.11). **A high false-alarm rate means it does not
   ship, whatever the held-out accuracy says.**
2. The held-out-cluster accuracy **second, with its caveat attached**: it says
   how well the model learned METU's 458 Ankara facades, not how it behaves on a
   Turkish home. No independent Turkish residential set exists to say that.
3. The **split fingerprint and seed**, recorded beside every number.
4. Single-patch **CPU latency at 4 threads**, and the per-photograph cost at 17
   tiles. Over budget is a result, not a detail to leave out.

`calibrated` stays **false**. And cracks remain the least useful konut
sub-problem: they map to earthquake damage, which DASK already sends a licensed
eksper to assess and settles on rebuild cost rather than by grade.

---

## `train_hitl_parts.ipynb` — which part is damaged

Trains `yolo11n-seg` to segment 21 car parts, so a finding can be reported as
"the front bumper" rather than as "21% of the vehicle, lower-left of the frame".
Generated by `backend/scripts/build_parts_notebook.py` — edit the generator, not
the JSON.

### The dataset that was rejected, and why it is worth knowing

Ultralytics ships `carparts-seg`: 3,833 images, 23 classes, CC BY 4.0, trainable
in one line. It is the first result anyone finds. Counting its Roboflow
augmentation names back to their sources:

```
3,833 image files, 585 unique SOURCE photographs      (6.6x augmentation)
source photographs appearing in more than one split:   429  (73%)
  ... appearing in all three splits:                    89
```

**A held-out mAP on it measures memorisation of rotated duplicates.** Its CC BY
badge also traces to `dsmlr/Car-Parts-Segmentation`, whose GitHub licence field
is null and which ships no LICENSE — a permissive badge over a source that
granted nothing, the third time this project has found that pattern.

The notebook re-counts the leak on your machine before using it, so the number
above is checked rather than believed.

### The dataset that survives

**Humans in the Loop, "Car Parts and Car Damages"** — *"dedicated to the public
domain by Humans in the Loop under CC0 1.0 license"*, a first-party dedication
verified on their own page. 1,812 images, 24,851 polygons, 21 part classes that
are an assessor's taxonomy one-to-one, and **441 images carrying part polygons
AND damage polygons on the same photograph** — direct supervision for
damage-to-part mapping rather than two datasets stitched together.

Take it from the source. The Roboflow and Hugging Face re-uploads add only
augmentation you can regenerate and replace a clean CC0 grant with a CC BY tag
crediting the wrong party.

### What the notebook refuses to let you skip

1. **The split is by source photograph, not by file**, and the cell asserts the
   grouping is plausible before continuing. The leak above is the reason.
2. **`meta.json` decides which folder is which.** The two folders are named
   backwards in at least one mirror — `Car damages dataset/meta.json` holds the
   21 *part* classes. Trusting the directory name trains a part model on damage
   labels and nothing looks wrong.
3. **Nothing is dropped silently.** Unmapped classes, non-polygon shapes and
   empty annotations are counted and printed, with a warning past 5%.
4. **The cross-source number is published first.** HITL is US/UK/EU
   salvage-auction photography; `carparts-seg` is South-East Asian dealer
   classifieds. They share class names and share no photograph, camera or
   continent, which makes it the one honest out-of-distribution probe available —
   the thing the building domain never had, and whose absence let a 0.9986 score
   coexist with fifteen false alarms out of fifteen (README 7.11).

### Two limits to state rather than discover

* **HITL documents who annotated its images and not who supplied them.** No stock
  watermarks were found in the frames opened — a different situation from the
  iStock and Getty findings in ADR-034 — but the provenance is unconfirmed. Send
  that email before publishing a checkpoint.
* **There is no left/right distinction.** `Front-door`, not `left-front-door`,
  which is the same limit `damage_position` already refuses to guess past. CC0
  imposes no copyleft so side tagging could be added, but that is a labelling
  project, not a training run.

### The architecture is settled by latency, before training starts

Measured at four threads on the production CPU: `yolo11n-seg` is **83 ms at
640 px**, against the vehicle specialist's 139 ms, so damage plus parts in series
is **~222 ms** — inside the 150–250 ms budget, at the top of it. 768 px and
larger backbones do not fit, so the notebook does not offer them.

### Citation

> Humans in the Loop, *Car Parts and Car Damages Dataset*, CC0 1.0. Annotated by
> trainees of Beetroot Academy as part of a programme with internally displaced
> people across Ukraine.
