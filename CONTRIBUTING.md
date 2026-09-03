# Contributing

This is a portfolio project, so the honest answer about pull requests is: they
are welcome and they may sit for a while. Issues get read.

What follows is not process for its own sake. It is the small number of rules
that make this repository's claims checkable, and a change that breaks one of
them makes the README wrong.

## Running it

```bash
cd backend && uv sync && uv run ruff check . && uv run mypy && uv run pytest
cd frontend && pnpm install && pnpm exec tsc --noEmit
```

`uv run pytest` runs without any model weights: the mock backend exists so the
whole suite is runnable on a laptop with no downloads. `BIOVISION_MODEL_BACKEND=real`
loads actual checkpoints and needs `scripts/fetch_weights.py` to have run.

## The rules that are not style

**Every number in the README is measured, and the script that produced it is in
`backend/scripts/`.** If you change a threshold, a prompt or a model, re-run the
relevant `eval_*.py` and update the number. A stale number is worse than no
number, because it reads as a measurement.

**Thresholds are stated, not fitted.** Several constants in this codebase are
deliberately *not* the value that scores best — `SURFACE_MARGIN = 0.0`,
`MIN_ZONE_SHARE = 0.02`, the specialist's `THRESHOLD = 0.5`. Each has a comment
saying which better-scoring value was refused and why. Picking a number because
it looks good on the evaluation set is picking it by looking at the answer, and
the README publishes those refusals as findings. If you tune one, say what you
tuned it against and hold that set out.

**A held-out score is not a result on its own.** README section 7.11 documents a
model that scored 0.9986 on held-out data and flagged fifteen intact rooms out of
fifteen. Any new model needs a number from a *different source* than its training
data, or an explicit statement that no such source exists.

**Look at the images.** `scripts/review_set.py` exists because an evaluation set
was once assembled from Wikimedia category names and turned out to contain a
painting in the `water` class and freeze-dried ice cream in `crack`. Candidates
go through it; `tests/unit/test_eval_set_integrity.py` fails if an image reaches
a set without a recorded verdict.

**Verify a licence by opening the files, not by reading the tag.** Three datasets
in `NOTICE.md` are recorded as rejected because their MIT / Public Domain / CC BY
tags sat over scraped iStock previews, Google Images downloads, and a repository
whose own licence field is null. Read filenames. Look at any `train_batch*.jpg` a
model repository ships.

**Nulls are load-bearing.** `area_ratio_vehicle` is null when no vehicle was
located, rather than falling back to the frame ratio. A field that means one
thing on one request and another thing on the next is worse than a field that is
sometimes absent. Do not add a silent fallback.

**The enum may not advertise what no model can emit.** `tire_flat` and
`surface_damage` were both removed for this reason (ADR-026, ADR-034).

## Commits

Conventional-commit prefixes, and a body that says *why* rather than *what* — the
diff already says what. If a change was driven by a measurement, put the numbers
in the message. `git log` is the second-best documentation this project has.

## Licence

AGPL-3.0, because the vehicle specialist links Ultralytics. Contributions are
accepted under the same licence. If you add a dataset or a checkpoint, add its
terms to `NOTICE.md` in the same change — including, and especially, when the
terms are unclear.
