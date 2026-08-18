"""Custom Presidio recognizers for configuration B (Australian financial PII).

These are added on top of the Presidio baseline. Each is deliberately narrow and
deterministic:

* ABN / ACN / TFN — a permissive digit-group regex proposes candidates; the
  official checksum (obsify.checksums) then confirms or rejects each one. Presidio's
  contract is: validate_result() -> True promotes the match to full confidence,
  False drops it entirely. So a random 11-digit string is never reported as an
  ABN — only a checksum-valid one is. This keeps false positives near zero for
  the structured identifiers.

* Account numbers — validity is *contextual*: a 6-10 digit run only counts when
  it sits next to a BSB (XXX-XXX). That can't be decided from the matched span
  alone, so this is a full EntityRecognizer that inspects the surrounding text.

* Engagement codes — a placeholder pattern; the regex lives in obsify.config so it
  can be retuned per firm without touching this file.
"""

from __future__ import annotations

import re

from presidio_analyzer import EntityRecognizer, Pattern, PatternRecognizer, RecognizerResult

from obsify.checksums import is_valid_abn, is_valid_acn, is_valid_medicare, is_valid_tfn
from obsify.config import Config


class AbnRecognizer(PatternRecognizer):
    """Australian Business Number — 11 digits, ATO modulus-89 checksum-validated."""

    def __init__(self) -> None:
        patterns = [Pattern("ABN (11 digits)", r"\b\d{2}\s?\d{3}\s?\d{3}\s?\d{3}\b", 0.3)]
        super().__init__(supported_entity="AU_ABN", patterns=patterns,
                         context=["abn", "australian business number"])

    def validate_result(self, pattern_text: str):
        return is_valid_abn(pattern_text)


class AcnRecognizer(PatternRecognizer):
    """Australian Company Number — 9 digits, ASIC check-digit validated."""

    def __init__(self) -> None:
        patterns = [Pattern("ACN (9 digits)", r"\b\d{3}\s?\d{3}\s?\d{3}\b", 0.3)]
        super().__init__(supported_entity="AU_ACN", patterns=patterns,
                         context=["acn", "australian company number"])

    def validate_result(self, pattern_text: str):
        return is_valid_acn(pattern_text)


class TfnRecognizer(PatternRecognizer):
    """Tax File Number — 8 or 9 digits, ATO weighted modulus-11 validated."""

    def __init__(self) -> None:
        patterns = [Pattern("TFN (8-9 digits)", r"\b\d{3}\s?\d{3}\s?\d{2,3}\b", 0.3)]
        super().__init__(supported_entity="AU_TFN", patterns=patterns,
                         context=["tfn", "tax file number"])

    def validate_result(self, pattern_text: str):
        return is_valid_tfn(pattern_text)


class MedicareRecognizer(PatternRecognizer):
    """Australian Medicare card number — 10-11 digits, weighted-modulus-10 checksum."""

    def __init__(self) -> None:
        patterns = [Pattern("Medicare (10-11 digits)",
                            r"\b\d{4}\s?\d{5}\s?\d{1,2}\b", 0.3)]
        super().__init__(supported_entity="MEDICARE", patterns=patterns,
                         context=["medicare"])

    def validate_result(self, pattern_text: str):
        return is_valid_medicare(pattern_text)


