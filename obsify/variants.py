"""Variant normalization for leak-checking (backs obsify.redaction).

A dictionary of legal-entity abbreviations (Pty Ltd / P/L / PL / Proprietary Limited,
Holdings / Hldgs, Nominees / Noms, Limited / Ltd, Australia / Aust / AU) is folded to
canonical markers so a term and its abbreviated forms compare equal. `canonicalize`
produces that canonical string; `distinctive_tokens` returns a name's distinctive
words (legal-suffix tokens dropped). `verify_value_free` uses both to catch variant
leaks of a forbidden term (e.g. "Veranth Hldgs P/L" leaking "Veranth Holdings Pty Ltd").
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


def canonicalize(text: str) -> str:
    """Casefold, collapse whitespace, and fold legal-suffix variants to markers."""
    t = " " + normalize_ws(text).casefold() + " "
    for pattern, repl in _SUFFIX_SUBS:
        t = re.sub(pattern, repl, t)
    return normalize_ws(t)


def distinctive_tokens(name: str) -> list[str]:
    """A name's distinctive tokens, with legal-suffix tokens removed."""
    toks = normalize_ws(name).casefold().split(" ")
    return [t for t in toks if t and t not in _LEGAL_SUFFIX_TOKENS]
