"""Generate `notebooks/train_metu_crack.ipynb`.

Written as a generator rather than edited as JSON because a notebook is a bad
thing to hand-edit and a worse thing to review in a diff. Run it and commit the
output:

    uv run python -m scripts.build_konut_notebook
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

NOTEBOOK = Path(__file__).resolve().parents[2] / "notebooks" / "train_metu_crack.ipynb"


def md(text: str) -> dict[str, object]:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip().splitlines(True)}


def code(text: str) -> dict[str, object]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text.strip().splitlines(True),
    }


CELLS: list[dict[str, object]] = [
    md(
        """
# The konut crack patch classifier — METU/Özgenel, CC BY 4.0

**What this trains, and the three things it is not.**

It trains a binary *patch* classifier: given a 227×227 crop of a building
surface, is there a crack in it. That is all. It is not a damage assessment, it
does not measure extent, and it does not name a peril.

**Why a patch classifier rather than a detector.** Measuring the zero-shot konut
router showed the failure was spatial dilution, not encoder weakness: a hairline
crack is a fraction of a percent of a photograph, and one global embedding of a
frame that is 99% intact wall is an embedding of an intact wall. Cutting the
frame into an overlapping grid moved the same weights by a wide margin. So the
right granularity here is a patch — and METU/Özgenel *is* 40,000 labelled
patches. The dataset and the finding agree, which is the only reason this shape
was chosen.

**Why this dataset and not the ones that looked better.** Two Roboflow projects
carry exactly the class list this product needs — `crack, stain, mold, damp,
peeling_paint, water_seepage` — and label themselves MIT and Public Domain. Both
were opened and looked at before either was used:

* `building-damage-insurance` (5,178 images, "MIT"): more than half the visible
  filenames are `istockphoto-<id>-612x612.jpg` — **iStock previews**, scraped at
  the free size. Getty's photographs are not MIT because an uploader typed MIT.
* `property-defect-issues` (604 images, "Public Domain"): the filenames are
  `download.jpg`, `download (1).jpg` … `images (23).jpg` — **Google Images
  default download names** — alongside a Seattle chimney-sweep company's website
  image and a UK damp-proofing contractor's job photograph.

Neither licence is the uploader's to grant. So the classes this product most
needs stay untrained, and what gets trained is the one thing with a licence that
survives reading: **METU/Özgenel, CC BY 4.0, verified against Mendeley
directly** — and, usefully, Turkish, since the source photographs are METU
campus buildings in Ankara.

**Read this before quoting any number this notebook prints.**

There is no independent Turkish residential evaluation set. 217 candidates were
fetched from eight Wikimedia categories and every one was looked at; `water` and
`crack` both came back with **zero** usable images (README 7.11). So the headline
here is measured on METU's own held-out split, and a number measured on a
dataset's own split says how well the model learned *that* dataset. It is
reported as such, everywhere, without exception.

The one genuinely out-of-distribution probe available is small and is run anyway:
**15 intact residential interiors** from the reviewed `konut_eval` set, from a
different source entirely. It cannot measure recall. It can measure false
alarms — which is exactly the failure that shipped in the vehicle specialist for
a whole release, and exactly what the one public crack checkpoint failed on
(64% of intact rooms).
"""
    ),
    md(
        """
## 1. Where this runs

Kaggle, for the same reasons as the vehicle notebook: 30 stated GPU hours a
week, no 90-minute idle disconnect, and background execution so a closed laptop
lid does not end the run. Colab works too; the setup cell detects which.

This model is small enough that the platform hardly matters — the point of
picking it is CPU inference later, not GPU training now.
"""
    ),
    code(
        """
import os, sys, json, time, random, hashlib
from pathlib import Path

ON_KAGGLE = Path("/kaggle/input").exists()
ON_COLAB = "google.colab" in sys.modules
WORK = Path("/kaggle/working") if ON_KAGGLE else Path("/content") if ON_COLAB else Path.cwd()
print("kaggle" if ON_KAGGLE else "colab" if ON_COLAB else "local", "->", WORK)

