"""Tests for variant normalization (obsify/variants.py).

`canonicalize` and `distinctive_tokens` back `verify_value_free`'s variant-aware leak
check: a term and its legal-suffix abbreviations must fold to the same canonical form.

Run: python tests/test_variants.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from obsify.variants import canonicalize, distinctive_tokens  # noqa: E402


def test_canonicalize_folds_legal_suffix_variants():
    # Abbreviated and full legal-suffix forms fold to the same canonical string, so a
    # term and its variant compare equal in a leak check.
    assert canonicalize("Veranth Holdings Pty Ltd") == canonicalize("VERANTH HLDGS P/L")
    assert canonicalize("Bluehaven Nominees Pty Ltd") == canonicalize("BLUEHAVEN NOMS P/L")
    assert canonicalize("Trentmoor Logistics Pty Ltd") == canonicalize(
        "trentmoor logistics proprietary limited")


def test_canonicalize_expected_form():
    assert canonicalize("Veranth Holdings Pty Ltd") == "veranth holdings ptyltd"


def test_canonicalize_distinguishes_unrelated_entities():
    assert canonicalize("Calderwell Marine Pty Ltd") != canonicalize("Smith Associates Pty Ltd")


def test_distinctive_tokens_drop_legal_suffixes():
    assert distinctive_tokens("Bluehaven Nominees Pty Ltd") == ["bluehaven", "nominees"]
    assert distinctive_tokens("Calderwell Marine Pty Ltd") == ["calderwell", "marine"]


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
