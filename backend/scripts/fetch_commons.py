"""Fetch evaluation images from Wikimedia Commons, one licence at a time.

    uv run python -m scripts.fetch_commons --category "Category:Broken telephone screens" \
        --into ../data/_sources/phone_screen --limit 60

Commons is the only source that covers every category this project still needs
-- cracked walls, shattered phone screens, broken household objects, and the
ordinary photographs the gate has to reject -- without an API key, a sign-up
form, or a licence that has to be taken on trust.

**Licence is read per file, and a file whose licence cannot be read is skipped.**
Commons is a collection, not a corpus: two photographs in the same category can
carry different terms, and some carry terms that permit nothing. The API returns
the licence per file, so this script asks for every one, records it in the
sidecar, and drops anything it cannot resolve or that is not in the accepted set.
An unrecorded licence is not a small gap in a manifest -- it is a claim nobody
can check, which is the specific thing this project exists to avoid.

Attribution travels with the image. CC BY and CC BY-SA require credit, so the
author and the Commons page URL are carried into the sidecar and from there into
the evaluation manifest, where they stay next to the file they belong to.

**Rate limits are respected rather than worked around.** Commons throttles, and
the polite answer is to slow down and identify yourself, not to retry harder.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API = "https://commons.wikimedia.org/w/api.php"

#: Commons asks that automated clients identify themselves and link somewhere a
#: maintainer can complain to. https://meta.wikimedia.org/wiki/User-Agent_policy
USER_AGENT = "BioVision-eval/1.0 (research dataset; https://github.com/bilalgurkansanli/BioVision)"

#: One request a second, and back off further when told to. The first version of
#: this script asked as fast as it could and was answered with HTTP 429.
REQUEST_INTERVAL = 1.0

#: Licences this project will redistribute the *reference* to. Everything else --
#: fair use, non-commercial-only, "permission granted", or an empty field -- is
#: skipped rather than guessed at.
ACCEPTED = re.compile(
    r"^(cc0|cc[ -]by([ -]sa)?[ -]\d|public domain|pd[ -]|gfdl)",
    re.IGNORECASE,
)

MIN_EDGE_PX = 400
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}

SIDECAR_FIELDS = ["filename", "source_url", "license", "author", "commons_title"]

_last_request = 0.0


def call(**params: str | int) -> dict[str, Any]:
    """One API call, throttled, with a bounded retry on 429 and maxlag."""
    global _last_request

    params.update(format="json", formatversion=2, maxlag=5)
    url = API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(5):
        wait = REQUEST_INTERVAL - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload: dict[str, Any] = json.load(response)
        except urllib.error.HTTPError as error:
            if error.code not in (429, 503):
                raise
            time.sleep(2**attempt)
            continue

        if "error" in payload and payload["error"].get("code") == "maxlag":
            time.sleep(2**attempt)
            continue
        return payload

    raise RuntimeError("Commons kept refusing after five attempts; try again later")


def strip_html(value: str) -> str:
    """Commons returns author and licence fields as small HTML fragments."""
    text = re.sub(r"<[^>]+>", " ", value)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def members(category: str, depth: int, seen: set[str]) -> list[str]:
    """File titles in a category, optionally descending into subcategories."""
    files: list[str] = []
    continuation: dict[str, str] = {}

    while True:
        payload = call(
            action="query",
            list="categorymembers",
            cmtitle=category,
            cmtype="file|subcat",
            cmlimit=500,
            **continuation,
        )
        for member in payload.get("query", {}).get("categorymembers", []):
            title = member["title"]
            if title.startswith("Category:"):
                if depth > 0 and title not in seen:
                    seen.add(title)
                    files.extend(members(title, depth - 1, seen))
            else:
                files.append(title)

        if "continue" not in payload:
            return files
        continuation = {"cmcontinue": payload["continue"]["cmcontinue"]}


def described(titles: list[str]) -> list[dict[str, str]]:
    """Resolve URL, licence and author for each file, 50 at a time."""
    resolved: list[dict[str, str]] = []

    for start in range(0, len(titles), 50):
        batch = titles[start : start + 50]
        payload = call(
            action="query",
            titles="|".join(batch),
            prop="imageinfo",
            iiprop="url|extmetadata|size|mime",
        )
        for page in payload.get("query", {}).get("pages", []):
            info = (page.get("imageinfo") or [{}])[0]
            if not info:
                continue
            metadata = info.get("extmetadata", {})
            licence = strip_html(metadata.get("LicenseShortName", {}).get("value", ""))
            resolved.append(
                {
                    "title": page["title"],
                    "url": info.get("url", ""),
                    "descriptionurl": info.get("descriptionurl", ""),
                    "license": licence,
                    "author": strip_html(metadata.get("Artist", {}).get("value", "")),
                    "mime": info.get("mime", ""),
                    "width": str(info.get("width", 0)),
                    "height": str(info.get("height", 0)),
                }
            )

    return resolved


def usable(entry: dict[str, str]) -> str:
    """Return the reason this file is unusable, or an empty string if it is."""
    if entry["mime"] not in ALLOWED_MIME:
        return "mime"
    if not entry["license"]:
        return "licence_missing"
    if not ACCEPTED.match(entry["license"]):
        return "licence_not_accepted"
    if min(int(entry["width"] or 0), int(entry["height"] or 0)) < MIN_EDGE_PX:
        return "too_small"
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--category", action="append", required=True, help="repeatable")
    parser.add_argument("--into", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--depth", type=int, default=0, help="subcategory recursion")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="skip files whose title matches this substring, case-insensitive",
    )
    arguments = parser.parse_args()

    titles: list[str] = []
    seen: set[str] = set()
    for category in arguments.category:
        found = members(category, arguments.depth, seen)
        print(f"{category}: {len(found)} files")
        titles.extend(found)

    # Sorted then deduplicated, so the same arguments always select the same
    # files -- the categories themselves grow over time.
    titles = sorted(dict.fromkeys(titles))

    excluded_by_title = 0
    if arguments.exclude:
        patterns = [text.lower() for text in arguments.exclude]
        kept = [t for t in titles if not any(p in t.lower() for p in patterns)]
        excluded_by_title = len(titles) - len(kept)
        titles = kept

    print(f"{len(titles)} unique files, resolving licences")
    entries = described(titles)

    rejected: dict[str, int] = {}
    accepted: list[dict[str, str]] = []
    for entry in entries:
        reason = usable(entry)
        if reason:
            rejected[reason] = rejected.get(reason, 0) + 1
        else:
            accepted.append(entry)

    print(f"usable: {len(accepted)}")
    if excluded_by_title:
        print(f"  excluded {excluded_by_title:>5,}  title matched --exclude")
    for reason, count in sorted(rejected.items()):
        print(f"  excluded {count:>5,}  {reason}")

    if len(accepted) < arguments.limit:
        print(f"\nwanted {arguments.limit}, only {len(accepted)} usable -- taking all of them")

    arguments.into.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []

    for entry in accepted[: arguments.limit]:
        # Commons file URLs sometimes carry a tracking query string, and Commons
        # titles run long -- both of which produced unopenable paths on Windows
        # the first time this ran. Take the path component, then bound the stem.
        path = urllib.parse.urlparse(entry["url"]).path
        name = urllib.parse.unquote(path.rsplit("/", 1)[-1])
        name = re.sub(r"[^A-Za-z0-9._-]", "_", name)

        stem, _, suffix = name.rpartition(".")
        if len(stem) > 72:
            # Keep the head readable and disambiguate with a digest of the whole
            # title, so two long names that share a prefix cannot collide.
            digest = hashlib.sha256(entry["title"].encode()).hexdigest()[:8]
            name = f"{stem[:72]}_{digest}.{suffix}"

        target = arguments.into / name

        if not target.exists():
            request = urllib.request.Request(entry["url"], headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    target.write_bytes(response.read())
            except Exception as error:
                print(f"  skipped {name}: {error}")
                continue
            time.sleep(REQUEST_INTERVAL)

        rows.append(
            {
                "filename": name,
                "source_url": entry["descriptionurl"],
                "license": entry["license"],
                "author": entry["author"][:120],
                "commons_title": entry["title"],
            }
        )

    sidecar = arguments.into / "attribution.csv"
    with sidecar.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SIDECAR_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    licences: dict[str, int] = {}
    for row in rows:
        licences[row["license"]] = licences.get(row["license"], 0) + 1

    print(f"\n{len(rows)} images -> {arguments.into}")
    for licence, count in sorted(licences.items(), key=lambda pair: -pair[1]):
        print(f"  {count:>3}  {licence}")
    print(f"attribution -> {sidecar}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
