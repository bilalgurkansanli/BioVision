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

```bash
kaggle datasets download -d hendrichscullen/vehide-dataset-automatic-vehicle-damage-detection
```

No form, no wait. 2.3 GB. Put the extracted copy at `MyDrive/datasets/vehide/`.

**The archive nests its directories twice** — `image/image/` and
`validation/validation/`. The notebook expects exactly that, because assuming
otherwise produced a run reporting "2,324 images missing" before anyone looked at
the tree.

### One licence question to settle before publishing anything

Kaggle labels the dataset Apache 2.0, but that label was applied by the uploader,
not by the authors (Huynh et al., HCMUTE, IEEE KSE 2023). Downloading and training
is fine. **Publishing a checkpoint trained on it needs one line of confirmation
from the authors first** — `cvis.hcmute.edu.vn` lists their contact. Having read
CarDD's licence rather than assuming it, doing less here would be inconsistent.

---

## What is actually in it

Measured with `uv run python -m scripts.inspect_vehide`, not taken from the dataset
card:

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
CarDD's `crack` and `tire_flat` are gone — VehiDE has no such annotations, and
advertising classes the model can never emit would be a lie in the schema itself.

---

## Running the notebook

Open in Colab, select a T4 runtime, run the cells in order. Roughly 2–3 hours.

| Setting | Value | Why |
|---|---|---|
| `MODEL` | `yolo11s-seg.pt` | Measured on CPU at the production thread count: 139 ms median per image at 640 px, against 483 ms for `yolo11m-seg`. The medium model pushes a request past a second on the VPS and would force a queue this design does not have. |
| `IMGSZ` | 640 | A real downscale from VehiDE's 1.7M px average. 960 roughly doubles inference cost (319 ms) and is the fallback **if the `scratch` row disappoints** — thin damage is what resolution buys. Retrain at 960 rather than running a 640-trained model at 960; YOLO performs best at the size it trained on. |
| `SEED` | 20260311 | Pinned, with `deterministic=True`. The split is also fingerprinted. |
| `EPOCHS` | 100, `patience=20` | Early stopping keeps a free-tier session viable. |

### The converter has been rehearsed, and the rehearsal has a lesson

Both converters — COCO for CarDD, VIA for VehiDE — were executed against synthetic
data before any real dataset existed. That caught real defects: RLE masks failing
with an unhelpful `TypeError`, and silent drops of images with no usable polygon.

**It also missed the biggest problem.** VehiDE does not write standard VIA. Its
regions are flat — `{"all_x": [...], "all_y": [...], "class": "tray_son"}` — with
no `shape_attributes` or `region_attributes`. The converter read the real file
without error and found 36,081 regions with zero classes, because the synthetic
fixture had been built on the same assumption as the code.

A rehearsal proves the code runs. It cannot test an assumption it shares with the
implementation. Both shapes are now accepted, and `inspect_via` prints which one
it found before anything is converted.

Nothing is dropped silently: unmapped classes, non-polygon shapes, images with no
usable region, and missing files are all counted and printed, with a warning past
5%. That warning fired at 100% on the first real run and named the files — which
is exactly what it was added for.

---

## After training

1. Download `best.pt` → `backend/weights/vehide_yolo_seg.pt`.
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
