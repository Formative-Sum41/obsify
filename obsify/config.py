"""Harness configuration.

Everything an operator might tune lives here as data, so a run is fully described
by this object plus the CLI arguments. `config_hash()` produces a short stable
digest recorded in every report and run-log line, so any result can be tied back
to the exact configuration that produced it (audit trail is the product).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Config:
    # --- OPERATOR-TUNABLE -----------------------------------------------------
    # Engagement/matter codes are a placeholder pattern. Real codes vary by firm and
    # system; the operator MUST review and tune this regex against a sample of real
    # codes before trusting configuration B/C recall for engagement codes.
    # Format as shipped: 2-4 uppercase letters, a hyphen, then 4-8 digits.
    engagement_code_pattern: str = r"\b[A-Z]{2,4}-\d{4,8}\b"

    # BSB is the Australian bank-branch code, printed as XXX-XXX (6 digits).
    # Account numbers are 6-10 digit runs that appear *adjacent* to a BSB; the
    # adjacency is what distinguishes an account number from an arbitrary integer.
    bsb_pattern: str = r"\b\d{3}-\d{3}\b"
    # Account numbers may be written as digit groups separated by single spaces or
    # hyphens (e.g. "1084 2217", "55 908 3312"). This pattern captures the whole
    # grouped run; the recognizer then removes separators and requires 6-10 total
    # digits, and excludes any run that is itself a BSB (XXX-XXX).
    account_number_pattern: str = r"\b\d+(?:[ -]\d+)*\b"
    account_digits_min: int = 6
    account_digits_max: int = 10
    # Max characters between a BSB match and an account-number candidate for the
    # two to be treated as adjacent (covers "BSB 123-456 Acct 12345678" spacing).
    bsb_account_adjacency_chars: int = 40

    # Presidio decision threshold: detections below this confidence are dropped.
    presidio_score_threshold: float = 0.4

    # --- precision controls (Phase A) ----------------------------------------
    # On real numeric ledgers, bare numbers coincidentally pass ID checksums
    # (a sequential journal ref passes the 8-digit TFN check ~9% of the time) and
    # NER flags codes/amounts/dates. These deterministic post-filters cut that
    # noise without a model. Applied in obsify/detection._post_recognize_filter.
    #
    # require_context: these identifier types are only accepted when a label word
    # (id_context_words) appears in the same segment — a bare number is dropped.
    # ON by default (labelled IDs in prose still pass; the fixtures are labelled).
    require_context_for_entities: tuple[str, ...] = (
        "AU_ABN", "AU_ACN", "AU_TFN", "MEDICARE", "DATE_OF_BIRTH",
        "AU_PASSPORT", "AU_DRIVER_LICENCE")
    id_context_words: dict[str, tuple[str, ...]] = field(default_factory=lambda: {
        "AU_ABN": ("abn", "australian business number"),
        "AU_ACN": ("acn", "australian company number"),
        "AU_TFN": ("tfn", "tax file number"),
        "MEDICARE": ("medicare",),
        "DATE_OF_BIRTH": ("date of birth", "dob", "d.o.b", "born"),
        "AU_PASSPORT": ("passport",),
        "AU_DRIVER_LICENCE": ("licence", "license", "driver"),
    })
    # suppress_letterless: drop detections whose span has NO letter (pure numbers,
    # amounts, dates) EXCEPT context-validated IDs and BSB-adjacent accounts.
    # suppress_ner_with_digits: drop PERSON/ORGANIZATION/LOCATION whose span holds
    # a digit (journal codes like EP180102) — real names carry no digits.
    # Both default OFF (eval/recall mode) and are enabled by detect-mode.
    suppress_letterless_detections: bool = False
    suppress_ner_with_digits: bool = False

    # Entities of interest: the single set of entity types the harness *counts*
    # as a PII detection, applied uniformly across all three configurations so
    # comparisons are fair. Passed to Presidio's analyze() to restrict output.
    #
    # MEASUREMENT DECISION — ORGANIZATION is INCLUDED. spaCy tags clean client
    # names ("X Pty Ltd") as ORGANIZATION, so config A/B legitimately catch them;
    # excluding it would have zeroed out the baseline's real recall on client
    # names and manufactured apparent value for the config-C differential. It is
    # counted, and its precision cost is visible in the false-positive column
    # (every incidental org mention — an audit firm, a tax office, a bank — is
    # flagged). DATE_TIME
    # and URL remain excluded as low-value-for-this-use-case noise. All three are
    # OPERATOR-TUNABLE: widen or narrow this set as the risk team decides.
    #
    # Baseline types appear in config A; the custom AU types only appear once
    # their recognizers are added (B); CLIENT_NAME only appears via the
    # differential check (C).
    entities_of_interest: tuple[str, ...] = field(
        default_factory=lambda: (
            # Presidio baseline PII (config A onward)
            "PERSON",
            "ORGANIZATION",
            "EMAIL_ADDRESS",
            "PHONE_NUMBER",
            "LOCATION",
            "CREDIT_CARD",
            "IBAN_CODE",
            "IP_ADDRESS",
            # Custom Australian recognizers (config B onward)
            "AU_ABN",
            "AU_ACN",
            "AU_TFN",
            "AU_BANK_ACCOUNT",
            "AU_ADDRESS",
            "MEDICARE",
            "DATE_OF_BIRTH",
            "AU_PASSPORT",
            "AU_DRIVER_LICENCE",
            "ENGAGEMENT_CODE",
            # Differential master-list check (config C)
            "CLIENT_NAME",
        )
    )

    def to_dict(self) -> dict:
        return asdict(self)

    def config_hash(self) -> str:
        """Stable 12-char digest of the full configuration."""
        blob = json.dumps(self.to_dict(), sort_keys=True, default=list)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


DEFAULT_CONFIG = Config()
