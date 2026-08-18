"""Tests for the fail-closed leak check (obsify/redaction.py) behind verify_value_free.

Covers: clean text passes, raw leak caught, suffix/abbreviation VARIANT leak caught,
case-insensitivity, empty terms, and that token overlap with structural words does NOT
false-trip unless the full value actually leaks.

Run: python tests/test_redaction.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from obsify.redaction import redaction_self_check  # noqa: E402

TERMS = [
    "Veranth Holdings Pty Ltd",
    "53 004 085 260",                          # an ABN value
    "120 Collins Street, Melbourne VIC 3000",
    "Location Partners Pty Ltd",               # 'Location' collides with a header word
]

# A realistic value-free blob that DOES contain colliding structural words
# ("Location" header, "cell D6" locator) but none of the forbidden values.
CLEAN = """
Types and counts only.
| Type | A | Location | Extraction |
| AU_ABN | miss | cell D6 | seen |
False positives: LOCATION=1, ORGANIZATION=11
"""


def test_clean_text_passes():
    assert redaction_self_check(CLEAN, TERMS) is False


def test_empty_terms_passes():
    assert redaction_self_check("anything at all", []) is False


def test_raw_value_leak_caught():
    leak = CLEAN + "\nsend to 120 Collins Street, Melbourne VIC 3000\n"
    assert redaction_self_check(leak, TERMS) is True


def test_abn_value_leak_caught():
    assert redaction_self_check(CLEAN + "\nABN 53 004 085 260 noted\n", TERMS) is True


def test_case_insensitive_leak_caught():
    assert redaction_self_check("contact VERANTH HOLDINGS PTY LTD", ["Veranth Holdings Pty Ltd"]) is True


def test_suffix_variant_leak_caught():
    # An abbreviated legal-suffix form of a term still leaks it.
    assert redaction_self_check("note re VERANTH HLDGS P/L", ["Veranth Holdings Pty Ltd"]) is True


def test_colliding_tokens_alone_do_not_false_trip():
    # 'Location' (a header word) is in CLEAN, but the full value 'Location Partners
    # Pty Ltd' is not -> must NOT be flagged.
    assert redaction_self_check(CLEAN, TERMS) is False


def test_colliding_full_value_leak_caught():
    assert redaction_self_check(CLEAN + "\nfee to Location Partners Pty Ltd\n", TERMS) is True


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
