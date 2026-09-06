"""What the whole pipeline does to a clean room, not what the model does.

    uv run python -m scripts.eval_building_endtoend

`eval_metu_crack.py` fed fifteen intact residential interiors straight to the
crack classifier and got **15/15 false alarms**. That number is true and it is
about the model. It is not about the product, because it skipped the two layers
that stand in front of the specialist:

* **the gate**, which rejects photographs that are not of damage at all;
* **the router**, which sends a photograph to `building` only if it looks like a
  building damage photograph -- an ordinary living room usually looks like
  `other`.

A number measured with those bypassed answers "how good is this checkpoint".
A claimant asks "what will this website tell me", and only the live pipeline can
answer that. So this posts the same fifteen photographs to the running API and
counts what comes back, which is the number that belongs next to a product
claim.

Both numbers are kept. Reporting only the friendlier one would be choosing the
measurement that flatters the decision, which is the move this project refuses
everywhere else.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

from scripts._paths import DATA, SOURCES

ROOMS = DATA / "konut_eval/none"
CRACKS = SOURCES / "building"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def post(url: str, path: Path) -> dict[str, object]:
    """Multipart by hand, so this script needs nothing the backend does not have."""
    boundary = "----biovision-eval-boundary"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="image"; filename="{path.name}"\r\n'.encode(),
            b"Content-Type: application/octet-stream\r\n\r\n",
            path.read_bytes(),
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return dict(json.load(response))
    except urllib.error.HTTPError as error:
        return dict(json.load(error))


def images_in(folder: Path, limit: int) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES)[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000/v1/analyze")
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--verbose", action="store_true")
    arguments = parser.parse_args()

    for folder, label, damaged in ((ROOMS, "INTACT ROOMS", False), (CRACKS, "CRACKED WALLS", True)):
        paths = images_in(folder, arguments.limit)
        if not paths:
            print(f"{label}: nothing at {folder}")
            continue

        gated = 0
        refused: dict[str, int] = {}
        elsewhere: dict[str, int] = {}
        reached = 0
        flagged = 0

        for path in paths:
            body = post(arguments.url, path)
            error = body.get("error")
            if isinstance(error, dict):
                # Distinguish "the gate said this is not damage" from "the API
                # said no for an unrelated reason". Counting a 429 as a gate
                # rejection would have reported 60 of 60 cracked walls filtered
                # out, which is a rate limit wearing a measurement's clothes.
                code = str(error.get("code"))
                if code == "out_of_distribution":
                    gated += 1
                    if arguments.verbose:
                        print(f"    gate rejected   {path.name[:44]}")
                else:
                    refused[code] = refused.get(code, 0) + 1
                continue
            domain = str(body.get("domain"))
            raw = body.get("findings")
            findings = raw if isinstance(raw, list) else []
            if domain != "building":
                elsewhere[domain] = elsewhere.get(domain, 0) + 1
                if arguments.verbose:
                    print(f"    routed {domain:<8} {path.name[:44]}")
                continue
            reached += 1
            if findings:
                flagged += 1
            if arguments.verbose:
                print(f"    building  {len(findings):>2} findings  {path.name[:44]}")

        total = len(paths)
        judged = total - sum(refused.values())
        print(f"\n{label} ({total} photographs)")
        for code, count in sorted(refused.items()):
            print(f"  !! refused as `{code}`: {count} -- NOT a measurement")
        if judged != total:
            print(f"  {judged} photographs actually reached the pipeline")
        print(f"  rejected by the gate            {gated}")
        for domain, count in sorted(elsewhere.items()):
            print(f"  routed to `{domain}` instead      {count}")
        print(f"  reached the building specialist {reached}")
        verdict = "correctly flagged" if damaged else "FALSE ALARM"
        print(f"  {verdict:<31} {flagged}/{judged}")

    print(
        "\nCompare with scripts/eval_metu_crack.py, which posts the same rooms\n"
        "straight to the checkpoint and gets 15/15. That number is about the\n"
        "model; this one is about the product. Both are true, they answer\n"
        "different questions, and neither replaces the other."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
