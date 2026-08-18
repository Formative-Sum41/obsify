"""Variant expansion for the client master-list differential check.

Two tiers, kept strictly separate because they carry different trust:

* **Full tier** — exact or *suffix-normalized* equality. A dictionary of
  legal-entity abbreviations (Pty Ltd / P/L / PL / Proprietary Limited, Holdings /
  Hldgs, Nominees / Noms, Limited / Ltd, Australia / Aust / AU) is folded to
  canonical markers on both the master entry and the extracted text; if the
  canonical master string appears (token-aligned) in the canonical text, it is a
  full catch — as trustworthy as an exact literal match.

* **Fuzzy tier** — the master's *distinctive* tokens (its name words, with legal
  suffix tokens dropped) appear in sequence within a short window, matching by
  equality or abbreviation prefix (so "NOM" matches "Nominees"). Fuzzy hits are
  advisory only: they go to a separate "fuzzy — operator review" column and are
  NEVER counted as catches, because prefix/window matching can over-reach.

The split is deliberate: a dictionary abbreviation ("Hldgs") is safe to auto-count;
an ad-hoc truncation ("NOM") should be a human's call.
"""

from __future__ import annotations

import re

from obsify.extraction import normalize_ws

# --- suffix-normalization dictionary (full tier) -----------------------------
# Ordered: multi-word / more-specific forms first so they consume before the
# standalone fallbacks. Each ABBREVIATION folds to its canonical WORD; the
# canonical word itself is left untouched (no self-referential rule), so a marker
# can never be re-matched by a later rule. "pty ltd" collapses to the single
# token "ptyltd" so a following standalone-ltd rule cannot split it.
_SUFFIX_SUBS: tuple[tuple[str, str], ...] = (
    (r"\bproprietary\s+limited\b", " ptyltd "),
    (r"\bpty\.?\s*/?\s*ltd\.?\b", " ptyltd "),   # pty ltd, pty. ltd., pty/ltd
    (r"\bpty\s+limited\b", " ptyltd "),
    (r"\bp\s*/\s*l\b", " ptyltd "),               # p/l, p / l
    (r"\bpty\.?\b", " ptyltd "),                  # standalone pty
    (r"\bpl\b", " ptyltd "),                      # standalone PL
    (r"\bhldgs?\b", " holdings "),                # hldg, hldgs -> holdings
    (r"\bnoms\b", " nominees "),                  # NOTE: 'nom' (no s) is fuzzy-only
    (r"\blimited\b", " ltd "),                    # standalone limited -> ltd
    (r"\bltd\.?\b", " ltd "),                     # normalise 'ltd.' -> 'ltd'
    (r"\baust\.?\b", " australia "),
    (r"\bau\b", " australia "),
)

# Tokens treated as legal-entity suffixes and dropped when computing the
# distinctive tokens used by the fuzzy pass (raw tokens, not canonical).
_LEGAL_SUFFIX_TOKENS = {
    "pty", "ltd", "p/l", "pl", "proprietary", "limited", "co", "inc",
}

_MIN_PREFIX = 3          # shortest abbreviation prefix that may fuzzy-match
_FUZZY_WINDOW_SLACK = 2  # extra tokens allowed between first & last matched token


def canonicalize(text: str) -> str:
    """Casefold, collapse whitespace, and fold legal-suffix variants to markers."""
    t = " " + normalize_ws(text).casefold() + " "
    for pattern, repl in _SUFFIX_SUBS:
        t = re.sub(pattern, repl, t)
    return normalize_ws(t)


def distinctive_tokens(name: str) -> list[str]:
    """The master entry's name tokens, with legal-suffix tokens removed."""
    toks = normalize_ws(name).casefold().split(" ")
    return [t for t in toks if t and t not in _LEGAL_SUFFIX_TOKENS]


def full_match(master: str, segment_text: str) -> bool:
    """Exact or suffix-normalized containment of `master` within `segment_text`."""
    cm = canonicalize(master)
    cs = canonicalize(segment_text)
    if not cm:
        return False
    # Pad with spaces so containment is token-aligned (no partial-token matches).
    return f" {cm} " in f" {cs} "


def _prefix_match(seg_tok: str, master_tok: str) -> bool:
    if seg_tok == master_tok:
        return True
    short, long = sorted((seg_tok, master_tok), key=len)
    return len(short) >= _MIN_PREFIX and long.startswith(short)


def fuzzy_match(master: str, segment_text: str) -> bool:
    """True if the master's distinctive tokens appear in sequence within a short
    window of the segment, matching by equality or abbreviation prefix.

    Requires >= 2 distinctive tokens (single-token names rely on the full tier,
    to avoid noisy one-word coincidences)."""
    distinctive = distinctive_tokens(master)
    if len(distinctive) < 2:
        return False
    seg_tokens = normalize_ws(segment_text).casefold().split(" ")

    # Greedy in-order scan: find each distinctive token after the previous match.
    start = 0
    while start < len(seg_tokens):
        idx = start
        first = last = None
        d = 0
        j = idx
        while d < len(distinctive) and j < len(seg_tokens):
            if _prefix_match(seg_tokens[j], distinctive[d]):
                if first is None:
                    first = j
                last = j
                d += 1
            j += 1
        if d == len(distinctive) and first is not None:
            window = last - first + 1
            if window <= len(distinctive) + _FUZZY_WINDOW_SLACK:
                return True
        start += 1
    return False
