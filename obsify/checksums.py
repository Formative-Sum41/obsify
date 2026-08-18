"""Deterministic checksum validators for Australian entity identifiers.

The detection recognizers use these to *confirm* candidates (a random 11-digit
string is never reported as an ABN — only a checksum-valid one is), and the demo/eval
generators use the minting helpers to produce valid synthetic identifiers. Because
generator and recognizer would share this code, each algorithm below is anchored to an
externally-published worked example and tests/test_checksums.py checks these validators
against those external valid AND invalid numbers — breaking the generator/validator
circularity.

All validators accept a raw string (which may contain spaces, hyphens, or other
separators), extract the digits, and return a bool. They never raise on
malformed input; non-conforming input is simply invalid.
"""

from __future__ import annotations

import re

_NON_DIGIT = re.compile(r"\D")


def _digits(value: str) -> str:
    """Strip every non-digit character, returning only the digit sequence."""
    return _NON_DIGIT.sub("", value)


# --- ABN: Australian Business Number (11 digits) -----------------------------
# Official ATO modulus-89 algorithm:
#   1. Subtract 1 from the first (leftmost) digit.
#   2. Multiply each of the 11 digits by its positional weight.
#   3. If the weighted sum is divisible by 89, the ABN is valid.
# External anchor: ABN 51 824 753 556 -> weighted sum 534, 534 % 89 == 0 (valid).
ABN_WEIGHTS = (10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19)


def is_valid_abn(value: str) -> bool:
    d = _digits(value)
    if len(d) != 11:
        return False
    digits = [int(c) for c in d]
    digits[0] -= 1  # subtract 1 from the leading digit
    total = sum(w * n for w, n in zip(ABN_WEIGHTS, digits))
    return total % 89 == 0


# --- ACN: Australian Company Number (9 digits) -------------------------------
# Official ASIC check-digit algorithm:
#   1. Weight the first 8 digits by [8,7,6,5,4,3,2,1] and sum.
#   2. remainder = sum % 10; complement = (10 - remainder) % 10.
#   3. The complement must equal the 9th (check) digit.
# External anchor: ACN 004 085 616 -> sum 84, (10 - 4) % 10 == 6 == check digit.
ACN_WEIGHTS = (8, 7, 6, 5, 4, 3, 2, 1)


def is_valid_acn(value: str) -> bool:
    d = _digits(value)
    if len(d) != 9:
        return False
    digits = [int(c) for c in d]
    total = sum(w * n for w, n in zip(ACN_WEIGHTS, digits[:8]))
    check = (10 - (total % 10)) % 10
    return check == digits[8]


# --- TFN: Tax File Number (8 or 9 digits) ------------------------------------
# Official ATO weighted-modulus-11 algorithm. The weighted sum of all digits
# must be divisible by 11. Two weight sets exist for the two historical lengths:
#   9-digit weights: [1, 4, 3, 7, 5, 8, 6, 9, 10]
#   8-digit weights: [10, 7, 8, 4, 6, 3, 5, 1]
# External anchor (9-digit): TFN 123 456 782 -> weighted sum 253, 253 % 11 == 0.
# The 8-digit weight set is the documented older ATO algorithm; the fixtures
# plant a checksum-verified 9-digit TFN (the anchored path).
TFN_WEIGHTS_9 = (1, 4, 3, 7, 5, 8, 6, 9, 10)
TFN_WEIGHTS_8 = (10, 7, 8, 4, 6, 3, 5, 1)


def is_valid_tfn(value: str) -> bool:
    d = _digits(value)
    if len(d) == 9:
        weights = TFN_WEIGHTS_9
    elif len(d) == 8:
        weights = TFN_WEIGHTS_8
    else:
        return False
    total = sum(w * int(c) for w, c in zip(weights, d))
    return total % 11 == 0


# --- Medicare card number (10 or 11 digits) ----------------------------------
# The first digit is 2-6; the first 8 digits are weighted by [1,3,7,9,1,3,7,9]
# and the sum modulo 10 must equal the 9th (check) digit. The 10th digit is an
# issue number and an optional 11th is the individual reference number (IRN).
# External anchor: 2123 45670 1 -> weighted sum of first 8 % 10 == 0 == 9th digit.
MEDICARE_WEIGHTS = (1, 3, 7, 9, 1, 3, 7, 9)


def is_valid_medicare(value: str) -> bool:
    d = _digits(value)
    if len(d) not in (10, 11):
        return False
    if d[0] not in "23456":
        return False
    total = sum(w * int(c) for w, c in zip(MEDICARE_WEIGHTS, d[:8]))
    return total % 10 == int(d[8])


# --- Minting helpers (used only by the fixture/eval generators) --------------
# These derive a valid check digit / final digit so a generator can produce
# synthetic-but-checksum-valid identifiers from an arbitrary numeric stem.


def complete_acn(first_eight: str) -> str:
    """Given 8 digits, append the ASIC check digit to form a valid 9-digit ACN."""
    d = _digits(first_eight)
    if len(d) != 8:
        raise ValueError("ACN stem must be exactly 8 digits")
    total = sum(w * int(c) for w, c in zip(ACN_WEIGHTS, d))
    check = (10 - (total % 10)) % 10
    return d + str(check)


def complete_medicare(first_eight: str, issue: int = 1) -> str:
    """Given 8 digits (first in 2-6), append the check digit and an issue number
    to form a valid 10-digit Medicare number."""
    d = _digits(first_eight)
    if len(d) != 8 or d[0] not in "23456":
        raise ValueError("Medicare stem must be 8 digits starting 2-6")
    total = sum(w * int(c) for w, c in zip(MEDICARE_WEIGHTS, d))
    return d + str(total % 10) + str(issue)
