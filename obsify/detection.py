"""Detection: Presidio analysis + the deterministic precision filter.

`_post_recognize_filter` is the precision pass that suppresses the numeric-ledger
false positives a model would otherwise flood — bare numbers that coincidentally pass
a checksum, amounts flagged as phones, alnum codes flagged as names — while keeping
validated PII (context-labelled IDs, Luhn cards, valid IPs, real phones).

`_analyze` runs the analyzer per `Segment` (so each hit keeps its source locator) and
applies that filter, returning located `Detection`s — used by the eval scorer. The MCP
server applies `_post_recognize_filter` directly to raw strings instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from obsify.config import Config
from obsify.extraction import Segment

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
    entity_type: str
    text: str            # the detected span
    locator: str
    score: float


_NER_TYPES = ("PERSON", "ORGANIZATION", "LOCATION")


def _post_recognize_filter(results, seg_text: str, config: Config):
    """Deterministic precision filter over one segment's detections.

    Kills the false positives that flood real numeric ledgers, without a model:
      A. structured IDs (AU_ABN/ACN/TFN/Medicare/DOB/passport/licence) require a
         label word in the segment — a bare number coincidentally passing a checksum
         is dropped;
      B. (detect-mode) letterless spans (numbers/amounts/dates) are dropped unless
         they are a context-validated ID, a BSB-adjacent account, a Luhn card, a
         valid IP, or a real phone (context or phone shape);
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
            # bare numbers: context-gated IDs, BSB-adjacent accounts, Luhn cards, and
            # valid IPs. Phones survive only with context or a strong phone shape.
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


def _analyze(analyzer, segments: list[Segment], config: Config) -> list[Detection]:
    """Analyze each segment and return located Detections (post precision filter)."""
    detections: list[Detection] = []
    entities = list(config.entities_of_interest)
    for seg in segments:
        results = analyzer.analyze(
            text=seg.text,
            language="en",
            entities=entities,
            score_threshold=config.presidio_score_threshold,
        )
        for r in _post_recognize_filter(results, seg.text, config):
            detections.append(Detection(
                document=seg.document,
                entity_type=r.entity_type,
                text=seg.text[r.start:r.end],
                locator=seg.locator,
                score=float(r.score),
            ))
    return detections
