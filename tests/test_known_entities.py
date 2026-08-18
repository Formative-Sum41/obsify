"""Tests for known-entity matching (obsify/known_entities.py) and its tool integration.

Matcher-level tests are model-free and fast; one integration test drives scan_pii /
redact_text with a local `.obsify.entities` file and asserts KNOWN_ENTITY is detected /
masked while the names themselves never appear in the shape output.

Run: python tests/test_known_entities.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import obsify.known_entities as K  # noqa: E402  (obsify first -> DLL bootstrap)


def _spans(text, names, fuzzy=False):
    return [text[s:e] for s, e in K.find_known(text, K.compile_matchers(names, fuzzy))]


# ------------------------------------------------------------------ matcher ----

def test_exact_and_case_insensitive():
    assert _spans("paid to Brightwater Holdings Pty Ltd today",
                  ["Brightwater Holdings Pty Ltd"]) == ["Brightwater Holdings Pty Ltd"]
    assert _spans("PAID TO PRIYA NAIR", ["Priya Nair"]) == ["PRIYA NAIR"]


def test_suffix_and_abbreviation_variants_matched():
    # The abbreviated/suffix-variant form NER would likely miss.
    assert _spans("elimination - BRIGHTWATER HLDGS P/L.",
                  ["Brightwater Holdings Pty Ltd"]) == ["BRIGHTWATER HLDGS P/L"]
    # Bare core (no legal suffix) still matches.
    assert _spans("distribution to Brightwater Holdings pending",
                  ["Brightwater Holdings Pty Ltd"]) == ["Brightwater Holdings"]


def test_no_false_match_on_scattered_tokens():
    assert _spans("the water was bright and the holdings grew",
                  ["Brightwater Holdings Pty Ltd"]) == []
    assert _spans("unrelated Smith Associates Pty Ltd",
                  ["Brightwater Holdings Pty Ltd"]) == []


def test_fuzzy_tolerates_inserted_token_default_does_not():
    text = "payment to Brightwater Marine Holdings Pty Ltd"
    assert _spans(text, ["Brightwater Holdings Pty Ltd"], fuzzy=False) == []
    assert _spans(text, ["Brightwater Holdings Pty Ltd"], fuzzy=True) == [
        "Brightwater Marine Holdings Pty Ltd"]


def test_overlapping_matches_deduped_longest_wins():
    # Two entries that both match the same region -> one non-overlapping span.
    spans = K.find_known("ref Brightwater Holdings Pty Ltd",
                         K.compile_matchers(["Brightwater Holdings", "Brightwater Holdings Pty Ltd"]))
    assert len(spans) == 1


# ------------------------------------------------------------ file handling ----

def test_load_entities_skips_comments_and_blanks():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / ".obsify.entities"
        f.write_text("# a comment\nBrightwater Holdings Pty Ltd\n\n  Priya Nair  \n", encoding="utf-8")
        assert K.load_entities(str(f)) == ["Brightwater Holdings Pty Ltd", "Priya Nair"]


def test_discover_walks_up_from_a_nested_path():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / ".obsify.entities").write_text("Acme\n", encoding="utf-8")
        nested = Path(d) / "a" / "b"
        nested.mkdir(parents=True)
        found = K.discover(str(nested / "file.xlsx"))
        assert found is not None and Path(found).name == ".obsify.entities"


def test_init_scaffolds_entities_template():
    import obsify.init as I
    with tempfile.TemporaryDirectory() as d:
        target = Path(d)
        msg = I._write_entities(target)
        assert (target / ".obsify.entities").exists() and "wrote" in msg
        body = (target / ".obsify.entities").read_text(encoding="utf-8")
        assert body.lstrip().startswith("#") and "KNOWN" in body  # template, no real names
        # never overwrites (may hold real names)
        assert "already exists" in I._write_entities(target)


# -------------------------------------------------------------- integration ----

def test_scan_and_redact_with_known_entities():
    import openpyxl
    import obsify.mcp_server as S
    with tempfile.TemporaryDirectory() as d:
        ents = Path(d) / ".obsify.entities"
        ents.write_text("Brightwater Holdings Pty Ltd\nPriya Nair\n", encoding="utf-8")
        p = Path(d) / "ledger.xlsx"
        wb = openpyxl.Workbook(); ws = wb.active
        ws.append(["Desc"]); ws.append(["elimination - BRIGHTWATER HLDGS P/L"]); ws.append(["ref Priya Nair"])
        wb.save(str(p))

        r = S.scan_pii(str(p), entities=str(ents))
        assert r["counts_by_type"].get("KNOWN_ENTITY", 0) >= 2, r["counts_by_type"]
        # shape only — no name (or variant) leaks into the output
        blob = json.dumps(r)
        assert "Brightwater" not in blob and "BRIGHTWATER" not in blob and "Priya" not in blob

        masked = S.redact_text("elimination - BRIGHTWATER HLDGS P/L; contact Priya Nair",
                               entities=str(ents))
        assert "BRIGHTWATER" not in masked and "Priya" not in masked
        assert "<KNOWN_ENTITY>" in masked


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
