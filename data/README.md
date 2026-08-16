# Datasets

**No images are committed to this directory.** Each subdirectory holds a
`manifest.csv` recording, for every image: its source URL, its upstream license, and
its SHA-256. Images are fetched locally by the fetch script.

This keeps material whose license does not permit redistribution out of a public
AGPL repository while keeping the evaluation exactly reproducible: anyone can rebuild
the same set and verify they got the same bytes.

See [`../docs/DECISIONS.md`](../docs/DECISIONS.md) ADR-005.

| Directory | Purpose | Size |
|---|---|---|
| `router_eval/` | Router confusion matrix | 30 per domain, 120 total |
| `router_calib/` | Temperature scaling split — **disjoint from `router_eval`** | 30 per domain, 120 total |
| `gate_eval/` | Out-of-distribution rejection: selfies, food, landscapes, screenshots, documents, animals | ~115 |
| `redaction_eval/` | Face-redaction miss rate (WIDER FACE subset) | 50 images, 95 faces |

The calibration and evaluation splits must never overlap. Fitting a temperature on
the same images used to report ECE would produce a number that means nothing.

## Rebuilding the sets

```bash
uv run python -m scripts.fetch_commons --category "Category:..." --into ../data/_sources/<domain>
uv run python -m scripts.contact_sheet --source ../data/_sources/<domain> --out sheet.jpg
uv run python -m scripts.sample_router_set --domain <domain> --source ../data/_sources/<domain> \
    --count 60 --attribution ../data/_sources/<domain>/attribution.csv
```

`_sources/` is a scratch directory and is not committed either.

**The contact sheet step is not optional.** A category name does not describe its
contents. `Category:Broken telephone screens` contained a photograph of a Kraków
market square; `Category:Damaged objects` turned out to be museum conservation
material — water-stained postcards, archaeological finds, and chopping boards
with no damage at all. Both were only visible by looking. See ADR-028.

## Where each domain comes from

| Domain | Source | Licence |
|---|---|---|
| `vehicle` | VehiDE | Research use, per the authors' terms |
| `building` | Wikimedia Commons, RCE heritage survey | CC BY-SA 4.0, all 60 |
| `phone_screen` | Kaggle, DataCluster Labs cracked screens | CC0 as declared by the uploader, not independently verified |
| `other` | Wikimedia Commons, specific damaged-object categories | 8 different licences across 70 files |
| gate negatives | Wikimedia Commons, six out-of-scope categories | per file |

Licences are resolved **per file**, not per collection, and a file whose licence
cannot be read is skipped rather than guessed at.

`building` is one institution, one country, one era, and the archive photographs
each facade from several angles — so `--group-regex` keeps one building's frames
on one side of the eval/calib cut. Disjoint splits are not independent splits.

## The exception

The 20 golden-set images live in `backend/tests/golden/images/` and **are** committed.
They must run in CI without a network fetch, which means they have to be material the
author owns outright. They are photographed by Bilal Gürkan Şanlı — see
[`../NOTICE.md`](../NOTICE.md).

## Manifest format

```csv
filename,source_url,license,sha256,domain,notes
```
