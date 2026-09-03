"""The building specialist: a crack patch classifier, and its false-alarm rate.

**This model was recommended against on a measurement that skipped two layers,
and the correction matters.** Fed fifteen intact rooms directly, the checkpoint
flagged **15 of 15**. Posted through the live pipeline, the same fifteen produce
**1 of 15** -- because the gate rejects seven as not-damage photographs and the
router sends seven to `other`. The first number is about the checkpoint; the
second is about the product, and only the second is what a claimant meets.

What it is: `mobilenetv3_small_100` fine-tuned on METU/Özgenel (CC BY 4.0;
Özgenel & Gönenç Sorguç, ISARC 2018; 40,000 patches at 227×227 from 458 parent
photographs of METU campus buildings in Ankara). Trained in
`notebooks/train_metu_crack.ipynb`, split by parent photograph rather than by
patch, seed 20260902, split fingerprint `c2e6ff005d376efc`.

Its held-out numbers are excellent: **accuracy 0.9986, precision 0.9973, recall
1.0000**, zero false negatives across 7,200 patches from 91 clusters it never
trained on, at 200 ms per photograph on the production CPU.

In isolation its behaviour on ordinary rooms is terrible, at every threshold:

    threshold   intact rooms flagged   of their tiles   cracked walls   of their tiles
    0.5             15/15                  96.5%           60/60           85.9%
    0.99            15/15                  90.2%           59/60           79.4%
    0.9999          15/15                  74.1%           59/60           71.0%

It even calls a *higher* share of an undamaged living room's tiles a crack than
of a genuinely cracked wall's -- off its training distribution it is not merely
uncalibrated, it is inverted. So no threshold is offered as a fix, and the
trained default is kept rather than one chosen to look better on fifteen rooms.

Through the pipeline it is a different thing entirely:

    posted to /v1/analyze     gate rejected   routed elsewhere   flagged
    15 intact rooms                 7                7           1 / 15
    60 cracked walls                0                1          59 / 60

**59 of 60 and 1 of 15.** The gate and the router are doing the work the
isolated measurement bypassed, which is the argument for measuring a product
rather than a checkpoint -- and the reason the earlier recommendation against
connecting this was wrong.

Both numbers are kept, because they answer different questions and quoting only
the friendlier one would be choosing the measurement that flatters the decision.
`scripts/eval_metu_crack.py` produces the first; `scripts/eval_building_endtoend.py`
produces the second. README section 7.11 holds both.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from biovision.models.base import DamageRegion, SpecialistAssessment
from biovision.pipeline.types import PreparedImage
from biovision.schemas.analyze import Finding
from biovision.schemas.enums import DamageType, Severity

logger = logging.getLogger(__name__)

#: ImageNet statistics, matching the training transform in the notebook. Wrong
#: values here would not raise -- they would quietly shift every score.
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

#: The grid the tiling measurement used, so this and README 7.11 describe the
#: same procedure. 4x4 plus the full frame is 17 forward passes.
GRID = 4

#: A tile smaller than this carries less signal than the resize artefacts it
#: introduces, so it is not worth an inference.
MIN_TILE_PIXELS = 32

#: The threshold the training run produced. Deliberately not tuned: the sweep in
#: the module docstring shows no threshold separates rooms from walls, so a
#: number picked from those fifteen rooms would be a number picked by looking at
#: the answer -- the mistake README sections 7.3, 7.9 and 7.10 each refused.
THRESHOLD = 0.5

#: Fed straight to the checkpoint, bypassing the gate and the router. This is
#: what the model does, and it is why it was nearly not connected.
ISOLATED_FALSE_ALARM_ROOMS = 15
ISOLATED_FALSE_ALARM_TOTAL = 15

#: Posted to the live API, which is what a claimant actually reaches. Measured
#: against the 15 residential interiors that survived individual review in
#: `konut_eval`, every verdict recorded with a reason in `verdicts.csv`.
FALSE_ALARM_ROOMS = 1
FALSE_ALARM_TOTAL = 15

#: And what it finds, measured the same way, on 60 reviewed masonry photographs.
RECALL_FOUND = 59
RECALL_TOTAL = 60

#: What the model scored on data drawn from its own training distribution. Kept
#: beside the false-alarm count on purpose: the distance between these two is the
#: entire point, and separating them would let either be quoted alone.
HELD_OUT_ACCURACY = 0.9986
HELD_OUT_RECALL = 1.0000
SPLIT_FINGERPRINT = "c2e6ff005d376efc"

CITATION = (
    "Özgenel, Ç.F. & Gönenç Sorguç, A. (2018), Performance Comparison of Pretrained "
    "Convolutional Neural Networks on Crack Detection in Buildings, ISARC 2018, "
    "Berlin. Mendeley 5y9wdsg2zt, CC BY 4.0."
)

WARNING_TR = (
    f"Bu model {RECALL_TOTAL} çatlak fotoğrafının {RECALL_FOUND} tanesini buldu ve "
    f"hasarsız {FALSE_ALARM_TOTAL} konut fotoğrafının {FALSE_ALARM_ROOMS} tanesinde "
    "yanlış alarm verdi. Ölçüm setleri küçük ve Türk konut iç mekânı içermiyor. "
    "Buradaki bulgular bir hasar tespiti değil, bakılması gereken yer önerisidir; "
    "hasarın miktarını ve sebebini yalnızca ruhsatlı bir eksper belirleyebilir."
)


def tiles(rgb: np.ndarray, grid: int = GRID) -> list[tuple[int, int, int, int]]:
    """Tile boxes as (left, top, right, bottom), the full frame first.

    Overlapping by half a tile, because a crack running along a boundary would
    otherwise be split into two fragments too small to name -- which looks
    exactly like the spatial dilution the grid exists to remove.

    Returns boxes rather than crops so a firing tile can become a finding's
    bounding box without a second pass.
    """
    height, width = rgb.shape[:2]
    boxes = [(0, 0, width, height)]
    if grid < 2:
        return boxes
    step_x, step_y = width / grid, height / grid
    for row in range(grid):
        for column in range(grid):
            left = max(0, int(column * step_x - step_x / 2))
            top = max(0, int(row * step_y - step_y / 2))
            right = min(width, int((column + 1.5) * step_x))
            bottom = min(height, int((row + 1.5) * step_y))
            if right - left > MIN_TILE_PIXELS and bottom - top > MIN_TILE_PIXELS:
                boxes.append((left, top, right, bottom))
    return boxes


class BuildingCrackSpecialist:
    """Per-tile crack classification over a building photograph."""

    def __init__(self, checkpoint: Path, num_threads: int = 4) -> None:
        import timm
        import torch

        self._torch = torch
        torch.set_num_threads(num_threads)

        saved = torch.load(checkpoint, map_location="cpu", weights_only=False)
        self._size = int(saved["imgsz"])
        self._model = timm.create_model(saved["model_name"], pretrained=False, num_classes=1)
        self._model.load_state_dict(saved["state_dict"])
        self._model.eval()
        self._architecture = str(saved["model_name"])

        logger.warning(
            "building crack specialist loaded (%s, fingerprint %s). Held-out accuracy "
            "%.4f on METU. End to end: %d/%d cracked walls found, %d/%d intact rooms "
            "falsely flagged. Fed directly, bypassing the gate, it flags %d/%d intact "
            "rooms -- so these findings are suggestions, never a determination.",
            self._architecture,
            SPLIT_FINGERPRINT,
            HELD_OUT_ACCURACY,
            RECALL_FOUND,
            RECALL_TOTAL,
            FALSE_ALARM_ROOMS,
            FALSE_ALARM_TOTAL,
            ISOLATED_FALSE_ALARM_ROOMS,
            ISOLATED_FALSE_ALARM_TOTAL,
        )

    @property
    def name(self) -> str:
        return f"metu-crack-patch-{self._architecture}"

    @property
    def ready(self) -> bool:
        return True

    @property
    def domain(self) -> str:
        return "building"

    @property
    def evaluation_size(self) -> int:
        """How many photographs stand behind this specialist's published figures.

        75 -- 60 cracked walls and 15 intact rooms, each reviewed individually.
        Exposed rather than hidden because the orchestrator decides whether to
        caveat a result from the size of its evidence, and a specialist that
        stays quiet about how little it was measured on would earn a silence it
        has not paid for.
        """
        return RECALL_TOTAL + FALSE_ALARM_TOTAL

    def analyze(self, image: PreparedImage) -> list[Finding]:
        return self.assess_pixels(image.pixels).findings

    def assess(self, image: PreparedImage) -> SpecialistAssessment:
        return self.assess_pixels(image.pixels)

    def _scores(self, rgb: np.ndarray, boxes: list[tuple[int, int, int, int]]) -> np.ndarray:
        torch = self._torch
        from PIL import Image

        batch = []
        for left, top, right, bottom in boxes:
            crop = Image.fromarray(rgb[top:bottom, left:right]).resize(
                (self._size, self._size), Image.Resampling.BILINEAR
            )
            array = np.asarray(crop, dtype=np.float32) / 255.0
            batch.append(((array - MEAN) / STD).transpose(2, 0, 1))
        with torch.no_grad():
            logits = self._model(torch.from_numpy(np.stack(batch))).squeeze(1)
            scores: np.ndarray = torch.sigmoid(logits).numpy()
        return scores

    def assess_pixels(self, rgb: np.ndarray) -> SpecialistAssessment:
        """Findings from the tiles that fired, and their union as the region.

        The full frame is scored with the tiles but never becomes a finding: a
        box around the whole photograph locates nothing, and reporting it would
        make the damaged-area ratio 1.0 on any photograph the model dislikes.
        """
        boxes = tiles(rgb)
        try:
            scores = self._scores(rgb, boxes)
        except Exception:
            logger.exception("building crack inference failed; reporting no findings")
            return SpecialistAssessment(findings=[], region=None)

        height, width = rgb.shape[:2]
        frame_area = float(height * width)
        findings: list[Finding] = []
        covered = np.zeros((height, width), dtype=bool)

        for index, (box, score) in enumerate(zip(boxes, scores, strict=True)):
            if index == 0 or score <= THRESHOLD:
                continue
            left, top, right, bottom = box
            covered[top:bottom, left:right] = True
            findings.append(
                Finding(
                    type=DamageType.CRACK,
                    score=float(score),
                    bbox=(left, top, right, bottom),
                    area_ratio=float((right - left) * (bottom - top)) / frame_area,
                    # A tile is a patch of wall, not a measured extent, so the
                    # band never rises above `minor` here however many fire.
                    # Letting area drive it would turn "the model dislikes this
                    # photograph" into "your house is severely damaged".
                    severity=Severity.MINOR,
                    # End-to-end recall, not METU's held-out 1.0000: what the
                    # class finds through the whole pipeline is the figure a
                    # reader can act on.
                    class_recall=RECALL_FOUND / RECALL_TOTAL,
                    # Clears the project's stated 0.40 bar comfortably. The
                    # warning on the response carries the caveat that belongs
                    # here instead: small sets, and no Turkish residential
                    # interiors in either of them.
                    class_reliable=True,
                )
            )

        if not findings:
            return SpecialistAssessment(findings=[], region=None)

        return SpecialistAssessment(
            findings=findings,
            region=DamageRegion(
                area_ratio_image=float(covered.sum()) / frame_area,
                # There is no building segmenter, so there is no building-relative
                # denominator. Null rather than the frame ratio: substituting one
                # would make a field mean two different things.
                area_ratio_vehicle=None,
                vehicle_frame_share=None,
                instances=len(findings),
                confidence_floor=THRESHOLD,
            ),
        )
