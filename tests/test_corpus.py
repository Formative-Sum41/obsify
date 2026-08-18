"""End-to-end test over the synthetic complex corpus (obsify/make_corpus.py).

Exercises all three formats through the real pipeline: multi-sheet Excel, DOCX
(paragraphs + tables), and — when reportlab is present — PDF. Asserts the expected
PII types are detected per format, that DOCX extraction yields both prose and table
segments, that the numeric ledger does NOT flood with false positives (precision),
and that scan_pii returns SHAPE ONLY across every format (no planted value leaks).

Run: python tests/test_corpus.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import obsify.make_corpus as MC          # noqa: E402  (imports obsify first -> DLL bootstrap)
import obsify.mcp_server as S            # noqa: E402
from obsify.extraction import extract_document  # noqa: E402


def _by_name(files, suffix):
    return next(f for f in files if f.endswith(suffix))


def _flat_planted(planted: dict) -> list[str]:
    out: list[str] = []
    for v in planted.values():
        out.extend(v if isinstance(v, list) else [v])
    return out


def test_corpus_writes_all_formats():
    with tempfile.TemporaryDirectory() as d:
        res = MC.build_corpus(d)
        names = {Path(f).name for f in res["files"]}
        assert "ledger.xlsx" in names and "audit_memo.docx" in names
        assert "master_list.txt" in names
        # PDF only when reportlab is installed; otherwise a note explains the skip.
        if "engagement_letter.pdf" not in names:
            assert any("reportlab" in n for n in res["notes"])


def test_excel_detects_labelled_ids_without_fp_flood():
    with tempfile.TemporaryDirectory() as d:
        res = MC.build_corpus(d)
        r = S.scan_pii(_by_name(res["files"], "ledger.xlsx"))
        c = r["counts_by_type"]
        assert r["files_read"] == 1
        # Inline-labelled identifiers ARE detected.
        assert c.get("AU_ABN", 0) >= 2, c
        assert c.get("AU_ACN", 0) >= 1, c
        assert c.get("EMAIL_ADDRESS", 0) >= 2, c
        # PRECISION: the 8-digit sequential JournalIDs carry no context word, so
        # none are flagged as TFN/ACN — only the one inline-labelled TFN survives.
        assert c.get("AU_TFN", 0) == 1, f"numeric-ledger FP flood not suppressed: {c}"
        assert c.get("AU_ACN", 0) == 1, f"bare IDs mis-flagged as ACN: {c}"


def test_docx_end_to_end_detection():
    with tempfile.TemporaryDirectory() as d:
        res = MC.build_corpus(d)
        docx = _by_name(res["files"], "audit_memo.docx")
        r = S.scan_pii(docx)
        c = r["counts_by_type"]
        assert r["files_read"] == 1, "DOCX must be read by scan_pii"
        for t in ("AU_TFN", "EMAIL_ADDRESS", "PERSON", "ENGAGEMENT_CODE", "AU_ABN"):
            assert c.get(t, 0) >= 1, f"DOCX missing expected {t}: {c}"


def test_docx_extraction_yields_prose_and_table():
    with tempfile.TemporaryDirectory() as d:
        res = MC.build_corpus(d)
        notes: list[str] = []
        segs, _ = extract_document(_by_name(res["files"], "audit_memo.docx"), notes)
        kinds = {s.kind for s in segs}
        assert "prose" in kinds and "table_cell" in kinds, kinds
        assert not notes, f"clean docx should produce no skip notes: {notes}"


def test_scan_is_shape_only_across_all_formats():
    with tempfile.TemporaryDirectory() as d:
        res = MC.build_corpus(d)
        planted = _flat_planted(res["planted"])
        for f in res["files"]:
            if f.endswith(".txt"):
                continue  # the master list intentionally contains the client names
            blob = json.dumps(S.scan_pii(f)).lower()
            for v in planted:
                assert v.lower() not in blob, f"scan_pii leaked {v!r} from {Path(f).name}"


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
