"""Robustness / graceful-degradation tests.

Codifies the behavior observed on real data (corrupt workbooks skipped with a note,
oversized sheets capped with a blind-spot note) plus the other edges: unsupported
types, no suffix, empty files, nested directories, and a mixed dir. The invariant:
obsify never crashes and never *silently* drops a file — every skip/cap is a note.

Extraction-level cases use extract_document (no model, fast). Cap/recursion cases use
scan_pii (loads the NER model once).

Run: python tests/test_robustness.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import openpyxl  # noqa: E402

import obsify.mcp_server as S            # noqa: E402  (obsify first -> DLL bootstrap)
from obsify.extraction import extract_document  # noqa: E402


def _xlsx(path: Path, rows: int, cols: int = 3) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "S"
    for r in range(rows):
        ws.append([f"cell_{r}_{c}" for c in range(cols)])
    wb.save(str(path))


# ---------------------------------------------------- extraction-level (no model) --

def test_corrupt_workbook_skipped_with_note():
    with tempfile.TemporaryDirectory() as d:
        bad = Path(d) / "corrupt.xlsx"
        bad.write_bytes(b"this is not a real zip/xlsx payload")
        notes: list[str] = []
        segs, cov = extract_document(str(bad), notes)
        assert segs == [] and cov == []
        assert any("could not read" in n for n in notes), notes


def test_unsupported_type_noted_not_crashed():
    with tempfile.TemporaryDirectory() as d:
        txt = Path(d) / "notes.txt"
        txt.write_text("hello", encoding="utf-8")
        notes: list[str] = []
        segs, _ = extract_document(str(txt), notes)
        assert segs == []
        assert any("unsupported file type" in n for n in notes), notes


def test_no_suffix_noted():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "README"
        f.write_text("x", encoding="utf-8")
        notes: list[str] = []
        extract_document(str(f), notes)
        assert any("unsupported file type" in n for n in notes), notes


def test_empty_workbook_does_not_crash():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "empty.xlsx"
        openpyxl.Workbook().save(str(p))  # one empty sheet
        notes: list[str] = []
        segs, cov = extract_document(str(p), notes)
        assert isinstance(segs, list)  # no exception; possibly zero segments


# ---------------------------------------------------- scan_pii-level (model once) --

def test_oversized_sheet_capped_with_blindspot_note():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "big.xlsx"
        _xlsx(p, rows=40, cols=3)           # ~120 cells
        r = S.scan_pii(str(p), max_cells=10)
        assert r["files_read"] == 1
        assert any("max_cells" in n or "UNSCANNED REMAINDER" in n for n in r["notes"]), r["notes"]


def test_scan_recurses_nested_dirs():
    with tempfile.TemporaryDirectory() as d:
        nested = Path(d) / "a" / "b" / "c"
        nested.mkdir(parents=True)
        _xlsx(nested / "deep.xlsx", rows=3)
        r = S.scan_pii(str(d))
        assert r["files_found"] >= 1 and r["files_read"] >= 1


def test_mixed_dir_reads_good_notes_bad_never_crashes():
    with tempfile.TemporaryDirectory() as d:
        _xlsx(Path(d) / "good.xlsx", rows=3)
        (Path(d) / "corrupt.xlsx").write_bytes(b"nope")
        (Path(d) / "readme.txt").write_text("hi", encoding="utf-8")
        r = S.scan_pii(str(d))
        # the good file is read; the corrupt one is noted; unsupported .txt isn't
        # discovered (wrong suffix), so it simply doesn't appear — no crash either way.
        assert r["files_read"] >= 1
        assert any("could not read" in n for n in r["notes"]), r["notes"]


def test_missing_path_is_graceful():
    r = S.scan_pii(str(Path(tempfile.gettempdir()) / "obsify_does_not_exist_zzz"))
    assert r["files_found"] == 0 and r["files_read"] == 0


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
