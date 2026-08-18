"""Independent cross-check against a THIRD-PARTY synthetic PII benchmark.

The scored harness (eval/score.py) grades obsify against data obsify's own author
generated — useful, but circular. This script measures recall against Microsoft
`presidio-research`'s public synthetic dataset (`synth_dataset_v2.json`), which a
different team generated with a different taxonomy.

Honest scope (why this is a weak-but-real signal):
  * It is IN-FAMILY — obsify is built on Presidio, so this validates the shared
    recognizer stack, not obsify's custom AU logic.
  * The dataset has no AU_ABN/ACN/TFN, so it only exercises the GENERIC recognizers
    (PERSON / EMAIL / PHONE / CREDIT_CARD / IBAN / ORGANIZATION) — the least custom
    part of obsify.
  * Their labelling is partial, so PRECISION isn't meaningful here (a detection they
    didn't label may be correct, not a false positive). We report RECALL only, by the
    masking view: a ground-truth span is "caught" if any obsify detection overlaps it.

Network: fetches from GitHub (HuggingFace is not required). Result is cached under
eval/.cache/. If offline, it prints instructions and exits 0.

Run:  python eval/bench_external.py [--sample 300]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from obsify.config import DEFAULT_CONFIG
from obsify.detection import _post_recognize_filter
from obsify.nlp import build_analyzer

_URL = ("https://raw.githubusercontent.com/microsoft/presidio-research/master/"
        "data/synth_dataset_v2.json")
_CACHE = Path(__file__).resolve().parent / ".cache" / "synth_dataset_v2.json"

# Generic GT types we can fairly map to an obsify recognizer.
_MAPPED = {"PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "IBAN_CODE",
           "ORGANIZATION"}

_CFG = replace(DEFAULT_CONFIG, suppress_letterless_detections=True,
               suppress_ner_with_digits=True)


def _load(timeout: int = 30):
    if _CACHE.exists():
        return json.loads(_CACHE.read_text(encoding="utf-8"))
    req = urllib.request.Request(_URL, headers={"User-Agent": "obsify-eval"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8")
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE.write_text(raw, encoding="utf-8")
    return json.loads(raw)


def _detect_spans(analyzer, text: str):
    """Return obsify detections as (start, end) offset pairs into `text`."""
    results = analyzer.analyze(text=text, language="en",
                               entities=list(_CFG.entities_of_interest),
                               score_threshold=_CFG.presidio_score_threshold)
    results = _post_recognize_filter(results, text, _CFG)
    return [(r.start, r.end) for r in results]


def run(sample: int) -> dict:
    data = _load()
    analyzer = build_analyzer(_CFG)
    caught: dict[str, int] = defaultdict(int)
    total: dict[str, int] = defaultdict(int)

    for rec in data[:sample]:
        text = rec["full_text"]
        det = _detect_spans(analyzer, text)
        for sp in rec.get("spans", []):
            gt_type = sp.get("entity_type")
            if gt_type not in _MAPPED:
                continue
            total[gt_type] += 1
            gs, ge = sp["start_position"], sp["end_position"]
            # masking view: caught if any detection overlaps the GT span
            if any(ds < ge and gs < de for ds, de in det):
                caught[gt_type] += 1

    per_type = {t: {"caught": caught[t], "total": total[t],
                    "recall": round(caught[t] / total[t], 3) if total[t] else 0.0}
                for t in sorted(total)}
    tot_c, tot_t = sum(caught.values()), sum(total.values())
    return {"sample": min(sample, len(data)), "records_available": len(data),
            "per_type": per_type,
            "overall_recall": round(tot_c / tot_t, 3) if tot_t else 0.0,
            "caught": tot_c, "total": tot_t}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python eval/bench_external.py",
                                 description="Cross-check obsify recall vs presidio-research.")
    ap.add_argument("--sample", type=int, default=300, help="records to score (default 300)")
    args = ap.parse_args(argv)

    try:
        res = run(args.sample)
    except Exception as exc:  # network or parse failure -> documented, non-fatal
        print(f"[bench] could not run ({type(exc).__name__}: {exc}).")
        print(f"[bench] fetch {_URL} to {_CACHE} manually, then re-run offline.")
        return 0

    print(f"[bench] presidio-research synth_dataset_v2 — scored {res['sample']} of "
          f"{res['records_available']} records (RECALL only; generic types; in-family).")
    print(f"[bench] overall recall: {res['overall_recall']:.1%} "
          f"({res['caught']}/{res['total']})")
    for t, s in res["per_type"].items():
        print(f"   {t:16} {s['recall']:.1%}  ({s['caught']}/{s['total']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
