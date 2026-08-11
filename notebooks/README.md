# Notebooks

## `train_cardd_yolo.ipynb` — Phase 5, not yet written

Fine-tunes YOLO segmentation on CarDD for the vehicle specialist, on a free Colab T4.

We train this ourselves rather than adopting a public checkpoint because a public
checkpoint has an unknown train/test split. Any leakage between it and our evaluation
split would make the per-class mAP table unverifiable — and that table is this
project's headline claim. See [`../docs/DECISIONS.md`](../docs/DECISIONS.md) ADR-003.

Requirements the notebook must satisfy, so the reported numbers mean something:

* the train/validation/test split and its **random seed** are pinned in the notebook;
* the CarDD copy is obtained through the dataset's official access process and is
  **never** committed or redistributed here;
* per-class metrics are exported to `docs/` and pasted into the README verbatim,
  including the classes that perform badly;
* the resulting checkpoint is published as a release artifact, not committed —
  `backend/scripts/fetch_weights.py` downloads it.

Blocked on the CarDD access request. Every other phase is independent of it.