!pip -q install timm==1.0.11 pillow scikit-learn

import numpy as np, torch, timm
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from PIL import Image

SEED = 20260902
random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
torch.cuda.manual_seed_all(SEED)
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print("torch", torch.__version__, "|", DEVICE)
if DEVICE == "cuda": print(torch.cuda.get_device_name(0))
"""
    ),
    md(
        """
## 2. The dataset, and its citation obligation

**Özgenel, Ç.F. & Gönenç Sorguç, A. (2018)**, *Performance Comparison of
Pretrained Convolutional Neural Networks on Crack Detection in Buildings*,
ISARC 2018, Berlin. Mendeley `5y9wdsg2zt`, **CC BY 4.0**.

CC BY requires attribution, so the citation travels with anything published from
this — the README, the model card, the response metadata. It is not optional and
it is not a footnote.

40,000 images, 20,000 cracked and 20,000 not, at 227×227, generated from **458
high-resolution parent photographs** at 4032×3024. No augmentation was applied by
the authors.

On Kaggle the mirror is `arunrk7/surface-crack-detection`; add it through *Add
Data*. The cell below **searches** for the `Positive`/`Negative` pair rather than
assuming a path, and prints what is actually mounted when it cannot find them.
The first version of this notebook assumed the path, and a mirror that nests one
level deeper ended the run at cell 2 — the same mistake the vehicle notebook
records against VehiDE's doubly-nested archive.

Counts are verified rather than trusted: a mirror with a different total is a
different dataset, whatever its title says.
"""
    ),
    code(
        """
# Find the dataset rather than assume where it is. The vehicle notebook's README
# records the same class of bug on VehiDE -- that archive nests its directories
# twice, and assuming otherwise cost a run before anyone looked at the tree.
# Assuming it again here cost another one, so this searches, and prints the tree
# when it fails instead of only saying no.
def find_root(bases, depth=3):
    for base in bases:
        if not base.exists():
            continue
        frontier, level = [base], 0
        while frontier and level <= depth:
            nxt = []
            for d in frontier:
                names = {c.name.lower(): c for c in d.iterdir() if c.is_dir()}
                if "positive" in names and "negative" in names:
                    return d, names["positive"], names["negative"]
                nxt.extend(names.values())
            frontier, level = nxt, level + 1
    return None, None, None

ROOT, POS_DIR, NEG_DIR = find_root([Path("/kaggle/input"), WORK])
if ROOT is None:
    print("Positive/ and Negative/ not found. What IS mounted:")
    for base in (Path("/kaggle/input"), WORK):
        if not base.exists():
            continue
        for d in sorted(base.iterdir()):
            print(" ", d)
            if d.is_dir():
                for sub in sorted(d.iterdir())[:8]:
                    print("     ", sub.name, "(dir)" if sub.is_dir() else "")
    raise SystemExit("dataset not found -- see the tree above and fix the mount")
print("found at", ROOT)

IMAGE_GLOBS = ("*.jpg", "*.jpeg", "*.png")
def listing(folder):
    out = []
    for pattern in IMAGE_GLOBS:
        out.extend(folder.rglob(pattern))
    return sorted(out)

positive, negative = listing(POS_DIR), listing(NEG_DIR)
print(f"Positive {len(positive)}  Negative {len(negative)}  total {len(positive)+len(negative)}")
assert len(positive) == len(negative) == 20000, (
    f"got {len(positive)}/{len(negative)}, published is 20,000/20,000 -- "
    "a different mirror, or a partial download"
)

w, h = Image.open(positive[0]).size
print("patch size", w, "x", h)
assert (w, h) == (227, 227)
"""
    ),
    md(
        """
## 3. The split, and the leak it exists to prevent

**40,000 patches came from 458 photographs — about 87 patches per photograph.**
Splitting at the patch level would put crops of the *same wall, metres apart*
into both train and test, and the resulting accuracy would measure memorisation
of 458 walls rather than recognition of cracks. On a dataset with this ratio that
is not a rounding error; it is most of the score.

