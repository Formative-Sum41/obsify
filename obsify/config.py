"""Detection configuration.

Everything tunable lives here as data: the entity types obsify detects, the custom
recognizer patterns, the precision-filter switches, and the context words that gate
identifier detection. `DEFAULT_CONFIG` is the recall-oriented default; the MCP server
enables the precision suppressors on top of it (see obsify.mcp_server).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    # --- OPERATOR-TUNABLE -----------------------------------------------------
    # Engagement/matter codes are a placeholder pattern. Real codes vary by firm and
    # system; review and tune this regex against a sample of real codes before
    # trusting engagement-code recall.
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

    # --- precision controls ---------------------------------------------------
    # On real numeric ledgers, bare numbers coincidentally pass ID checksums
    # (a sequential journal ref passes the 8-digit TFN check ~9% of the time) and
    # NER flags codes/amounts/dates. These deterministic post-filters cut that
    # noise without a model. Applied in obsify/detection._post_recognize_filter.
    #
    # require_context: these identifier types are only accepted when a label word
    # (id_context_words) appears in the same segment — a bare number is dropped.
    # A labelled ID in prose still passes.
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
    # amounts, dates) EXCEPT validated PII (context IDs, BSB-adjacent accounts, Luhn
    # cards, valid IPs, real phones — see detection._post_recognize_filter).
    # suppress_ner_with_digits: drop PERSON/ORGANIZATION/LOCATION whose span holds
    # a digit (journal codes like EP180102) — real names carry no digits.
    # Both default OFF (recall mode); the MCP server enables them (detect mode).
    suppress_letterless_detections: bool = False
    suppress_ner_with_digits: bool = False

    # The entity types obsify detects, passed to Presidio's analyze() to restrict
    # output. ORGANIZATION is INCLUDED: spaCy tags company names ("X Pty Ltd") as
    # ORGANIZATION, so it carries real recall on entity names — at a visible
    # precision cost (incidental org mentions get flagged), the tradeoff documented
    # in eval/. DATE_TIME and URL are excluded as low-value noise (DATE_OF_BIRTH is
    # a separate context-gated recognizer). Widen or narrow this set as needed.
    entities_of_interest: tuple[str, ...] = field(
        default_factory=lambda: (
            # Presidio baseline recognizers
            "PERSON",
            "ORGANIZATION",
            "EMAIL_ADDRESS",
            "PHONE_NUMBER",
            "LOCATION",
            "CREDIT_CARD",
            "IBAN_CODE",
            "IP_ADDRESS",
            # obsify's custom Australian recognizers
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
        )
    )


DEFAULT_CONFIG = Config()
