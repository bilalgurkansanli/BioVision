"""Fit the router's temperature and produce the reliability diagram.

    uv run python -m scripts.calibrate_router

Writes `backend/weights/router_calibration.json` and
`docs/assets/reliability_router.png`, and prints the before/after ECE for the README.

Temperature scaling divides the logits by a single scalar fitted to minimise negative
log-likelihood on a **held-out** split. One parameter is the whole point: it cannot
reorder the classes, so accuracy is provably unchanged and only the claimed
confidence moves. That is what makes it an honest correction rather than a second
model quietly making decisions.

The fit uses the calibration split; the ECE reported to users is measured on the
evaluation split, which the fit never sees. Doing both on the same images would
produce an excellent number that describes nothing, so the two sets are asserted
disjoint before anything runs.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import torch

from biovision.config import BACKEND_ROOT, Settings
from biovision.domains.catalog import DomainCatalog
from biovision.models.calibration import (
    CALIBRATION_FILENAME,
    MIN_CALIBRATION_SAMPLES,
    Calibration,
    expected_calibration_error,
)
from biovision.models.clip import ClipEncoder
from biovision.models.clip_router import ClipRouter
from biovision.models.scoring import softmax
from scripts._evalset import (
    EvalSetMissingError,
    LabelledImage,
    assert_disjoint,
    load_rgb,
    load_set,
    summarise,
)

ASSETS = BACKEND_ROOT.parent / "docs" / "assets"
N_BINS = 15


def collect_logits(
    router: ClipRouter, entries: list[LabelledImage]
) -> tuple[np.ndarray, np.ndarray]:
    """Uncalibrated logits and integer labels for a split."""
    index = {key: position for position, key in enumerate(router.domain_keys)}
    logits = []
    labels = []

    for position, entry in enumerate(entries, start=1):
        if entry.domain not in index:
            print(f"  skipping {entry.filename}: unknown domain {entry.domain!r}")
            continue
        logits.append(router.logits_for(load_rgb(entry.path)))
        labels.append(index[entry.domain])
        if position % 25 == 0:
            print(f"  {position}/{len(entries)}")

    return np.stack(logits), np.array(labels, dtype=np.int64)


def fit_temperature(logits: np.ndarray, labels: np.ndarray) -> float:
    """Minimise NLL over a single scalar, with L-BFGS.

    Optimising log(T) rather than T keeps the parameter positive without a
    constraint: a negative or zero temperature would invert or explode the logits.
    """
    tensor_logits = torch.from_numpy(logits)
    tensor_labels = torch.from_numpy(labels)

    log_temperature = torch.zeros(1, requires_grad=True)  # log(1.0) == 0
    optimiser = torch.optim.LBFGS([log_temperature], lr=0.1, max_iter=100)
    loss_function = torch.nn.CrossEntropyLoss()

    def closure() -> torch.Tensor:
        optimiser.zero_grad()
        loss: torch.Tensor = loss_function(
            tensor_logits / log_temperature.exp(), tensor_labels
        )
        # torch's own annotations are incomplete here; both calls are correct.
        loss.backward()  # type: ignore[no-untyped-call]
        return loss

    optimiser.step(closure)  # type: ignore[no-untyped-call]
    return float(log_temperature.exp().item())


def metrics(logits: np.ndarray, labels: np.ndarray, temperature: float) -> tuple[float, float]:
    """(ECE, accuracy) for a split at a given temperature."""
    probabilities = np.stack([softmax(row / temperature) for row in logits])
    predicted = probabilities.argmax(axis=1)
    confidences = probabilities.max(axis=1)
    correct = (predicted == labels).astype(np.float32)
    return expected_calibration_error(confidences, correct, N_BINS), float(correct.mean())


def plot_reliability(
    logits: np.ndarray, labels: np.ndarray, temperature: float, path: Path
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 2, figsize=(11, 5), sharey=True)

    for panel, (scale, title) in enumerate(
        [(1.0, "Before calibration"), (temperature, f"After (T = {temperature:.3f})")]
    ):
        probabilities = np.stack([softmax(row / scale) for row in logits])
        confidences = probabilities.max(axis=1)
        correct = (probabilities.argmax(axis=1) == labels).astype(np.float32)

        centres, accuracies = [], []
        for lower, upper in itertools.pairwise(np.linspace(0.0, 1.0, N_BINS + 1)):
            in_bin = (confidences > lower) & (confidences <= upper)
            if not in_bin.any():
                continue
            centres.append((lower + upper) / 2)
            accuracies.append(float(correct[in_bin].mean()))

        ece = expected_calibration_error(confidences, correct, N_BINS)

        axis = axes[panel]
        axis.plot([0, 1], [0, 1], "k--", linewidth=1, label="perfect calibration")
        axis.bar(centres, accuracies, width=1 / N_BINS * 0.9, alpha=0.75, label="accuracy")
        axis.set_xlim(0, 1)
        axis.set_ylim(0, 1)
        axis.set_xlabel("confidence")
        axis.set_title(f"{title}\nECE = {ece:.4f}")
        if panel == 0:
            axis.set_ylabel("observed accuracy")
        axis.legend(loc="upper left", fontsize=8)

    figure.suptitle("Router reliability -- evaluation split (never seen by the fit)")
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=150)
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="write the temperature even when it makes ECE worse on the held-out split",
    )
    arguments = parser.parse_args()

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    try:
        calibration_split = load_set("router_calib")
        evaluation_split = load_set("router_eval")
        assert_disjoint(calibration_split, evaluation_split)
    except EvalSetMissingError as exc:
        print(exc)
        return 1

    print(f"calibration split: {len(calibration_split)} images, {summarise(calibration_split)}")
    print(f"evaluation split:  {len(evaluation_split)} images, {summarise(evaluation_split)}\n")

    catalog = DomainCatalog.load(settings.domains_path)
    encoder = ClipEncoder(
        settings.clip_model, settings.clip_pretrained, settings.weights_path,
        settings.torch_num_threads,
    )
    # Explicitly uncalibrated: fitting on already-scaled logits would compound two
    # temperatures.
    router = ClipRouter(encoder, catalog, calibration=None)

    print("encoding calibration split ...")
    calib_logits, calib_labels = collect_logits(router, calibration_split)
    print("encoding evaluation split ...")
    eval_logits, eval_labels = collect_logits(router, evaluation_split)

    temperature = fit_temperature(calib_logits, calib_labels)
    print(f"\nfitted temperature: {temperature:.4f}")
    if temperature > 1.0:
        print(
            "  (T > 1 lowers confidence: the fit judged the router overconfident on the\n"
            "   calibration split by negative log likelihood. Whether that also improves\n"
            "   ECE on the held-out split is a separate question, answered below.)"
        )

    ece_before, accuracy_before = metrics(eval_logits, eval_labels, 1.0)
    ece_after, accuracy_after = metrics(eval_logits, eval_labels, temperature)

    print("\n### Calibration (measured on the evaluation split)\n")
    print("| Metric | Before | After |")
    print("|---|---|---|")
    print(f"| ECE | {ece_before:.4f} | {ece_after:.4f} |")
    print(f"| Top-1 accuracy | {accuracy_before:.1%} | {accuracy_after:.1%} |")

    if abs(accuracy_before - accuracy_after) > 1e-9:
        # Temperature scaling is monotonic; it cannot change the argmax. A change
        # here means a bug, not a result.
        print("\n*** accuracy changed -- that is impossible for temperature scaling ***")
        return 2

    calibration = Calibration(
        temperature=temperature,
        ece_before=ece_before,
        ece_after=ece_after,
        accuracy=accuracy_after,
        n_samples=int(calib_labels.size),
        fitted_on="router_calib",
        model_id=encoder.name,
    )

    diagram = ASSETS / "reliability_router.png"
    plot_reliability(eval_logits, eval_labels, temperature, diagram)
    print(f"\nwritten: {diagram}")

    target = settings.weights_path / CALIBRATION_FILENAME

    if ece_after >= ece_before and not arguments.force:
        # The fit is not written. Loading it would make every response say
        # `domain_confidence_calibrated: true` while the confidence numbers are
        # measurably worse than the uncalibrated ones -- a claim of rigour that
        # the measurement contradicts, which is the exact failure this project
        # exists to avoid. Refusing is the result, not an error.
        print(
            f"\nNOT WRITTEN. Temperature scaling made ECE worse on the held-out split "
            f"({ece_before:.4f} -> {ece_after:.4f}), so there is nothing to claim.\n"
            "\nThe reliability diagram shows why: the bars sit ABOVE the diagonal, so the\n"
            "router is mildly UNDER-confident, and a temperature above 1 lowers confidence\n"
            "further -- the wrong direction. Temperature scaling minimises negative log\n"
            "likelihood, not ECE, and on a router this well separated the two disagree.\n"
            "\nResponses keep reporting domain_confidence_calibrated: false, correctly.\n"
            "Re-run with --force to write it anyway, having read the above."
        )
        return 0

    target.write_text(json.dumps(calibration.model_dump(), indent=2) + "\n", encoding="utf-8")
    print(f"written: {target}")

    if calibration.n_samples < MIN_CALIBRATION_SAMPLES:
        # The file is still written -- inspecting it is how you decide whether the
        # split is worth growing. It simply will not be loaded, and saying so here
        # is cheaper than wondering later why nothing changed.
        print(
            f"\nNOTE: fitted on {calibration.n_samples} samples, below the "
            f"{MIN_CALIBRATION_SAMPLES}-sample floor. The API will REFUSE this file and keep "
            "reporting domain_confidence_calibrated: false. ECE over this few samples is "
            "noise, and labelling noise 'calibrated' is the thing this project refuses to do."
        )
        return 0

    print("\nResponses will now report domain_confidence_calibrated: true.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