The published 97–99% figures for this dataset are, as far as can be told from
the papers, patch-level splits. Treat them accordingly.

The parent photograph is not recorded in the filenames, so it has to be
recovered. Patches of one 4032×3024 photograph share illumination, white balance
and surface tone — low-dimensional properties that survive downscaling, unlike
the crack, which is high-frequency. So the split clusters on colour statistics
with **k fixed at 458, the known parent count**, which makes it a fact from the
dataset description rather than a tuned hyperparameter.

**This recovers the grouping approximately, not exactly, and the notebook says
so rather than implying a clean split.** What matters is that it is much better
than random, and the cell after it measures exactly how much that is worth: it
evaluates the same trained model on held-out *clusters* and on a random
*patch* split, and prints the gap. That gap is this dataset's leakage, and it is
the number the published 97–99% figures do not report.
"""
    ),
    code(
        """
# Patches from one 4032x3024 photograph share illumination, white balance and
# surface tone. Those are low-dimensional and survive downscaling; the crack
# itself is high-frequency and mostly does not. So cluster on colour statistics
# with k fixed at the KNOWN parent count -- 458 is not a hyperparameter here, it
# is a fact from the dataset description.
#
# This recovers the parent grouping approximately, not exactly, and the notebook
# says so rather than implying a clean split. What it buys is measurable and is
# measured two cells down.
from sklearn.cluster import MiniBatchKMeans

def signature(path):
    a = np.asarray(Image.open(path).convert("RGB").resize((16, 16), Image.BILINEAR),
                   dtype=np.float32) / 255.0
    return np.concatenate([a.mean(axis=(0, 1)), a.std(axis=(0, 1)),
                           a.mean(axis=1).flatten(), a.mean(axis=0).flatten()])

t0 = time.time()
paths = positive + negative
labels = [1]*len(positive) + [0]*len(negative)
features = np.stack([signature(p) for p in paths])
print(f"described {len(paths)} patches in {time.time()-t0:.0f}s, {features.shape[1]} dims")

PARENTS = 458  # from the dataset description, not tuned
assignment = MiniBatchKMeans(n_clusters=PARENTS, random_state=SEED, n_init=10,
                             batch_size=2048).fit_predict(features)

clusters = {}
for group, path, label in zip(assignment, paths, labels):
    clusters.setdefault(int(group), []).append((path, label))

sizes = sorted((len(v) for v in clusters.values()), reverse=True)
print(f"{len(clusters)} clusters | largest {sizes[:5]} | median {sizes[len(sizes)//2]} "
      f"| smallest {sizes[-5:]}")
print(f"expected ~{len(paths)//PARENTS} patches per parent photograph")
assert len(clusters) > PARENTS * 0.8, "clustering collapsed; the split would not separate parents"
"""
    ),
    code(
        """
keys_sorted = sorted(clusters)
rng = random.Random(SEED)
rng.shuffle(keys_sorted)

n = len(keys_sorted)
n_test, n_val = int(n*0.20), int(n*0.10)
split_keys = {
    "test":  keys_sorted[:n_test],
    "val":   keys_sorted[n_test:n_test+n_val],
    "train": keys_sorted[n_test+n_val:],
}
splits = {name: [item for k in ks for item in clusters[k]] for name, ks in split_keys.items()}

overlap = set(split_keys["train"]) & set(split_keys["test"])
assert not overlap, f"{len(overlap)} clusters in both train and test"

print(f"{'split':<7}{'clusters':>10}{'patches':>10}{'cracked':>10}")
for name in ("train", "val", "test"):
    items = splits[name]
    print(f"{name:<7}{len(split_keys[name]):>10}{len(items):>10}"
          f"{sum(l for _, l in items)/len(items):>9.1%}")

FINGERPRINT = hashlib.sha256(
    json.dumps({k: sorted(str(p) for p, _ in v) for k, v in splits.items()},
               sort_keys=True).encode()
).hexdigest()[:16]
print("\\nsplit fingerprint", FINGERPRINT, "- record this next to any number from this run")
"""
    ),
    md(
        """
## 4. The model

