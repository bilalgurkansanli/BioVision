"""No sentence in this system may sound like an offer to pay.

BioVision is not an insurer, an agent or a loss adjuster. It computes where a
regulatory line falls and cites the article. The moment a string says what an
insurer *will pay*, or asserts that a vehicle *will be* written off, the product
has crossed from arithmetic into a determination reserved by law to a
Levha-registered eksper (Genelge 2025/12 m.4/2, m.5/2) -- and into language a
claimant could later argue was a promise.

Prose in a review can drift. This test cannot, so the rule lives here:

    A sentence may take as its subject:  mevzuat, eşik, çizgi, tavan, oran,
    liste, basamak, kural.

    It may never take *sigortacı* as subject with *ödeyecek / ödenir /
    alırsınız* as verb, never attach a lira figure to *tazminat* as a
    prediction, and never assert *pert olacak*.

Scanned over the Turkish user-facing strings in the frontend rather than the
backend, because that is where the sentences a claimant actually reads live.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from biovision.config import BACKEND_ROOT

FRONTEND = BACKEND_ROOT.parent / "frontend"

#: Files a user's eyes reach. Tests, configs and type declarations are excluded:
#: a forbidden phrase inside a test asserting it is forbidden is not a defect.
SCANNED_SUFFIXES = {".tsx", ".ts"}
SKIP_PARTS = {"node_modules", ".next", "tests", "__tests__"}
SKIP_NAMES = {"types.ts", "contract.test-d.ts"}


#: Each pattern is a way of promising something this system cannot promise.
#: `\w*` endings catch Turkish suffixes -- "ödenecektir", "alırsınızdır".
FORBIDDEN: list[tuple[str, str]] = [
    (
        # `.` rather than `[^.]`: in Turkish the full stop is the thousands
        # separator, so "1.400.000" broke a cross-sentence guard that used it as
        # a boundary. The scan is line-by-line, which bounds the match anyway.
        r"sigortac[ıi]\w*.{0,60}?öde\w+",
        "states what the insurer will pay; the insurer decides that, not this system",
    ),
    (
        r"tazminat\w*\s*[:=]?\s*[\d.,]+\s*TL",
        "attaches a lira figure to tazminat as a prediction",
    ),
    (
        r"tahmini\s+tazminat",
        "'estimated compensation' is a payout prediction",
    ),
    (
        r"tahmini\s+onar[ıi]m\s+bedeli",
        "no photo-based repair-cost estimate has a published accuracy; "
        "a derived band is not a measured band",
    ),
    (
        r"pert\s+olacak|pert\s+olur\b",
        "asserts the write-off outcome; only a registered eksper determines it",
    ),
    (
        r"%\s*\d+\s*(?:ihtimal|olas[ıi]l[ıi]k)\w*\s+(?:ile\s+)?pert",
        "attaches a probability to a write-off",
    ),
    (
        r"priminiz\s+%\s*\d+\s+artacak",
        "states a future premium as fact; Ek-2 is a ceiling, not a price",
    ),
    (
        r"pert\s+s[ıi]n[ıi]r[ıi]\s*%\s*70|%\s*70'?[ıi]\s+a[şs]",
        "the 70% threshold has no basis in Turkish regulation; the figure is 60%",
    ),
    (
        r"kesinlikle\s+(?:pert|a[ğg][ıi]r\s+hasar)",
        "'definitely' about an outcome this system cannot determine",
    ),
]

COMPILED = [(re.compile(pattern, re.IGNORECASE), reason) for pattern, reason in FORBIDDEN]


def _scanned_files() -> list[Path]:
    if not FRONTEND.is_dir():
        return []
    return [
        path
        for path in FRONTEND.rglob("*")
        if path.suffix in SCANNED_SUFFIXES
        and path.name not in SKIP_NAMES
        and not SKIP_PARTS & set(path.parts)
    ]


def test_there_are_files_to_scan() -> None:
    """A silent pass because the glob broke would be worse than a failure."""
    files = _scanned_files()
    assert len(files) > 5, f"expected frontend sources under {FRONTEND}, found {len(files)}"


@pytest.mark.parametrize("pattern,reason", FORBIDDEN)
def test_the_pattern_matches_its_own_example(pattern: str, reason: str) -> None:
    """Each rule is exercised against a sentence it must catch.

    A regex that matches nothing passes every scan and protects nothing.
    """
    examples = {
        r"sigortac[ıi]\w*.{0,60}?öde\w+": "Sigortacı size 1.400.000 TL ödeyecek",
        r"tazminat\w*\s*[:=]?\s*[\d.,]+\s*TL": "Tahmini tazminat: 1.430.000 TL",
        r"tahmini\s+tazminat": "Tahmini tazminat tutarı",
        r"tahmini\s+onar[ıi]m\s+bedeli": "Tahmini onarım bedeli ~620.000 TL",
        r"pert\s+olacak|pert\s+olur\b": "Aracınız pert olacak",
        r"%\s*\d+\s*(?:ihtimal|olas[ıi]l[ıi]k)\w*\s+(?:ile\s+)?pert": "%82 ihtimalle pert",
        r"priminiz\s+%\s*\d+\s+artacak": "Priminiz %45 artacak",
        r"pert\s+s[ıi]n[ıi]r[ıi]\s*%\s*70|%\s*70'?[ıi]\s+a[şs]": "Pert sınırı %70'tir",
        r"kesinlikle\s+(?:pert|a[ğg][ıi]r\s+hasar)": "Bu araç kesinlikle pert",
    }
    example = examples[pattern]
    assert re.search(pattern, example, re.IGNORECASE), (
        f"pattern for {reason!r} does not match its own example {example!r}"
    )


def test_no_user_facing_string_promises_a_payout() -> None:
    """The scan itself.

    Failure here is not a style note. It means a sentence on screen tells a
    claimant what they will be paid, or what will happen to their car, and this
    system knows neither.
    """
    violations: list[str] = []

    for path in _scanned_files():
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            # A rule quoted in a comment explaining the rule is not a violation.
            stripped = line.strip()
            if stripped.startswith(("//", "*", "/*")):
                continue
            for pattern, reason in COMPILED:
                match = pattern.search(line)
                if match:
                    relative = path.relative_to(FRONTEND.parent)
                    violations.append(f"{relative}:{line_number}  {match.group(0)!r} -- {reason}")

    assert not violations, "user-facing copy promises what this system cannot:\n" + "\n".join(
        violations
    )


def test_the_scan_would_catch_a_planted_violation(tmp_path: Path) -> None:
    """Proves the scan works, without waiting for someone to write the bad line.

    The scan reads real files, so a bug in the traversal would make it pass
    forever. This plants a sentence and asserts the patterns fire on it.
    """
    planted = "  const summary = 'Sigortacı size 1.430.000 TL ödeyecek';"

    hits = [reason for pattern, reason in COMPILED if pattern.search(planted)]
    assert hits, "a plain payout promise slipped through every pattern"


# ---------------------------------------------------------------------------
# Turkish possessive suffixes on interpolated numbers
# ---------------------------------------------------------------------------
#
#  Not a promise, a grammar bug -- but the same class of defect and the same
#  scan catches it, so it lives here rather than in a file of its own.
#
#  A Turkish possessive suffix harmonises with how the preceding word is
#  PRONOUNCED, not how it is spelled. For a number that means the suffix depends
#  on the last word of the spoken form: %85 is "seksen beş" -> "%85'i", %20 is
#  "yirmi" -> "%20'si", %100 is "yüz" -> "%100'ü". A template that appends a
#  fixed "'i" is therefore right for some values and wrong for others, and which
#  ones it is wrong for changes with the data.
#
#  This was found by looking at the running page, fixed on the write-off lines,
#  and then reintroduced verbatim four months later on a different component.
#  The fix in both cases is "kadarı" / "kadarında", which attaches to a word
#  rather than to a digit. The rule is now a test instead of a memory.

SUFFIX_AFTER_NUMBER = re.compile(
    # An interpolated expression, optionally closed with `}`, immediately
    # followed by an apostrophe (literal or the `&apos;` entity) and a vowel.
    r"\{[^}]*\}(?:&apos;|['’])\s*[a-zçğıöşü]",
)


def test_no_possessive_suffix_is_appended_to_an_interpolated_number() -> None:
    """Use "kadarı"/"kadarında" instead; it attaches to a word, not to digits."""
    violations: list[str] = []

    for path in _scanned_files():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith(("//", "*", "/*")):
                continue
            match = SUFFIX_AFTER_NUMBER.search(line)
            if match:
                relative = path.relative_to(FRONTEND.parent)
                violations.append(f"{relative}:{line_number}  {match.group(0)!r}")

    assert not violations, (
        "a Turkish possessive suffix is glued to an interpolated value. The "
        "suffix follows pronunciation (%85'i but %20'si, %100'ü) and a template "
        "cannot know it. Use 'kadarı' / 'kadarında':\n" + "\n".join(violations)
    )


def test_the_suffix_scan_would_catch_a_planted_violation() -> None:
    """The same self-check the payout scan carries, for the same reason."""
    assert SUFFIX_AFTER_NUMBER.search("aracın %{Math.round(x * 100)}&apos;i")
    assert SUFFIX_AFTER_NUMBER.search("değerin %{ratio}'ı hasarlı")
    # And does not fire on the accepted form.
    assert not SUFFIX_AFTER_NUMBER.search("aracın %{Math.round(x * 100)} kadarı")
