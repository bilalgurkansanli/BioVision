# Notebooks

## `train_cardd_yolo.ipynb` — the vehicle specialist

Fine-tunes YOLO segmentation on CarDD for the vehicle specialist, on a free Colab T4.

We train this ourselves rather than adopting a public checkpoint because a public
checkpoint has an unknown train/test split. Any leakage between it and our evaluation
split would make the per-class mAP table unverifiable — and that table is this
project's headline claim. See [`../docs/DECISIONS.md`](../docs/DECISIONS.md) ADR-003.

---

## Getting CarDD

The dataset belongs to the PIC Lab at the Chinese Academy of Sciences and is released
by signature, not by download link.

1. Read the licence at <https://cardd-ustc.github.io/> — the form is linked there as
   `docs/CarDD_license.pdf`.
2. Fill in affiliation, name, email and signature.
3. Email it to Xinkuang Wang, `wangxk0624@mail.ustc.edu.cn`, and ask for the download
   link.

**Ask two extra questions in that email**, because both are cheaper to settle now than
after the model is trained:

* whether a **checkpoint fine-tuned on CarDD may be redistributed** (a GitHub release
  attached to an AGPL-3.0 repository). The licence forbids distributing "all or part of
  the dataset" and does not say where derived weights fall. Until they answer, this
  project does not publish the checkpoint — [ADR-025](../docs/DECISIONS.md).
* whether **commercial evaluation** is permitted, should the work go beyond a portfolio
  piece. The licence names "testing commercial systems" as requiring authorisation.

The dataset is ~4,000 images with ~9,000 annotated instances across six classes.

---

## Running the notebook

Put the CarDD copy at `MyDrive/datasets/CarDD/`, open the notebook in Colab, select a
T4 runtime, and run the cells in order.

Settings are pinned at the top and chosen deliberately:

| Setting | Value | Why |
|---|---|---|
| `MODEL` | `yolo11s-seg.pt` | Measured on CPU at the production thread count: 139 ms median per image at 640 px, against 483 ms for `yolo11m-seg`. The medium model pushes a request past a second on the VPS and would force a queue. |
| `IMGSZ` | 640 | 960 roughly doubles inference cost (319 ms). Worth revisiting only if `scratch` recall is poor — thin damage is what downscaling costs you. Retrain at 960 rather than running a 640-trained model at 960; YOLO performs best at the size it was trained on. |
| `SEED` | 20260311 | Pinned, with `deterministic=True`, so the split and the reported metrics are reproducible. |
| `EPOCHS` | 100, `patience=20` | Early stopping keeps a free-tier session viable. |

Expect roughly 2–3 hours on a free T4.

### The conversion has been rehearsed

The COCO→YOLO conversion and the split were executed against synthetic COCO before any
real data existed, because their first contact with 4,000 images is a bad place to
discover a bug. Two behaviours came out of that rehearsal:

* **RLE masks raise a clear error.** COCO stores masks as polygons *or* as run-length
  encoding. This converter reads polygons; fed RLE it used to fail with
  `TypeError: unsupported operand type(s) for /: 'str' and 'int'`, which is accurate and
  unhelpful. It now says what happened and what to do about it.
* **Nothing is dropped silently.** Images with no usable polygon, annotations whose file
  is missing, degenerate polygons and `iscrowd` instances are all counted and printed,
  and losing more than 5% prints a warning. A converter that quietly turns 4,000 images
  into 3,100 would change the class balance and poison every number downstream, and
  nothing later in the pipeline could detect it.

---

## After training

1. Download `best.pt` → `backend/weights/cardd_yolo_seg.pt`.
2. Restart the API. `/health` lists the new component; the vehicle domain starts
   measuring. **No code change** — the specialist is loaded by filename.
3. Paste the per-class table from the evaluation cell into README section 7,
   **verbatim, including the classes that perform badly**. With the citation.
4. Record the split fingerprint the notebook prints alongside the metrics. If it ever
   differs, the numbers are not comparable to the published ones.
5. Run the golden set: `uv run python -m scripts.update_golden`, inspect the diff, and
   commit the expected outputs.

**`calibrated` stays `false` after all this.** The response will carry
`specialist_model: "cardd-yolo-seg-v1"` and real findings, but segmentation confidences
are not calibrated and `severity` is a rule over area ratio rather than a fitted model —
which `severity_calibrated: false` already reports. "I measured this" and "I have
calibrated how sure I am" remain two separate claims.

### Requirements the notebook satisfies, so the numbers mean something

* the train/validation/test split and its **random seed** are pinned, and the split is
  fingerprinted;
* the CarDD copy is obtained through the official access process and is **never**
  committed or redistributed here;
* per-class metrics are printed as markdown and pasted into the README verbatim,
  including the classes that perform badly;
* the checkpoint is **not** published — see [ADR-025](../docs/DECISIONS.md).
