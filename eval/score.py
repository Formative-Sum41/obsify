"""Score obsify's detection against the labelled eval corpus — SYNTHETIC DATA ONLY.

Runs the exact SHIPPING detector (`_DETECT_CFG`: the same suppressors mcp_server uses)
over the generated corpus, matches detections against the answer key, and reports:

  * recall  — of items expected to DETECT, how many were flagged (per type + overall);
  * suppression — of items expected to SUPPRESS (bare context-gated IDs), how many were
                  correctly dropped (a suppression is designed behaviour, not a miss);
  * coverage gaps — items obsify has no recognizer for (expected 0; confirmed here);
  * precision — detections matching a planted value (TP) vs matching none (FP), with the
                FP-torture rate (detections on the numeric Journals sheet, which plants no
                PII) called out as the honest numeric-noise signal.

Matching reuses the harness's proven logic: normalized (whitespace-collapsed, casefolded)
containment; an item is caught if a flagged span contains it (full) or a >=4-char flagged
span sits inside it (partial). This grades the same synthetic values it planted — the
external benchmark (eval/bench_external.py) is the independent cross-check.

  ##  NEVER point this at real data.  It reads detected VALUES to match them; that is only
  ##  safe because the corpus is fabricated.

Run:  python eval/score.py --corpus ./eval_corpus [--out eval_report.md]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from obsify.config import DEFAULT_CONFIG
from obsify.detection import _analyze
from obsify.extraction import extract_document, normalize_ws
from obsify.nlp import build_analyzers

# The detector users actually get (mcp_server's posture).
_DETECT_CFG = replace(DEFAULT_CONFIG, suppress_letterless_detections=True,
                      suppress_ner_with_digits=True)
_TORTURE_SHEET = "Journals"   # the FP-torture sheet plants no PII


def _norm(s) -> str:
    return normalize_ws(str(s)).casefold()


def _load_key(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _f1(p: float, r: float) -> float:
    return 0.0 if (p + r) == 0 else round(2 * p * r / (p + r), 3)


def evaluate(corpus_dir: str) -> dict:
    corpus = Path(corpus_dir)
    key = _load_key(corpus / "answer_key.jsonl")
    _, analyzer = build_analyzers(_DETECT_CFG)

    # detect (with values — synthetic only) per document
    dets_by_doc: dict[str, list] = {}
    for doc in sorted({it["document"] for it in key}):
        path = corpus / doc
        if not path.exists():
            dets_by_doc[doc] = []
            continue
        notes: list[str] = []
        segs, _ = extract_document(str(path), notes)
        dets_by_doc[doc] = _analyze(analyzer, segs, _DETECT_CFG, "obsify")

    detnorm_by_doc = {doc: [(_norm(d.text), d) for d in dets] for doc, dets in dets_by_doc.items()}

    # --- match each planted item ---
    for it in key:
        dets = detnorm_by_doc.get(it["document"], [])
        val = _norm(it["value"])
        full = any(val and val in dn for dn, _ in dets)
        partial = any(dn and dn in val and len(dn) >= 4 for dn, _ in dets)
        it["_caught"] = full or partial

    # --- precision: TP = detection matching a planted value; FP = matching none ---
    planted_by_doc: dict[str, list[str]] = defaultdict(list)
    for it in key:
        planted_by_doc[it["document"]].append(_norm(it["value"]))
    tp = 0
    fp: list = []
    for doc, dets in detnorm_by_doc.items():
        pl = [p for p in planted_by_doc.get(doc, []) if p]
        for dn, d in dets:
            if dn and any(dn in p or p in dn for p in pl):
                tp += 1
            else:
                fp.append(d)
    fp_torture = [d for d in fp if _TORTURE_SHEET.lower() in d.locator.lower()]
    total_dets = sum(len(v) for v in dets_by_doc.values())
    precision = round(tp / (tp + len(fp)), 3) if (tp + len(fp)) else 0.0

    # --- partition by expected behaviour, per type ---
    per_type: dict[str, dict] = defaultdict(lambda: {"detect": 0, "caught": 0,
                                                     "suppress": 0, "suppressed_ok": 0,
                                                     "gap": 0, "gap_detected": 0})
    det_total = det_caught = sup_total = sup_ok = gap_total = gap_det = 0
    misses: list[dict] = []
    for it in key:
        pt = per_type[it["type"]]
        if it["expected"] == "detect":
            pt["detect"] += 1; det_total += 1
            if it["_caught"]:
                pt["caught"] += 1; det_caught += 1
            else:
                misses.append(it)
        elif it["expected"] == "suppress":
            pt["suppress"] += 1; sup_total += 1
            if not it["_caught"]:
                pt["suppressed_ok"] += 1; sup_ok += 1
        elif it["expected"] == "gap":
            pt["gap"] += 1; gap_total += 1
            if it["_caught"]:
                pt["gap_detected"] += 1; gap_det += 1

    recall = round(det_caught / det_total, 3) if det_total else 0.0
    return {
        "precision": precision, "recall": recall, "f1": _f1(precision, recall),
        "tp": tp, "fp": len(fp), "fp_torture": len(fp_torture), "total_detections": total_dets,
        "detect_total": det_total, "detect_caught": det_caught,
        "suppress_total": sup_total, "suppressed_ok": sup_ok,
        "gap_total": gap_total, "gap_detected": gap_det,
        "per_type": dict(per_type),
        "misses": misses,
        "fp_types": _count_types(fp),
    }


def _count_types(dets) -> dict:
    c: dict[str, int] = defaultdict(int)
    for d in dets:
        c[d.entity_type] += 1
    return dict(sorted(c.items()))


def render_report(res: dict) -> str:
    L = ["# obsify evaluation report", "",
         "_Synthetic corpus, scored against the shipping detector (`_DETECT_CFG`). "
         "All values fabricated._", "",
         "## Headline", "",
         f"- **Recall** (items expected to detect): **{res['recall']:.1%}** "
         f"({res['detect_caught']}/{res['detect_total']})",
         f"- **Precision** (TP / TP+FP): **{res['precision']:.1%}** "
         f"({res['tp']} TP, {res['fp']} FP)",
         f"- **F1**: {res['f1']}",
         f"- **Suppression correct** (bare context-gated IDs dropped by policy): "
         f"{res['suppressed_ok']}/{res['suppress_total']}",
         f"- **FP-torture** (false positives on the numeric Journals sheet, no PII planted): "
         f"**{res['fp_torture']}**",
         f"- **Coverage gaps** (no recognizer): {res['gap_total']} planted, "
         f"{res['gap_detected']} detected (expect 0)",
         "", "## Recall by type (expected=detect)", "",
         "| Type | Caught / Total |", "|---|---|"]
    for t, s in sorted(res["per_type"].items()):
        if s["detect"]:
            L.append(f"| {t} | {s['caught']}/{s['detect']} |")
    L += ["", "## Suppression by type (expected=suppress — higher is better)", "",
          "| Type | Suppressed / Total |", "|---|---|"]
    for t, s in sorted(res["per_type"].items()):
        if s["suppress"]:
            L.append(f"| {t} | {s['suppressed_ok']}/{s['suppress']} |")
    L += ["", "## Coverage gaps (expected=gap — detection impossible, documented)", "",
          "| Type | Detected / Planted |", "|---|---|"]
    for t, s in sorted(res["per_type"].items()):
        if s["gap"]:
            L.append(f"| {t} | {s['gap_detected']}/{s['gap']} |")
    L += ["", "## False positives by type", "",
          "| Entity type | FP count |", "|---|---:|"]
    for t, n in res["fp_types"].items():
        L.append(f"| {t} | {n} |")
    if res["misses"]:
        L += ["", "## Recall misses (expected=detect, not caught)", "",
              "| Type | Note |", "|---|---|"]
        for m in res["misses"]:
            L.append(f"| {m['type']} | {m.get('note', '')} |")
    L.append("")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python eval/score.py",
                                 description="Score obsify detection against the eval corpus.")
    ap.add_argument("--corpus", default="./eval_corpus")
    ap.add_argument("--out", default=None, help="write the markdown report here")
    args = ap.parse_args(argv)

    res = evaluate(args.corpus)
    report = render_report(res)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"[score] report written: {args.out}")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