class DateOfBirthRecognizer(PatternRecognizer):
    """A date treated as a date of birth — only when a DOB label word is nearby.
    The context requirement is enforced in the post-filter (require_context), so a
    plain calendar date is not swept up as PII."""

    def __init__(self) -> None:
        # Score above the analyze threshold (0.4) so the candidate survives to the
        # post-filter, where require-context (DOB label word nearby) enforces precision
        # — a plain calendar date with no DOB label is dropped there, not here.
        patterns = [
            Pattern("DOB numeric", r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b", 0.5),
            Pattern("DOB written",
                    r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
                    r"[a-z]*\.?\s+\d{4}\b", 0.5),
        ]
        super().__init__(supported_entity="DATE_OF_BIRTH", patterns=patterns,
                         context=["date of birth", "dob", "d.o.b", "born"])


class AuPassportRecognizer(PatternRecognizer):
    """Australian passport — 1-2 letters followed by 7 digits. There is no public
    checksum, so precision comes from require-context ('passport' nearby); a bare
    letter+digits token elsewhere is dropped in the post-filter."""

    def __init__(self) -> None:
        patterns = [Pattern("AU passport", r"\b[A-Za-z]{1,2}\d{7}\b", 0.5)]
        super().__init__(supported_entity="AU_PASSPORT", patterns=patterns,
                         context=["passport"])


class AuDriverLicenceRecognizer(PatternRecognizer):
    """Australian driver licence. Formats vary by state (6-10 alphanumeric, at least
    one digit) and there is no national checksum, so this is context-gated (a
    'licence'/'driver' word must be nearby) to avoid flagging arbitrary codes."""

    def __init__(self) -> None:
        patterns = [Pattern("AU driver licence",
                            r"\b(?=[A-Za-z0-9]*\d)[A-Za-z0-9]{6,10}\b", 0.5)]
        super().__init__(supported_entity="AU_DRIVER_LICENCE", patterns=patterns,
                         context=["licence", "license", "driver"])


class EngagementCodeRecognizer(PatternRecognizer):
    """Engagement codes. OPERATOR-TUNABLE: the pattern is supplied from Config so
    it can be retuned against real codes without editing this module."""

    def __init__(self, pattern: str) -> None:
        patterns = [Pattern("Engagement code (operator-tunable)", pattern, 0.6)]
        super().__init__(supported_entity="ENGAGEMENT_CODE", patterns=patterns,
                         context=["engagement", "reference", "ref"])


class BsbAdjacentAccountRecognizer(EntityRecognizer):
    """Account numbers defined by *context*: a 6-10 digit run adjacent to a BSB.

    A bare integer is not PII; a bank account number is. The BSB (XXX-XXX) next to
    it is the signal that promotes an otherwise-ambiguous digit run to an account
    number. Adjacency is measured in characters between the two spans and is
    configurable (Config.bsb_account_adjacency_chars).
    """

    ENTITY = "AU_BANK_ACCOUNT"

    def __init__(self, config: Config) -> None:
        super().__init__(supported_entities=[self.ENTITY], name="BsbAdjacentAccountRecognizer")
        self._bsb = re.compile(config.bsb_pattern)
        self._acct = re.compile(config.account_number_pattern)
        self._max_gap = config.bsb_account_adjacency_chars
        self._min_digits = config.account_digits_min
        self._max_digits = config.account_digits_max

    def load(self) -> None:  # required by EntityRecognizer, nothing to load
        return None

    @staticmethod
    def _overlaps(a_start: int, a_end: int, spans) -> bool:
        return any(not (a_end <= s or a_start >= e) for s, e in spans)

    def analyze(self, text: str, entities, nlp_artifacts=None):
        if self.ENTITY not in entities:
            return []
        bsb_spans = [m.span() for m in self._bsb.finditer(text)]
        if not bsb_spans:
            return []
        results = []
        for m in self._acct.finditer(text):
            a_start, a_end = m.span()
            # Count digits after removing single-space/hyphen separators.
            n_digits = sum(c.isdigit() for c in m.group())
            if not (self._min_digits <= n_digits <= self._max_digits):
                continue
            # Never flag the BSB itself (e.g. "062-000" is 6 digits but is the BSB).
            if self._overlaps(a_start, a_end, bsb_spans):
                continue
            # Require adjacency to a BSB (0 if overlapping/adjacent).
            near = any(
                min(abs(a_start - b_end), abs(b_start - a_end)) <= self._max_gap
                for b_start, b_end in bsb_spans
            )
            if near:
                results.append(RecognizerResult(
                    entity_type=self.ENTITY, start=a_start, end=a_end, score=0.85,
                ))
        return results


class AuAddressRecognizer(EntityRecognizer):
    """Australian street addresses.

    Anchored on a street line (optional unit/level prefix, a street number, a
    street name, and a street-type from a fixed dictionary), then extended to any
    trailing suburb / state / postcode. A *full* address needs street plus a
    suburb-or-postcode; a bare street line will be a shorter span and therefore
    score as partial under the existing containment scoring. When a state
    abbreviation is present, the 4-digit postcode is validated against that
    state's ranges; an inconsistent postcode is dropped from the span rather than
    trusted.
    """

    ENTITY = "AU_ADDRESS"

    _STREET_TYPES = ("Street", "St", "Road", "Rd", "Avenue", "Ave", "Crescent",
                     "Cres", "Drive", "Dr", "Court", "Ct", "Place", "Pl", "Lane",
                     "Ln", "Highway", "Hwy", "Boulevard", "Blvd", "Parade", "Pde")

    _STATE_RANGES = {
        "NSW": [(1000, 2599), (2619, 2899), (2921, 2999)],
        "ACT": [(200, 299), (2600, 2618), (2900, 2920)],
        "VIC": [(3000, 3999), (8000, 8999)],
        "QLD": [(4000, 4999), (9000, 9999)],
        "SA": [(5000, 5799), (5800, 5999)],
        "WA": [(6000, 6797), (6800, 6999)],
        "TAS": [(7000, 7799), (7800, 7999)],
        "NT": [(800, 899), (900, 999)],
    }

    def __init__(self) -> None:
        super().__init__(supported_entities=[self.ENTITY], name="AuAddressRecognizer")
        types = "|".join(sorted(self._STREET_TYPES, key=len, reverse=True))
        unit = r"(?:(?:Unit|Suite|Level|L|U)\.?\s*\d+[A-Za-z]?\s*[,/]?\s*)?"
        # street: optional unit + number + 1-3 name words + street type
        self._street = re.compile(
            rf"{unit}\d+[A-Za-z]?\s+(?:[A-Z][A-Za-z'.-]+\s+){{1,3}}(?:{types})\b\.?"
        )
        states = "|".join(self._STATE_RANGES)
        # trailing suburb / state / postcode immediately after a street. Suburb
        # tokens are Title-case ([A-Z][a-z]...) so they cannot swallow an all-caps
        # state abbreviation, which would otherwise skip postcode validation.
        self._trail = re.compile(
            rf"\s*,?\s*(?P<suburb>(?:[A-Z][a-z][A-Za-z'.-]*)(?:\s+[A-Z][a-z][A-Za-z'.-]*){{0,2}})?"
            rf"\s*,?\s*(?P<state>{states})?\s*(?P<postcode>\d{{4}})?"
        )

    def load(self) -> None:
        return None

    def _postcode_ok(self, state: str, postcode: str) -> bool:
        try:
            pc = int(postcode)
        except ValueError:
            return False
        return any(lo <= pc <= hi for lo, hi in self._STATE_RANGES.get(state, []))

    def analyze(self, text: str, entities, nlp_artifacts=None):
        if self.ENTITY not in entities:
            return []
        results = []
        for m in self._street.finditer(text):
            start, end = m.span()
            tm = self._trail.match(text, end)
            has_suffix_component = False
            if tm:
                suburb, state, postcode = tm.group("suburb"), tm.group("state"), tm.group("postcode")
                # If a state and postcode both appear but disagree, don't trust the
                # postcode: end the span before it.
                if postcode and state and not self._postcode_ok(state, postcode):
                    trimmed_end = tm.start("postcode")
                    end = max(end, trimmed_end)
                    has_suffix_component = bool(suburb or state)
                elif suburb or state or postcode:
                    end = tm.end()
                    has_suffix_component = True
            score = 0.85 if has_suffix_component else 0.4
            results.append(RecognizerResult(
                entity_type=self.ENTITY, start=start, end=end, score=score,
            ))
        return results


def build_custom_recognizers(config: Config) -> list[EntityRecognizer]:
    """The full set of configuration-B custom recognizers."""
    return [
        AbnRecognizer(),
        AcnRecognizer(),
        TfnRecognizer(),
        MedicareRecognizer(),
        DateOfBirthRecognizer(),
        AuPassportRecognizer(),
        AuDriverLicenceRecognizer(),
        EngagementCodeRecognizer(config.engagement_code_pattern),
        BsbAdjacentAccountRecognizer(config),
        AuAddressRecognizer(),
    ]
