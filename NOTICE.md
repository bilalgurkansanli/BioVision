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
| Vehicle specialist (YOLO-seg) | Fine-tuned by this project on CarDD — see `notebooks/train_cardd_yolo.ipynb` | AGPL-3.0 (Ultralytics), plus the CarDD conditions below |
| CarDD dataset | Obtained under the dataset's own access terms; **not redistributed here** | PIC Lab / CAS — see below |
| Gate + Router (CLIP/SigLIP) | Upstream checkpoint | Upstream terms apply — recorded here once selected |
| Face detector — `face_detection_yunet_2023mar.onnx` | [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) | MIT |
| Plate detector | **None in v1** — plates are not redacted, see `docs/DECISIONS.md` ADR-015 | — |

### VehiDE — the training set actually used

VehiDE (Huynh et al., IEEE KSE 2023) is downloaded from Kaggle and is not
redistributed here. Kaggle labels it Apache 2.0; that label was applied by the
uploader, who is not the paper's authors. Downloading and training on it is
uncontroversial. **Publishing a checkpoint trained on it is held until the authors
confirm the licence** — the same standard applied to CarDD below, for the same
reason.

Any publication using VehiDE should cite:

> N. T. Huynh, N. N. D. Tran, A. T. Huynh, V.-D. Hoang and H. D. Nguyen, "VehiDE
> Dataset: New dataset for Automatic vehicle damage detection in Car insurance,"
> *2023 15th International Conference on Knowledge and Systems Engineering (KSE)*,
> IEEE, 2023. doi:10.1109/KSE59128.2023.10299490

### CarDD — surveyed, not used

Kept here because ADR-003's survey referenced it and because access is still worth
requesting: if it arrives, training on both and publishing the comparison is
strictly more informative than either alone.

The CarDD dataset is the property of the PIC Lab at the Chinese Academy of Sciences and
is obtained by signing their licensing form. It is **not** redistributed by this
repository in any form, and neither is any checkpoint trained on it — see
[`docs/DECISIONS.md`](docs/DECISIONS.md) ADR-025 for why the derived weights are treated
the same way as the data until the PIC Lab says otherwise.

Three conditions from their licence bear directly on this project:

* **Research use requires their prior consent.** That consent is the signed form.
* **Commercial use requires separate authorisation**, and the licence names "testing
  commercial systems" as an example. Showing this repository as a portfolio piece is not
  commercial use; deploying it inside an insurance product would be.
* **Redistribution of the dataset, in whole or in part, is forbidden without prior
  authorisation.**

Any publication using CarDD must cite:

> X. Wang, W. Li and Z. Wu, "CarDD: A New Dataset for Vision-Based Car Damage
> Detection," *IEEE Transactions on Intelligent Transportation Systems*, vol. 24, no. 7,
> pp. 7202–7214, 2023. doi:10.1109/TITS.2023.3258480

This applies to the per-class metrics table in the README, which is why the citation
appears there too. The train/validation/test split and its random seed are pinned in the
notebook, so those metrics are reproducible by anyone holding their own CarDD copy.