`mobilenetv3_small_100`: **2.5M parameters**, chosen for what it costs on the
production CPU rather than for what it scores here. This layer would run once per
tile, and the tiling measurement used 17 tiles per photograph — so a model that
is merely "fast" is still 17× too slow. The last cell measures single-patch CPU
latency at the production thread count and states the per-photograph cost
plainly, including when that cost is unaffordable.
"""
    ),
    code(
        """
MODEL_NAME, IMGSZ, EPOCHS, BATCH, LR = "mobilenetv3_small_100", 224, 12, 128, 3e-4

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

class Patches(Dataset):
    def __init__(self, items, train):
        self.items, self.train = items, train
    def __len__(self):
        return len(self.items)
    def __getitem__(self, i):
        path, label = self.items[i]
        im = Image.open(path).convert("RGB").resize((IMGSZ, IMGSZ), Image.BILINEAR)
        if self.train:
            # Flips only. A crack has no canonical orientation, so flips are
            # honest; colour jitter would teach invariance to the illumination
            # that the cluster split depends on being informative.
            if random.random() < 0.5: im = im.transpose(Image.FLIP_LEFT_RIGHT)
            if random.random() < 0.5: im = im.transpose(Image.FLIP_TOP_BOTTOM)
        a = (np.asarray(im, dtype=np.float32)/255.0 - MEAN) / STD
        return torch.from_numpy(a.transpose(2, 0, 1)), torch.tensor(label, dtype=torch.float32)

loaders = {
    name: DataLoader(Patches(splits[name], name == "train"), batch_size=BATCH,
                     shuffle=(name == "train"), num_workers=2, pin_memory=True)
    for name in ("train", "val", "test")
}
model = timm.create_model(MODEL_NAME, pretrained=True, num_classes=1).to(DEVICE)
print(MODEL_NAME, f"{sum(p.numel() for p in model.parameters())/1e6:.1f}M parameters")
"""
    ),
    code(
        """
optimiser = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
schedule = torch.optim.lr_scheduler.CosineAnnealingLR(optimiser, T_max=EPOCHS)
loss_fn = nn.BCEWithLogitsLoss()

def evaluate(loader):
    model.eval(); correct = total = 0
    with torch.no_grad():
        for x, y in loader:
            p = (torch.sigmoid(model(x.to(DEVICE)).squeeze(1)) > 0.5).float().cpu()
            correct += (p == y).sum().item(); total += len(y)
    return correct/total

best, best_state = 0.0, None
for epoch in range(1, EPOCHS+1):
    model.train(); t0 = time.time(); running = 0.0
    for x, y in loaders["train"]:
        optimiser.zero_grad()
        loss = loss_fn(model(x.to(DEVICE)).squeeze(1), y.to(DEVICE))
        loss.backward(); optimiser.step(); running += loss.item()
    schedule.step()
    accuracy = evaluate(loaders["val"])
    if accuracy > best:
        best, best_state = accuracy, {k: v.cpu().clone() for k, v in model.state_dict().items()}
    print(f"epoch {epoch:>2}  loss {running/len(loaders['train']):.4f}  "
          f"val {accuracy:.4f}  {time.time()-t0:.0f}s")

model.load_state_dict(best_state)
print(f"\\nbest validation {best:.4f}")
"""
    ),
    md(
        """
## 5. The number, and what it is a number about

Two evaluations, and the gap between them is the point.
"""
    ),
    code(
        """
model.eval()
tp = fp = tn = fn = 0
with torch.no_grad():
    for x, y in loaders["test"]:
        p = (torch.sigmoid(model(x.to(DEVICE)).squeeze(1)) > 0.5).float().cpu()
        tp += ((p==1)&(y==1)).sum().item(); fp += ((p==1)&(y==0)).sum().item()
        tn += ((p==0)&(y==0)).sum().item(); fn += ((p==0)&(y==1)).sum().item()

