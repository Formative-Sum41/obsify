"""Checksum validator tests anchored to externally-published worked examples.

Run: python -m pytest tests/test_checksums.py
(or execute directly: python tests/test_checksums.py)

These tests break the generator<->validator circularity described in
obsify/checksums.py: they assert against numbers whose validity was established
outside this codebase (ATO/ASIC worked examples), plus deliberately corrupted
variants that must be rejected.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from obsify.checksums import (  # noqa: E402
    complete_acn,
    complete_medicare,
    is_valid_abn,
    is_valid_acn,
    is_valid_medicare,
    is_valid_tfn,
)


def test_abn_external_anchor_valid():
    # ATO worked example.
    assert is_valid_abn("51 824 753 556")
    assert is_valid_abn("51824753556")


def test_abn_rejects_corrupted():
    # Flip one digit -> must fail the modulus-89 check.
    assert not is_valid_abn("51824753557")
    assert not is_valid_abn("51824753546")
    # Wrong length.
    assert not is_valid_abn("5182475355")
    assert not is_valid_abn("")


def test_acn_external_anchor_valid():
    # ASIC worked example.
    assert is_valid_acn("004 085 616")
    assert is_valid_acn("004085616")


def test_acn_rejects_corrupted():
    assert not is_valid_acn("004085617")  # wrong check digit
    assert not is_valid_acn("104085616")  # altered body
    assert not is_valid_acn("00408561")   # wrong length


def test_tfn_external_anchor_valid():
    # 9-digit TFN worked example, weighted sum 253 (=11*23).
    assert is_valid_tfn("123 456 782")
    assert is_valid_tfn("123456782")


def test_tfn_rejects_corrupted():
    assert not is_valid_tfn("123456783")  # breaks divisibility by 11
    assert not is_valid_tfn("123456780")
    assert not is_valid_tfn("1234567")    # wrong length


def test_medicare_anchor_valid():
    # First 8 digits weighted [1,3,7,9,1,3,7,9]; sum % 10 == 9th (check) digit.
    assert is_valid_medicare("2123 45670 1")
    assert is_valid_medicare("2123456701")


def test_medicare_rejects_corrupted():
    assert not is_valid_medicare("2123456711")  # wrong check digit
    assert not is_valid_medicare("1123456701")  # first digit must be 2-6
    assert not is_valid_medicare("212345670")   # wrong length


def test_complete_medicare_roundtrips():
    for stem in ("21234567", "39876543", "60000000"):
        assert is_valid_medicare(complete_medicare(stem))


def test_complete_acn_roundtrips():
    # Minting must produce numbers the validator accepts (internal consistency),
    # and must agree with the external anchor stem.
    assert complete_acn("00408561") == "004085616"
    for stem in ("12345678", "98765432", "10000000"):
        assert is_valid_acn(complete_acn(stem))


if __name__ == "__main__":
    # Allow running without pytest installed.
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
