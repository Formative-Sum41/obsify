"""The three detection configurations, run per document.

A — Baseline:             Presidio out of the box (en_core_web_lg).
B — Baseline + custom:    A plus the Australian recognizers (ABN/ACN/TFN/account/
                          engagement).
C — B + differential:     B plus a case-insensitive literal check of every client
                          master-list line against the extracted text. A client
                          name found by the differential that B did not already
                          flag is recorded as caught-by-differential-only.

Detection runs per Segment so each hit keeps the precise source locator, and so a
value split across a line break is matched inside its (whitespace-normalized)
segment. Configuration C is a strict superset of B; A and B are independent
analyzer passes over the same segments.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from obsify.config import Config
from obsify.extraction import Segment, normalize_ws
from obsify.nlp import build_analyzers
from obsify.variants import full_match, fuzzy_match

# Letterless PHONE_NUMBER survives suppression only with phone context nearby or a
# strong phone shape (leading +country, (area), 0x trunk, or 13/1800). A decimal
# point marks an amount, never a phone.
_PHONE_CTX = ("phone", "mobile", "mob", "telephone", "tel", "fax", "call",
              "contact", "cell")
_PHONE_SHAPE = re.compile(r"^\s*(?:\+\d|\(\d{2,3}\)|0[2-478]|1[38]00)")


def _phone_survives(span: str, low_seg: str) -> bool:
    if "." in span:                       # a decimal point marks an amount
        return False
    if any(w in low_seg for w in _PHONE_CTX):
        return True
    if _PHONE_SHAPE.match(span):          # AU-strong prefix (+country, (area), 0x, 13/1800)
        return True
    # separator-grouped run of phone length (handles international formats a bare
    # ledger ID never has — IDs are contiguous digits, phones are grouped).
    compact = re.sub(r"[\s()\-+]", "", span)
    return compact.isdigit() and 7 <= len(compact) <= 15 and bool(re.search(r"[\s()\-]", span))


@dataclass(frozen=True)
class Detection:
    document: str
    config: str          # "A", "B", or "C"
    entity_type: str
    text: str            # the detected span (or master-list line for differential)
    locator: str
    score: float
    # Differential tier: "" for a Presidio detection; "full" for an exact or
    # suffix-normalized master-list hit (counts as a catch); "fuzzy" for a
    # token-fuzzy hit (advisory only — operator review, never auto-counted).
    differential_tier: str = ""
    differential_only: bool = False       # full-tier hit B did not already flag
    ocr_derived: bool = False             # from an OCR'd page (lower trust, reported apart)
    provenance: str = ""                  # e.g. "context-required" — why it survived the filter


_NER_TYPES = ("PERSON", "ORGANIZATION", "LOCATION")


def _post_recognize_filter(results, seg_text: str, config: Config):
    """Deterministic precision filter over one segment's detections.

    Kills the false positives that flood real numeric ledgers, without a model:
      A. structured IDs (AU_ABN/ACN/TFN) require a label word in the segment — a
         bare number coincidentally passing a checksum is dropped;
      B. (detect-mode) letterless spans (numbers/amounts/dates) are dropped unless
         they are a context-validated ID or a BSB-adjacent account;
      C. (detect-mode) NER names containing a digit (journal codes like EP180102)
         are dropped — real person/org/location names carry no digits.
    """
    low = seg_text.casefold()
    kept = []
    for r in results:
        et = r.entity_type
        span = seg_text[r.start:r.end]
        if et in config.require_context_for_entities:
            if not any(w in low for w in config.id_context_words.get(et, ())):
                continue
        if config.suppress_letterless_detections and not any(c.isalpha() for c in span):
            # Exempt types that are checksum/format-validated rather than coincidental
            # bare numbers: context-gated IDs (ABN/ACN/TFN/Medicare/DOB), BSB-adjacent
            # accounts, Luhn cards, and valid IPs. Phones survive only with context or a
            # strong phone shape. Letterless suppression targets numeric NOISE, not
            # validated PII.
            exempt = (et in config.require_context_for_entities
                      or et in ("AU_BANK_ACCOUNT", "CREDIT_CARD", "IP_ADDRESS"))
            if et == "PHONE_NUMBER" and not exempt:
                exempt = _phone_survives(span, low)
            if not exempt:
                continue
        if config.suppress_ner_with_digits and et in _NER_TYPES and any(c.isdigit() for c in span):
            continue
        kept.append(r)
    return kept


def _analyze(analyzer, segments: list[Segment], config: Config, label: str,
             ocr: bool = False) -> list[Detection]:
    detections: list[Detection] = []
    entities = list(config.entities_of_interest)
    for seg in segments:
        results = analyzer.analyze(
            text=seg.text,
            language="en",
            entities=entities,
            score_threshold=config.presidio_score_threshold,
        )
        results = _post_recognize_filter(results, seg.text, config)
        for r in results:
            prov = "context-required" if r.entity_type in config.require_context_for_entities else ""
            detections.append(Detection(
                document=seg.document,
                config=label,
                entity_type=r.entity_type,
                text=seg.text[r.start:r.end],
                locator=seg.locator,
                score=float(r.score),
                ocr_derived=ocr,
                provenance=prov,
            ))
    return detections


def _differential(segments: list[Segment], master_list: list[str],
                  b_detections: list[Detection]) -> list[Detection]:
    """Match each master-list line against each segment via the variant expander.

    Two tiers (obsify.variants): a *full* hit is an exact or suffix-normalized match
    (counts as a catch); a *fuzzy* hit is a token-fuzzy resemblance (advisory,
    operator review only). Whether a full hit is 'differential-only' is decided by
    asking if configuration B already flagged the same client name in that document.
    """
    # Pre-index B's detected texts per document for the "already flagged?" test.
    b_by_doc: dict[str, list[str]] = {}
    for d in b_detections:
        b_by_doc.setdefault(d.document, []).append(normalize_ws(d.text).casefold())

    detections: list[Detection] = []
    for line in master_list:
        needle = normalize_ws(line).casefold()
        if not needle:
            continue
        for seg in segments:
            if full_match(line, seg.text):
                already = any(needle in bt or bt in needle
                              for bt in b_by_doc.get(seg.document, []))
                detections.append(Detection(
                    document=seg.document, config="C", entity_type="CLIENT_NAME",
                    text=line, locator=seg.locator, score=1.0,
                    differential_tier="full", differential_only=not already,
                ))
            elif fuzzy_match(line, seg.text):
                detections.append(Detection(
                    document=seg.document, config="C", entity_type="CLIENT_NAME",
                    text=line, locator=seg.locator, score=0.5,
                    differential_tier="fuzzy",
                ))
    return detections


@dataclass
class DetectionOutput:
    by_config: dict[str, list[Detection]]  # "A" -> [...], "B" -> [...], "C" -> [...]
    differential_only_count: int
    ocr_detections: list[Detection] = field(default_factory=list)


def _dedupe(detections: list[Detection]) -> list[Detection]:
    """Collapse detections of the same value/type/tier within a document to one.

    The same span is seen in a line segment and again in the page-level block; a
    value can also legitimately recur. For counting (catches, false positives)
    each distinct (document, entity_type, normalized text, tier) is one finding.
    The first occurrence's locator is kept (line locators sort before the block).
    """
    seen: set[tuple[str, str, str, str]] = set()
    out: list[Detection] = []
    for d in detections:
        key = (d.document, d.entity_type, normalize_ws(d.text).casefold(), d.differential_tier)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def run_all_configs(segments: list[Segment], config: Config,
                    master_list: list[str] | None,
                    ocr_segments: list[Segment] | None = None) -> DetectionOutput:
    baseline_analyzer, custom_analyzer = build_analyzers(config)

    a = _dedupe(_analyze(baseline_analyzer, segments, config, "A"))
    b = _dedupe(_analyze(custom_analyzer, segments, config, "B"))

    # Config C = B's detections (relabelled) + differential hits.
    c: list[Detection] = [
        Detection(d.document, "C", d.entity_type, d.text, d.locator, d.score)
        for d in b
    ]
    diff_only_count = 0
    if master_list:
        diff = _dedupe(_differential(segments, master_list, b))
        c.extend(diff)
        # Count distinct full-tier client names B did not already flag.
        for d in diff:
            if d.differential_tier == "full" and d.differential_only:
                diff_only_count += 1

    # OCR-derived detections (from --ocr on low-coverage pages) are collected
    # separately and NOT folded into A/B/C scoring: OCR is lower trust and the
    # page stays gated. They are reported apart, using the full custom recognizer
    # set so the reviewer sees the strongest available read of the scanned page.
    ocr_detections: list[Detection] = []
    if ocr_segments:
        ocr_detections = _dedupe(_analyze(custom_analyzer, ocr_segments, config, "OCR", ocr=True))

    return DetectionOutput(
        by_config={"A": a, "B": b, "C": c},
        differential_only_count=diff_only_count,
        ocr_detections=ocr_detections,
    )