accuracy = (tp+tn)/(tp+fp+tn+fn)
precision = tp/(tp+fp) if tp+fp else 0.0
recall = tp/(tp+fn) if tp+fn else 0.0
print(f"HELD-OUT CLUSTERS ({tp+fp+tn+fn} patches from clusters never trained on)")
print(f"  accuracy {accuracy:.4f}   precision {precision:.4f}   recall {recall:.4f}")
print(f"  TP {tp}  FP {fp}  TN {tn}  FN {fn}")
print(f"  split fingerprint {FINGERPRINT}  seed {SEED}")
print(
    "\\nThis says how well the model learned METU's 458 Ankara facades.\\n"
    "It is NOT a claim about a Turkish home, because no Turkish residential\\n"
    "evaluation set exists to make one against. Quote it with this sentence."
)
"""
    ),
    code(
        """
# What the cluster split was worth. The same trained model, evaluated on patches
# drawn at random from the clusters it TRAINED on -- which is what a patch-level
# split reports, because there the test patches share parents with train.
#
# The gap between this and the number above is this dataset's leakage. It is the
# figure the published 97-99% results for METU do not separate out, and the
# reason they should not be compared with the number above.
trained_items = splits["train"]
leaky = random.Random(SEED).sample(trained_items, min(4000, len(trained_items)))
leaky_loader = DataLoader(Patches(leaky, train=False), batch_size=BATCH, num_workers=2)
leaky_accuracy = evaluate(leaky_loader)

print(f"held-out CLUSTERS (parents never seen)   {accuracy:.4f}")
print(f"patches from clusters ALREADY trained on {leaky_accuracy:.4f}")
gap = leaky_accuracy - accuracy
print(f"gap {gap:+.4f}")
print(
    "\\nA large positive gap means most of a patch-split score is memorisation "
    "of 458 Ankara facades.\\nQuote the first number; the second exists only so "
    "the first can be compared with what others publish."
)
"""
    ),
    code(
        """
# The out-of-distribution probe: 15 intact residential interiors, reviewed one by
# one and recorded in konut_eval/verdicts.csv. Different source, different
# cameras, different subject. It cannot measure recall -- nothing here is
# cracked. It measures the failure that actually ships.
INTACT = next((p for p in [Path("/kaggle/input/konut-eval/none"),
                           Path.cwd().parents[1]/"data"/"konut_eval"/"none"] if p.is_dir()), None)
if INTACT is None:
    print("intact interiors not mounted; skipping the only out-of-distribution check")
else:
    photos = sorted(q for q in INTACT.iterdir() if q.suffix.lower() in {".jpg",".jpeg",".png"})
    fired = 0
    for q in photos:
        im = Image.open(q).convert("RGB")
        W, H = im.size; g = 4
        tiles = [im.crop((int(c*W/g), int(r*H/g), int((c+1)*W/g), int((r+1)*H/g)))
                 for r in range(g) for c in range(g)]
        batch = torch.stack([
            torch.from_numpy(((np.asarray(t.resize((IMGSZ,IMGSZ), Image.BILINEAR),
                dtype=np.float32)/255.0 - MEAN)/STD).transpose(2,0,1)) for t in tiles])
        with torch.no_grad():
            if (torch.sigmoid(model(batch.to(DEVICE)).squeeze(1)) > 0.5).any():
                fired += 1
    share = fired / len(photos)
    print(f"OUT OF DISTRIBUTION: {fired}/{len(photos)} intact rooms = {share:.0%}")
    print(
        "\\nFor comparison, measured the same way: the one public crack checkpoint\\n"
        "(OpenSistemas/YOLOv8-crack-seg) fired on 64% of intact rooms at its default.\\n"
        "A number far above the held-out accuracy above is the honest headline,\\n"
        "because it is the one a claimant would meet."
    )
"""
    ),
    code(
        """
# CPU latency at the production thread count. Decides whether this ships at all:
# the layer runs once per tile, and the tiling work used 17 tiles per photograph.
cpu_model = timm.create_model(MODEL_NAME, pretrained=False, num_classes=1).eval()
cpu_model.load_state_dict({k: v.cpu() for k, v in model.state_dict().items()})
torch.set_num_threads(4)
x = torch.randn(1, 3, IMGSZ, IMGSZ)
with torch.no_grad():
    for _ in range(5): cpu_model(x)
    times = []
    for _ in range(30):
        t0 = time.perf_counter(); cpu_model(x); times.append((time.perf_counter()-t0)*1000)
