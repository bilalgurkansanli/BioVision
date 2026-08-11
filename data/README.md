# Datasets

**No images are committed to this directory.** Each subdirectory holds a
`manifest.csv` recording, for every image: its source URL, its upstream license, and
its SHA-256. Images are fetched locally by the fetch script.

This keeps material whose license does not permit redistribution out of a public
AGPL repository while keeping the evaluation exactly reproducible: anyone can rebuild
the same set and verify they got the same bytes.

See [`../docs/DECISIONS.md`](../docs/DECISIONS.md) ADR-005.

| Directory | Purpose | Target size |
|---|---|---|
| `router_eval/` | Router confusion matrix (Phase 4) | ~50 images per domain |
| `router_calib/` | Temperature scaling split — **disjoint from `router_eval`** | ~25 images per domain |
| `gate_eval/` | Out-of-distribution rejection: selfies, screenshots, landscapes | ~100 images |

The calibration and evaluation splits must never overlap. Fitting a temperature on
the same images used to report ECE would produce a number that means nothing.

## The exception

The 20 golden-set images live in `backend/tests/golden/images/` and **are** committed.
They must run in CI without a network fetch, which means they have to be material the
author owns outright. They are photographed by Bilal Gürkan Şanlı — see
[`../NOTICE.md`](../NOTICE.md).

## Manifest format

```csv
filename,source_url,license,sha256,domain,notes
```
