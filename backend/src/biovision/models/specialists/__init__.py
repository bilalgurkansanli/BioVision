"""Specialist implementations, and the set of names `domains.yaml` may refer to.

`domains.yaml` names a specialist; this package provides it. The two are joined by
:data:`KNOWN_SPECIALISTS`, which exists so that a name with no implementation
behind it is a startup failure rather than a domain that quietly reports "no
specialist available" forever.

That distinction matters precisely *because* adding a domain is meant to be a
one-line edit: the easier the edit, the more likely the typo, and the failure it
would otherwise produce is indistinguishable from this project's honest answer.
"""

from __future__ import annotations

#: Every specialist name a domain entry is allowed to reference.
#: Add a name here in the same change that adds its implementation module.
KNOWN_SPECIALISTS: frozenset[str] = frozenset(
    {
        # Phase 5: CarDD fine-tuned YOLO segmentation, six damage classes.
        # Trained by this project (notebooks/train_cardd_yolo.ipynb) rather than
        # taken from a public checkpoint, because a checkpoint whose train/test
        # split is unknown makes the reported mAP unverifiable.
        "vehicle_yolo",
    }
)

__all__ = ["KNOWN_SPECIALISTS"]
