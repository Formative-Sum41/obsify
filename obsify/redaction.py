"""Fail-closed redaction self-check.

Given a piece of text and a list of forbidden `terms` (values that must not appear),
decide whether the text leaks any of them — in normalized OR suffix-canonical form,
plus each term's distinctive-token core, so abbreviation/variant leaks are caught too.
The check FAILS CLOSED: a value that coincides with a type label or locator counts as
a leak, and zero detail is returned on what matched. This backs `verify_value_free`
(confirm an artifact is safe before it leaves the perimeter) and `write_*` guards that
delete their output on any leak.

Depends only on the whitespace/variant normalizers (`normalize_ws`, `canonicalize`,
`distinctive_tokens`) — no scoring/report machinery.
"""

from __future__ import annotations

from pathlib import Path

from obsify.extraction import normalize_ws
from obsify.variants import canonicalize, distinctive_tokens


def _redaction_forbidden(gt_values: list[str], master_list: list[str],
                         identifiers: list[str]) -> set[str]:
    """Every surface form that must not appear: each value, master entry and
    document/sheet identifier in normalized and canonical form, plus each master
    entry's distinctive-token core (which every suffix/abbreviation variant
    canonicalizes to a superstring of, so variant leaks are caught too).
    Identifiers are included because a filename or tab name can itself identify a
    subject."""
    forbidden: set[str] = set()
    for v in list(gt_values) + list(master_list) + list(identifiers):
        forbidden.add(normalize_ws(v).casefold())
        forbidden.add(canonicalize(v))
    for m in master_list:
        core = canonicalize(" ".join(distinctive_tokens(m)))
        if core:
            forbidden.add(core)
    forbidden.discard("")
    return forbidden


def redaction_self_check(summary_text: str, gt_values: list[str],
                         master_list: list[str], identifiers: list[str] | None = None) -> bool:
    """Return True if ANY forbidden surface form (or variant) appears in the text.
    Fails closed: a value that coincides with a type label or locator counts as a
    leak. Zero detail is returned — the caller reports failure only."""
    norm = normalize_ws(summary_text).casefold()
    canon = canonicalize(summary_text)
    for f in _redaction_forbidden(gt_values, master_list, identifiers or []):
        if f in norm or f in canon:
            return True
    return False


def write_redacted_summary(summary_md: str, path: str, gt_values: list[str],
                           master_list: list[str], identifiers: list[str] | None = None) -> bool:
    """Write the summary, then self-check the WRITTEN file. On any leak, delete the
    file and return False (caller reports 'redaction self-check failed', no detail).
    Returns True on a clean, verified file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(summary_md, encoding="utf-8")
    written = p.read_text(encoding="utf-8")  # grep the actual bytes on disk
    if redaction_self_check(written, gt_values, master_list, identifiers):
        p.unlink(missing_ok=True)
        return False
    return True
