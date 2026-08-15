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
