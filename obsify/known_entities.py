"""Known-entity matching — deterministically find a caller-supplied list of sensitive
names, including suffix/abbreviation variants that NER misses.

When you can enumerate the entities to hide (a per-engagement list of client and
personnel names), a dictionary match gives 100% coverage of those known names and their
common variants — complementing Presidio's probabilistic NER, which has imperfect recall
on names, especially abbreviated forms ("BRIGHTWATER HLDGS P/L" for "Brightwater Holdings
Pty Ltd").

PRIVACY — the list of names is itself sensitive substance, so it never enters the model's
context: it lives in a LOCAL `.obsify.entities` file, read only by local code and passed
to the tools by PATH (or auto-discovered), never as a value. `scan_pii` reports
KNOWN_ENTITY by type/location only; `redact_text` masks it. This module is Presidio-free
and returns character spans; the MCP layer wraps them as detections.

Matching tiers:
  * default    — core name tokens (with dictionary abbreviations: Holdings/Hldgs,
                 Nominees/Noms, …) matched contiguously, with an optional trailing legal
                 suffix (Pty Ltd / P/L / …). High precision.
  * fuzzy=True — the same, but tolerating up to two filler tokens between core tokens.
                 May over-mask; opt-in for "when in doubt, redact."
"""

from __future__ import annotations

import re
from pathlib import Path

ENTITY = "KNOWN_ENTITY"
ENTITIES_FILENAME = ".obsify.entities"

# Abbreviation variants for common name tokens (mirrors variants._SUFFIX_SUBS).
_TOKEN_VARIANTS = {
    "holdings": ("holdings", "hldgs", "hldg"),
    "nominees": ("nominees", "noms", "nom"),
    "australia": ("australia", "aust", "au"),
    "company": ("company", "co"),
    "incorporated": ("incorporated", "inc"),
    "corporation": ("corporation", "corp"),
    "international": ("international", "intl"),
}
# Trailing legal-suffix surface forms, matched as an optional group.
_LEGAL_SUFFIX_RE = (r"(?:pty\.?\s*/?\s*ltd\.?|proprietary\s+limited|pty\s+limited"
                    r"|p\s*/\s*l|pty\.?|ltd\.?|limited|llc|inc\.?|co\.?)")
_LEGAL_SUFFIX_TOKENS = {"pty", "ltd", "limited", "proprietary", "pl",
                        "co", "inc", "llc", "corp"}
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def load_entities(path: str) -> list[str]:
    """Read names from an `.obsify.entities` file (one per line; `#` comments; blank
    lines ignored). The names are returned to local code only — never surfaced."""
    names: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.append(line)
    return names


def discover(near: str | None) -> str | None:
    """Find the nearest `.obsify.entities`, walking up from `near` (a file or dir) and
    then from cwd. Returns its path, or None."""
    starts: list[Path] = []
    if near:
        p = Path(near)
        starts.append(p if p.is_dir() else p.parent)
    starts.append(Path.cwd())
    for start in starts:
        for base in (start, *start.parents):
            f = base / ENTITIES_FILENAME
            if f.exists():
                return str(f)
    return None


def _name_to_regex(name: str, fuzzy: bool) -> str | None:
    toks = [t.lower() for t in _WORD.findall(name)]
    core = list(toks)
    while core and core[-1] in _LEGAL_SUFFIX_TOKENS:   # strip trailing legal suffix
        core.pop()
    if not core:
        return None
    parts = ["(?:" + "|".join(_TOKEN_VARIANTS.get(t, (re.escape(t),))) + ")" for t in core]
    gap = r"(?:\W+\w+){0,2}\W+" if fuzzy else r"\W+"
    body = gap.join(parts)
    return r"\b" + body + r"(?:\W+" + _LEGAL_SUFFIX_RE + r")?"


def compile_matchers(names: list[str], fuzzy: bool = False) -> list[re.Pattern]:
    matchers: list[re.Pattern] = []
    for n in names:
        rx = _name_to_regex(n, fuzzy)
        if rx:
            matchers.append(re.compile(rx, re.IGNORECASE))
    return matchers


def find_known(text: str, matchers: list[re.Pattern]) -> list[tuple[int, int]]:
    """Return non-overlapping (start, end) character spans of known-entity matches,
    longest-match-wins where matches overlap."""
    raw: list[tuple[int, int]] = []
    for rx in matchers:
        for m in rx.finditer(text):
            if m.group().strip():
                raw.append((m.start(), m.end()))
    # keep non-overlapping spans, preferring the longest at each position
    raw.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    spans: list[tuple[int, int]] = []
    last_end = -1
    for s, e in raw:
        if s >= last_end:
            spans.append((s, e))
            last_end = e
    return spans
