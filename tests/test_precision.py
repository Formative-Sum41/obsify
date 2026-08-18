"""Tests for the deterministic precision filter (obsify/detection._post_recognize_filter).

Proves the filter kills the false positives that flood real numeric ledgers while
keeping context-validated identifiers and real names.

Run: python tests/test_precision.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from obsify.config import DEFAULT_CONFIG  # noqa: E402
from obsify.detection import _post_recognize_filter  # noqa: E402

EVAL = DEFAULT_CONFIG  # suppressors off (recall mode)
DETECT = replace(DEFAULT_CONFIG, suppress_letterless_detections=True,
                 suppress_ner_with_digits=True)  # detect mode


@dataclass
class R:  # minimal stand-in for a Presidio RecognizerResult
    entity_type: str
    start: int
    end: int


def _kept(text, entity_type, config):
    r = R(entity_type, 0, len(text))
    return bool(_post_recognize_filter([r], text, config))


def test_require_context_drops_unlabelled_id():
    # A bare number typed as TFN with no label word is dropped (both modes).
    assert not _kept("00000948", "AU_TFN", EVAL)
    assert not _kept("100000002", "AU_ACN", EVAL)


def test_require_context_keeps_labelled_id():
    assert _kept("TFN 123 456 782", "AU_TFN", EVAL)
    assert _kept("ABN 51 824 753 556", "AU_ABN", EVAL)


def test_letterless_suppression_detect_mode():
    # Amount flagged as phone -> dropped in detect mode, kept in eval mode.
    assert not _kept("24728837.75", "PHONE_NUMBER", DETECT)
    assert _kept("24728837.75", "PHONE_NUMBER", EVAL)


def test_letterless_exempts_context_id_and_account():
    # A labelled TFN and a BSB account are letterless but must survive detect mode.
    assert _kept("TFN 123 456 782", "AU_TFN", DETECT)
    assert _kept("40518261", "AU_BANK_ACCOUNT", DETECT)


def test_ner_with_digits_dropped_detect_mode():
    assert not _kept("EP180102", "ORGANIZATION", DETECT)
    assert not _kept("GJ180603", "PERSON", DETECT)


def test_real_names_survive():
    # Names/orgs carry letters and no digits, so the precision suppressors must keep
    # them (unlike codes like EP180102). Values here are synthetic.
    assert _kept("Trentmoor Logistics Group", "ORGANIZATION", DETECT)
    assert _kept("Jordan Avery", "PERSON", DETECT)
    assert _kept("Melbourne", "LOCATION", DETECT)


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
