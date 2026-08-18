"""Tests for the redacted-summary self-check (obsify/redaction.py).

The self-check is the safety boundary for the only artifact that may cross the
perimeter to an LLM. These tests prove it (a) passes a genuinely value-free
summary, (b) catches a raw value leak, (c) catches a suffix/abbreviation VARIANT
leak, (d) is NOT fooled into a false pass or false fail by a value whose tokens
collide with the summary's own structural words, and (e) fails closed at the
writer (deletes the file, returns False).

Run: python tests/test_redaction.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from obsify.redaction import redaction_self_check, write_redacted_summary  # noqa: E402

MASTER = [
    "Veranth Holdings Pty Ltd",
    "Location Partners Pty Ltd",   # 'Location' collides with a summary header
    "Cell Dynamics Pty Ltd",       # 'Cell' collides with cell locators
]
GT = [
    "53 004 085 260",              # ABN value
    "120 Collins Street, Melbourne VIC 3000",
    "Location Partners Pty Ltd",
]

# Document/sheet identifiers that must also never leak (a filename or tab name
# can identify a client). The summary anonymizes these to Doc N / Sheet K.
IDENTIFIERS = ["engagement_letter.pdf", "GL Detail"]

# A realistic value-free, ANONYMIZED summary body that DOES contain the colliding
# structural words ("Location" header, "cell D6" locator, "CLIENT_NAME"/"AU_ABN"
# types) but no values and no raw document/sheet identifiers.
CLEAN_SUMMARY = """
## Missed & partial items (type + location only)
| Type | A | B | C | Fuzzy (C) | Location | Extraction |
| CLIENT_NAME | miss | miss | full | - | Doc 2 / Sheet 1 / cell D6 | seen |
| AU_ABN | miss | full | full | - | Doc 4 / page 1 / line 10 | seen |
## False positives
| A | 12 | LOCATION=1, ORGANIZATION=11 |
"""


def test_clean_summary_passes():
    assert redaction_self_check(CLEAN_SUMMARY, GT, MASTER) is False


def test_raw_value_leak_caught():
    leak = CLEAN_SUMMARY + "\naccidental: 120 Collins Street, Melbourne VIC 3000\n"
    assert redaction_self_check(leak, GT, MASTER) is True


def test_abn_value_leak_caught():
    leak = CLEAN_SUMMARY + "\nABN 53 004 085 260 slipped in\n"
    assert redaction_self_check(leak, GT, MASTER) is True


def test_suffix_variant_leak_caught():
    # A variant surface form NER/differential would treat as the same client.
    leak = CLEAN_SUMMARY + "\nnote re VERANTH HLDGS P/L\n"
    assert redaction_self_check(leak, GT, MASTER) is True


def test_collision_value_leak_caught():
    # The full colliding value leaking must be caught (not excused as a header).
    leak = CLEAN_SUMMARY + "\nfee to Location Partners Pty Ltd\n"
    assert redaction_self_check(leak, GT, MASTER) is True


def test_collision_tokens_alone_do_not_false_trip():
    # 'Location' (header) and 'cell' (locator) appear, but neither full client
    # value does -> must NOT be flagged as a leak.
    assert redaction_self_check(CLEAN_SUMMARY, GT, MASTER) is False


def test_writer_fails_closed_and_deletes():
    leak = CLEAN_SUMMARY + "\nleak: Veranth Holdings Pty Ltd\n"
    with tempfile.TemporaryDirectory() as d:
        path = str(Path(d) / "summary.md")
        ok = write_redacted_summary(leak, path, GT, MASTER)
        assert ok is False, "writer should report failure on leak"
        assert not Path(path).exists(), "leaky summary file must be deleted"


def test_writer_keeps_clean_file():
    with tempfile.TemporaryDirectory() as d:
        path = str(Path(d) / "summary.md")
        ok = write_redacted_summary(CLEAN_SUMMARY, path, GT, MASTER, IDENTIFIERS)
        assert ok is True
        assert Path(path).exists()


def test_clean_passes_with_identifiers():
    assert redaction_self_check(CLEAN_SUMMARY, GT, MASTER, IDENTIFIERS) is False


def test_filename_leak_caught():
    # A client-identifying filename must be caught even though it is not a GT/master value.
    leak = CLEAN_SUMMARY + "\nsource file: engagement_letter.pdf\n"
    assert redaction_self_check(leak, GT, MASTER, IDENTIFIERS) is True


def test_sheet_name_leak_caught():
    leak = CLEAN_SUMMARY + "\nfrom sheet 'GL Detail'\n"
    assert redaction_self_check(leak, GT, MASTER, IDENTIFIERS) is True


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
