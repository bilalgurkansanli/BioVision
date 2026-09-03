"""Measured per-class performance, attached to the findings it describes.

These are the numbers from README section 7.3 -- the vehicle specialist evaluated
on VehiDE's held-out validation set, 2,322 images. They live here so the API can
return them beside each finding.

**Why the response carries them.** The project's claim is that the system states
what it cannot do. It did, in the README, and the screen said "dent · 42%" with
nothing beside it. Someone photographing a written-off car saw one finding and
reasonably concluded the system had judged the damage light -- when what actually
happened is that this class has a recall of 0.253 and the model found a quarter of
what was there.

A confidence score answers "how sure is the model about this box". Recall answers
"how much does this model tend to miss". A reader needs both, and only one of them
was on screen.

`scratch` scoring 0.239 with six times the training data of `glass_shatter` at
0.782 is not a bug to be tuned away: a scratch boundary is a judgement call for
whoever drew the polygon, and ADR-030 records the 960 px run that ruled out
resolution as the cause. Until that class is re-annotated, these are the numbers,
and hiding them would only move the surprise to whoever relies on the output.
"""

from __future__ import annotations

from dataclasses import dataclass

from biovision.schemas.enums import DamageType


@dataclass(frozen=True)
class ClassPerformance:
    """What was measured for one damage class, on the held-out split."""

    map50: float
    recall: float
    precision: float

    @property
    def reliable(self) -> bool:
        """Whether this project is willing to call the class usable.

        The line is drawn at recall 0.40 -- below it the model misses more than it
        finds, and a client showing the result without a caveat would be passing on
        a confidence the evidence does not support. The threshold is a judgement
        call, published rather than hidden, like the severity floors.
        """
        return self.recall >= 0.40


#: Source: README section 7.3. Mask metrics on VehiDE's validation split, which the
#: training never saw. Update these together with that table -- a unit test asserts
#: the two agree.
VEHICLE_CLASS_PERFORMANCE: dict[DamageType, ClassPerformance] = {
    DamageType.GLASS_SHATTER: ClassPerformance(map50=0.782, recall=0.747, precision=0.797),
    DamageType.MISSING_PART: ClassPerformance(map50=0.649, recall=0.643, precision=0.710),
    DamageType.LAMP_BROKEN: ClassPerformance(map50=0.479, recall=0.480, precision=0.630),
    DamageType.PUNCTURED: ClassPerformance(map50=0.458, recall=0.468, precision=0.558),
    DamageType.TORN: ClassPerformance(map50=0.285, recall=0.302, precision=0.452),
    DamageType.DENT: ClassPerformance(map50=0.244, recall=0.253, precision=0.476),
    DamageType.SCRATCH: ClassPerformance(map50=0.239, recall=0.275, precision=0.410),
}