per_patch = float(np.median(times))
print(f"{per_patch:.1f} ms per patch, 4 threads")
print(f"17 tiles -> {per_patch*17:.0f} ms per photograph, against a 150-250 ms budget")
if per_patch*17 > 250:
    print("OVER BUDGET. Batch the tiles, cut the grid, or do not ship this layer.")

torch.save({"state_dict": {k: v.cpu() for k, v in model.state_dict().items()},
            "model_name": MODEL_NAME, "imgsz": IMGSZ, "seed": SEED,
            "split_fingerprint": FINGERPRINT,
            "test_accuracy": accuracy, "test_precision": precision, "test_recall": recall,
            "dataset": "Ozgenel & Gonenc Sorguc 2018, Mendeley 5y9wdsg2zt, CC BY 4.0",
            "evaluation_caveat": ("held-out CLUSTERS of the same 458 METU facades; "
                                  "no independent Turkish residential set exists")},
           WORK / "metu_crack_patch.pt")
print("\\nsaved", WORK / "metu_crack_patch.pt")
"""
    ),
    md(
        """
## 6. Before any of this reaches the product

1. Record the **split fingerprint** beside every number. A different fingerprint
   means the numbers are not comparable to the published ones.
2. Publish the out-of-distribution false-alarm rate **first**, and the held-out
   accuracy second with its caveat attached. The order is the honesty.
3. Carry the **CC BY 4.0 attribution** — Özgenel & Gönenç Sorguç, ISARC 2018 —
   into the README and the model card. Attribution is a licence condition.
4. If the false-alarm rate on intact rooms is high, **it does not ship**, whatever
   the held-out accuracy says. That is the rule the vehicle specialist was
   corrected by (README 7.10) and the rule the public crack checkpoint failed
   (7.11).
5. `calibrated` stays **false**. A trained binary classifier is not a calibrated
   probability, and cracks are still the least useful konut sub-problem: they map
   to earthquake damage, which DASK already sends a licensed eksper to assess and
   settles on rebuild cost rather than by grade.
"""
    ),
]


def check(cells: list[dict[str, object]]) -> None:
    """Every code cell must parse before the notebook is written.

    Cell text lives inside triple-quoted strings here, so a backslash escape is
    processed once by this file and once more by the notebook. Getting that
    wrong produced an unterminated string literal three times, and each one was
    only visible after generating and re-parsing. So the generator checks itself:
    a notebook that cannot parse is never written, and the escape bug cannot
    reach Kaggle again.
    """
    for index, cell in enumerate(cells):
        if cell["cell_type"] != "code":
            continue
        newline = chr(10)
        lines = "".join(cell["source"]).split(newline)  # type: ignore[arg-type]
        # `!pip ...` is IPython, not Python. Neutralise it for the parse only.
        parseable = newline.join(
            f"pass  # {line}" if line.strip().startswith("!") else line for line in lines
        )
        try:
            ast.parse(parseable)
        except SyntaxError as error:
            offending = lines[(error.lineno or 1) - 1] if lines else ""
            raise SystemExit(
                f"cell {index} does not parse: {error}"
                f"{newline}  line {error.lineno}: {offending!r}"
                f"{newline}  a backslash escape in the generator is the usual cause"
                " -- it needs doubling, or removing."
            ) from error


def main() -> int:
    check(CELLS)
    NOTEBOOK.parent.mkdir(parents=True, exist_ok=True)
    NOTEBOOK.write_text(
        json.dumps(
            {
                "cells": CELLS,
                "metadata": {
                    "kernelspec": {
                        "display_name": "Python 3",
                        "language": "python",
                        "name": "python3",
                    },
                    "language_info": {"name": "python", "version": "3.11"},
                },
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {NOTEBOOK} ({len(CELLS)} cells, every code cell parses)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
