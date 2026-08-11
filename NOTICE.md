# NOTICE

BioVision — Copyright (C) 2026 Bilal Gürkan Şanlı

This program is free software: you may redistribute it and/or modify it under the
terms of the **GNU Affero General Public License, version 3**, as published by the
Free Software Foundation. The complete license text is in [`LICENSE`](LICENSE),
reproduced verbatim.

BioVision is AGPL-3.0 because it links against Ultralytics YOLO, which is AGPL-3.0.
If you run a modified version of BioVision as a network service, you must offer its
users the corresponding source.

---

## Bundled assets and their licensing

### Golden-set images — `backend/tests/golden/images/`

The 20 regression images committed in this repository were **photographed by Bilal
Gürkan Şanlı**, who holds full copyright and releases them under the same AGPL-3.0
terms as the rest of this work. They are committed deliberately: the golden-set
regression test must run in CI without a network fetch, which rules out
manifest-and-download for these specific files.

No third-party photographs are committed to this repository.

### Evaluation and calibration images — `data/`

Not committed. Each set is represented by a `manifest.csv` recording the source URL,
the upstream license, and the SHA-256 of every image. Images are retrieved locally by
the fetch script. This keeps images whose licenses do not permit redistribution out
of a public AGPL repository, while keeping the evaluation exactly reproducible.

### Model weights — `backend/weights/`

Not committed. Downloaded by `backend/scripts/fetch_weights.py`, which verifies each
artifact against a pinned SHA-256 before installing it.

| Component | Source | License |
|---|---|---|
| Vehicle specialist (YOLO-seg) | Fine-tuned by this project on CarDD — see `notebooks/train_cardd_yolo.ipynb` | AGPL-3.0 (Ultralytics) |
| CarDD dataset | Obtained under the dataset's own access terms; **not redistributed here** | Upstream terms apply |
| Gate + Router (CLIP/SigLIP) | Upstream checkpoint | Upstream terms apply — recorded here once selected |
| Face detector — `face_detection_yunet_2023mar.onnx` | [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) | MIT |
| Plate detector | **None in v1** — plates are not redacted, see `docs/DECISIONS.md` ADR-015 | — |

The CarDD dataset is **not** redistributed by this repository in any form. The
training notebook consumes a copy obtained through the dataset's official access
process; the train/validation/test split and its random seed are pinned in the
notebook so the reported metrics are reproducible by anyone with their own copy.
