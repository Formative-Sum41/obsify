"""Fail-closed, variant-aware leak check — backs the `verify_value_free` tool.

Given `text` and a list of forbidden `terms`, decide whether the text leaks any of
them — in normalized OR suffix-canonical form, plus each term's distinctive-token
core, so abbreviation/variant leaks are caught too (e.g. "Veranth Hldgs P/L" leaks the
term "Veranth Holdings Pty Ltd"). Fails closed: a value that coincides with a type
label or locator still counts as a leak, and no detail is returned on what matched.

Depends only on the whitespace/variant normalizers (`normalize_ws`, `canonicalize`,
`distinctive_tokens`).
"""

from __future__ import annotations

from obsify.extraction import normalize_ws
from obsify.variants import canonicalize, distinctive_tokens


def _forbidden_forms(terms: list[str]) -> set[str]:
    """Every surface form a term must not appear as: normalized, suffix-canonical, and
    its distinctive-token core (which every suffix/abbreviation variant canonicalizes
    to a superstring of, so variant leaks are caught)."""
    forbidden: set[str] = set()
    for t in terms:
        forbidden.add(normalize_ws(t).casefold())
        forbidden.add(canonicalize(t))
        core = canonicalize(" ".join(distinctive_tokens(t)))
        if core:
            forbidden.add(core)
    forbidden.discard("")
    return forbidden


def redaction_self_check(text: str, terms: list[str]) -> bool:
    """Return True if any forbidden term (or a suffix/token-core variant of it) appears
    in `text`. Fails closed; reports no detail on what matched."""
    norm = normalize_ws(text).casefold()
    canon = canonicalize(text)
    return any(f in norm or f in canon for f in _forbidden_forms(terms))
