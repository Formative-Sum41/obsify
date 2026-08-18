"""Scored-evaluation test — turns the eval harness into a regression gate.

Generates the labelled synthetic corpus (eval/generate.py) and scores obsify's
shipping detector against it (eval/score.py), then asserts:

  * DETERMINISTIC guarantees exactly (regex/checksum/policy — model-independent):
    zero FP-torture, all bare context-gated IDs suppressed, coverage gaps stay 0,
    and every checksum/regex-validated type is fully caught;
  * NER-dependent recall/precision against thresholds (spaCy output can vary slightly
    across model versions, so these are bounds, not equalities).

Also guards the credit-card fix (a Luhn-valid card must not be dropped by letterless
suppression). Requires the eval deps (faker; reportlab for the PDF planted items).

Run: python tests/test_evaluation.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "eval"))

import obsify  # noqa: E402,F401  (bootstrap before spaCy)
import generate as G  # noqa: E402  (eval/generate.py)
import score as SC    # noqa: E402  (eval/score.py)

# checksum/regex-validated types the deterministic pipeline must always catch
_DETERMINISTIC = ("AU_ABN", "AU_ACN", "AU_TFN", "CREDIT_CARD", "IBAN_CODE",
                  "EMAIL_ADDRESS", "ENGAGEMENT_CODE", "AU_ADDRESS",
                  "MEDICARE", "IP_ADDRESS", "DATE_OF_BIRTH",
                  "AU_PASSPORT", "AU_DRIVER_LICENCE")


def test_eval_scoreboard_meets_thresholds():
    with tempfile.TemporaryDirectory() as d:
        G.build_eval_corpus(d)
        res = SC.evaluate(d)

        # --- deterministic guarantees (must hold exactly) ---
        assert res["fp_torture"] == 0, f"numeric-noise FP flood: {res['fp_torture']}"
        assert res["suppress_total"] >= 3 and res["suppressed_ok"] == res["suppress_total"], res
        # any remaining documented gap (e.g. AU passport) must stay undetected
        assert res["gap_total"] >= 1 and res["gap_detected"] == 0, res

        pt = res["per_type"]
        for t in _DETERMINISTIC:
            s = pt.get(t)
            if s and s["detect"]:                       # PDF-only types absent if no reportlab
                assert s["caught"] == s["detect"], f"{t} recall regressed: {s}"

        # --- NER-dependent (thresholds) ---
        assert res["recall"] >= 0.9, f"overall recall too low: {res['recall']}"
        assert res["precision"] >= 0.5, f"precision too low: {res['precision']}"


def test_credit_card_not_dropped_by_letterless_suppression():
    # Regression guard for the fix: a Luhn-valid card is validated PII, not numeric
    # noise, so the letterless suppressor must not drop it.
    with tempfile.TemporaryDirectory() as d:
        G.build_eval_corpus(d)
        res = SC.evaluate(d)
        cc = res["per_type"].get("CREDIT_CARD", {"caught": 0, "detect": 0})
        assert cc["detect"] >= 1 and cc["caught"] == cc["detect"], cc


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
            except Exception as e:  # noqa: BLE001
                failures += 1
                print(f"ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{failures} failure(s)")
    sys.exit(1 if failures else 0)
