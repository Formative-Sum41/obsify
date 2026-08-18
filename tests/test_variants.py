"""Tests for the differential variant expander (obsify/variants.py).

Run: python tests/test_variants.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from obsify.variants import canonicalize, distinctive_tokens, full_match, fuzzy_match  # noqa: E402


def test_suffix_normalized_full_matches():
    # Dictionary abbreviations fold to the same canonical form -> full catch.
    assert full_match("Veranth Holdings Pty Ltd", "elimination - VERANTH HLDGS P/L.")
    assert full_match("Bluehaven Nominees Pty Ltd", "paid BLUEHAVEN NOMS P/L")
    assert full_match("Trentmoor Logistics Pty Ltd", "TRENTMOOR LOGISTICS PROPRIETARY LIMITED")


def test_exact_is_a_full_match():
    assert full_match("Calderwell Marine Pty Ltd", "for Calderwell Marine Pty Ltd today")


def test_full_match_is_contiguous_not_loose():
    # Inserting a token breaks the full match (avoids over-broad catches).
    assert not full_match("Calderwell Marine Pty Ltd", "Calderwell Marine Services Pty Ltd")


def test_fuzzy_catches_nondictionary_truncation():
    # 'NOM' is not a dictionary abbreviation, so it is fuzzy-only, never full.
    m = "Bluehaven Nominees Pty Ltd"
    assert not full_match(m, "distribution to BLUEHAVEN NOM P/L pending")
    assert fuzzy_match(m, "distribution to BLUEHAVEN NOM P/L pending")


def test_fuzzy_does_not_flag_unrelated_entity():
    neg = "external counsel Smith & Associates Pty Ltd advised"
    for m in ("Bluehaven Nominees Pty Ltd", "Calderwell Marine Pty Ltd",
              "Veranth Holdings Pty Ltd", "Trentmoor Logistics Pty Ltd",
              "Oskestra Civil Engineering Pty Ltd"):
        assert not fuzzy_match(m, neg), m


def test_fuzzy_requires_all_distinctive_tokens_in_window():
    # Only one distinctive token present -> no fuzzy hit.
    assert not fuzzy_match("Calderwell Marine Pty Ltd", "the marine survey was filed")
    # Tokens too far apart -> outside the window.
    assert not fuzzy_match("Calderwell Marine Pty Ltd",
                           "Calderwell paid the invoice for the marine survey last week")


def test_distinctive_tokens_drop_legal_suffixes():
    assert distinctive_tokens("Bluehaven Nominees Pty Ltd") == ["bluehaven", "nominees"]
    assert canonicalize("Veranth Holdings Pty Ltd") == "veranth holdings ptyltd"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    print(f"\n{failures} failure(s)")
    sys.exit(1 if failures else 0)
