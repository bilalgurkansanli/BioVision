"""Evaluate the router: confusion matrix, per-domain accuracy, threshold sweep.

    uv run python -m scripts.eval_router

Writes `docs/assets/confusion_matrix_router.png` and prints the markdown tables the
README carries. Copy them verbatim -- including the rows that look bad. A per-domain
breakdown that hides its worst row is the single-number claim this project exists to
avoid, wearing a table for a disguise.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from biovision.config import BACKEND_ROOT, Settings
from biovision.domains.catalog import DomainCatalog
from biovision.domains.gate import GatePrompts
from biovision.models.clip import ClipEncoder
from biovision.models.clip_gate import ClipGate
from biovision.models.clip_router import ClipRouter
from scripts._evalset import EvalSetMissingError, LabelledImage, load_rgb, load_set, summarise

ASSETS = BACKEND_ROOT.parent / "docs" / "assets"


def predict(
    router: ClipRouter, entries: list[LabelledImage]
) -> tuple[list[str], np.ndarray]:
    """Return predicted domains and the full probability matrix."""
    predictions: list[str] = []
    probabilities = []

    for index, entry in enumerate(entries, start=1):
        decision = router.classify_pixels(load_rgb(entry.path))
        predictions.append(decision.domain)
        probabilities.append(
            np.array([decision.scores[key] for key in router.domain_keys], dtype=np.float32)
        )

        if index % 25 == 0:
            print(f"  {index}/{len(entries)}")

    return predictions, np.stack(probabilities)


def confusion(truth: list[str], predicted: list[str], keys: list[str]) -> np.ndarray:
    index = {key: position for position, key in enumerate(keys)}
    matrix = np.zeros((len(keys), len(keys)), dtype=int)
    for actual, guess in zip(truth, predicted, strict=True):
        if actual in index and guess in index:
            matrix[index[actual], index[guess]] += 1
    return matrix


def markdown_matrix(matrix: np.ndarray, keys: list[str]) -> str:
    header = "| true \\ predicted | " + " | ".join(keys) + " | recall |"
    divider = "|" + "---|" * (len(keys) + 2)
    rows = [header, divider]

    for position, key in enumerate(keys):
        total = int(matrix[position].sum())
        hits = int(matrix[position, position])
        recall = f"{hits / total:.0%}" if total else "n/a"
        cells = " | ".join(str(int(value)) for value in matrix[position])
        rows.append(f"| **{key}** | {cells} | {recall} |")

    return "\n".join(rows)


def threshold_sweep(
    confidences: np.ndarray, correct: np.ndarray, thresholds: list[float]
) -> str:
    """Accuracy and coverage as the abstain threshold moves.

    This is the table that sets `router_min_confidence`. Below the threshold the
    router returns `unknown` rather than guessing, so the trade is coverage against
    the accuracy of what it does answer -- and refusing to answer is a legitimate
    outcome here, not a loss.
    """
    rows = ["| threshold | coverage | accuracy on answered |", "|---|---|---|"]
    for threshold in thresholds:
        answered = confidences >= threshold
        coverage = float(answered.mean())
        accuracy = float(correct[answered].mean()) if answered.any() else float("nan")
        rows.append(f"| {threshold:.2f} | {coverage:.0%} | {accuracy:.1%} |")
    return "\n".join(rows)


def plot_confusion(matrix: np.ndarray, keys: list[str], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    normalised = matrix / np.maximum(matrix.sum(axis=1, keepdims=True), 1)

    figure, axes = plt.subplots(figsize=(1.6 * len(keys) + 2, 1.4 * len(keys) + 2))
    axes.imshow(normalised, cmap="Blues", vmin=0, vmax=1)

    axes.set_xticks(range(len(keys)), keys, rotation=45, ha="right")
    axes.set_yticks(range(len(keys)), keys)
    axes.set_xlabel("predicted")
    axes.set_ylabel("true")
    axes.set_title("Router confusion matrix (row-normalised)")

    for row in range(len(keys)):
        for column in range(len(keys)):
            axes.text(
                column,
                row,
                f"{int(matrix[row, column])}",
                ha="center",
                va="center",
                color="white" if normalised[row, column] > 0.5 else "black",
            )

    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=150)
    plt.close(figure)


def main() -> int:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    try:
        entries = load_set("router_eval")
    except EvalSetMissingError as exc:
        print(exc)
        return 1

    print(f"evaluation set: {len(entries)} images, {summarise(entries)}")

    catalog = DomainCatalog.load(settings.domains_path)
    encoder = ClipEncoder(
        settings.clip_model, settings.clip_pretrained, settings.weights_path,
        settings.torch_num_threads,
    )
    router = ClipRouter(encoder, catalog)

    predicted, probabilities = predict(router, entries)
    truth = [entry.domain for entry in entries]

    keys = catalog.keys
    matrix = confusion(truth, predicted, keys)
    correct = np.array(
        [actual == guess for actual, guess in zip(truth, predicted, strict=True)]
    )
    confidences = probabilities.max(axis=1)

    print("\n### Router confusion matrix\n")
    print(markdown_matrix(matrix, keys))
    print(f"\nOverall top-1 accuracy: **{correct.mean():.1%}** over {len(entries)} images.\n")

    print("### Threshold sweep\n")
    print(threshold_sweep(confidences, correct, [0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]))

    # The gate is evaluated on this set too: every image here is in-distribution by
    # construction, so anything it rejects is a false reject -- the error that costs
    # a user their analysis.
    gate = ClipGate(encoder, GatePrompts.load(settings.gate_prompts_path), settings.gate_threshold)

    # Broken out by domain, because a rejection rate averaged over four domains
    # hides which kind of damage the gate cannot see -- and that is the part
    # worth knowing.
    rejects: dict[str, list[int]] = {}
    for entry in entries:
        passed = gate.check_pixels(load_rgb(entry.path)).passed
        tally = rejects.setdefault(entry.domain, [0, 0])
        tally[0] += int(not passed)
        tally[1] += 1

    rejected = sum(misses for misses, _ in rejects.values())
    print(
        f"\n### Gate\n\nFalse rejects on in-distribution images: "
        f"**{rejected}/{len(entries)}** ({rejected / len(entries):.1%}) "
        f"at threshold {settings.gate_threshold}.\n"
    )
    print("| domain | images | wrongly rejected |")
    print("|---|---|---|")
    for domain, (misses, total) in sorted(rejects.items()):
        print(f"| {domain} | {total} | {misses} ({misses / total:.0%}) |")

    # The other error, which the set above cannot see. A gate measured only on
    # damage photographs can look perfect by accepting everything; these are the
    # uploads it is supposed to turn away.
    try:
        negatives = load_set("gate_eval")
    except EvalSetMissingError as exc:
        print(f"\nFalse accepts: not measured -- {exc}")
    else:
        accepted: dict[str, list[int]] = {}
        for entry in negatives:
            passed = gate.check_pixels(load_rgb(entry.path)).passed
            tally = accepted.setdefault(entry.domain, [0, 0])
            tally[0] += int(passed)
            tally[1] += 1

        total_accepted = sum(hits for hits, _ in accepted.values())
        print(
            f"\nFalse accepts on out-of-scope images: "
            f"**{total_accepted}/{len(negatives)}** "
            f"({total_accepted / len(negatives):.1%}).\n"
        )
        print("| out-of-scope category | images | wrongly accepted |")
        print("|---|---|---|")
        for category, (hits, total) in sorted(accepted.items()):
            print(f"| {category} | {total} | {hits} ({hits / total:.0%}) |")

    output = ASSETS / "confusion_matrix_router.png"
    plot_confusion(matrix, keys, output)
    print(f"\nwritten: {output}")
    print("\nPaste these tables into README section 7, verbatim, including the bad rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
