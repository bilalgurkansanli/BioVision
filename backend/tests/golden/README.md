# Golden set

Twenty hand-picked images with their expected outputs, committed to this repository.
This is the regression tripwire for the whole system: any model swap, threshold
change or prompt edit that alters these outputs fails CI.

```
images/<name>.jpg        the input, photographed by the author (see ../../../NOTICE.md)
expected/<name>.json     the expected response, minus volatile fields
```

## What is compared

Not the whole response — `request_id` and `timing_ms` change every run, and asserting
on them would produce a test that fails for no reason. The comparison covers the
fields that encode a decision:

| Field | Compared |
|---|---|
| `domain` | exactly |
| `specialist_model` | exactly (including `null`) |
| `calibrated`, `domain_confidence_calibrated` | exactly |
| `warning` | exactly |
| `domain_confidence` | within a tolerance |
| `findings[].type` | as a sorted multiset |
| `findings[].score`, `area_ratio` | within a tolerance |
| `privacy.face_detector`, `plate_detector` | exactly (including `null`) |
| `vlm_description` | presence only, never content |

`vlm_description` is checked for presence and never for content: it comes from a
remote model that may be updated upstream at any time, and asserting on its prose
would make CI fail for something that is not a regression.

## Expected status codes

Some entries expect a failure rather than a response. Those carry the status and
error code instead:

```json
{ "expect_status": 422, "expect_error": "out_of_distribution" }
```

The set should include at least one of each: a vehicle photo with visible damage, an
undamaged object, a domain with no specialist, a low-confidence image, a selfie
(422), and an oversized or corrupt file.

## Regenerating

After a deliberate change, review each diff before accepting it:

```bash
uv run python -m scripts.update_golden --review
```

Regenerating without reading the diffs turns the tripwire into a rubber stamp.

## Status

**Empty.** The images do not exist yet. `test_golden.py` skips with a message rather
than passing vacuously — a green test over zero cases is worse than a skipped one,
because it reads as coverage.
