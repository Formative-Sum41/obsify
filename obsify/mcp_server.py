"""obsify — a local, privacy-preserving MCP server for working with sensitive data.

Design principle (why this is safe to hand any AI client): MCP tool *arguments*
come from the model and *results* go back into the model's context. So the
privacy-preserving tools take a PATH to data the model cannot see, touch the real
data LOCALLY, and return only SHAPE — types, locations and counts, never values.
The model reasons over shape; substance never enters its context and never leaves
to a provider. Utilities (redact_text, verify_value_free) round out the toolkit.

Advisory, not enforcing: it makes the capability available; the host decides how
to use it. Runs locally over stdio. Makes no network calls when processing your
data; the only network use is a one-time NER-model download on first run (a public
model, no user data sent), which OBSIFY_AUTO_DOWNLOAD=0 disables.

Tools:
  scan_pii(path)            -> PII types + locations + counts (NO values)   [shape]
  redact_text(text)         -> the text with PII masked to [TYPE] tokens    [utility]
  verify_value_free(text,   -> fail-closed check that `text` contains none
                    terms)     of `terms` (or their suffix/variant forms)   [utility]

Run:  python -m obsify.mcp_server         (stdio, for MCP clients)
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from pathlib import Path

import obsify  # noqa: F401  (Windows runtime bootstrap before presidio import)
from mcp.server.mcpserver import MCPServer

from obsify import known_entities
from obsify.config import DEFAULT_CONFIG
from obsify.detection import _post_recognize_filter
from obsify.extraction import SUPPORTED_SUFFIXES, extract_document
from obsify.redaction import redaction_self_check

mcp = MCPServer(
    name="obsify",
    title="obsify — privacy-preserving PII toolkit",
    description="Local, deterministic PII detection, redaction and verification. "
                "Substance stays local; only shape is returned.",
    instructions="Use scan_pii on a file/folder PATH to learn what PII is where "
                 "WITHOUT its values. Use redact_text to mask a string. Use "
                 "verify_value_free to confirm a string leaks none of a value list.",
)

# The spaCy model + analyzer are expensive; build once, lazily, and reuse.
_ANALYZER = None
# Detect posture: enable the precision suppressors so numeric ledgers do not flood.
_DETECT_CFG = replace(DEFAULT_CONFIG, suppress_letterless_detections=True,
                      suppress_ner_with_digits=True)
_SUFFIXES = SUPPORTED_SUFFIXES  # pdf, xlsx/xlsm, docx — single source of truth


def _analyzer():
    global _ANALYZER
    if _ANALYZER is None:
        from obsify.nlp import build_analyzer
        _ANALYZER = build_analyzer(_DETECT_CFG)
    return _ANALYZER


def _detect(text: str, matchers=None):
    """Analyze one text with the custom recognizers + precision filter, then merge in
    any known-entity matches as KNOWN_ENTITY spans."""
    entities = list(_DETECT_CFG.entities_of_interest)
    results = _analyzer().analyze(text=text, language="en", entities=entities,
                                  score_threshold=_DETECT_CFG.presidio_score_threshold)
    results = _post_recognize_filter(results, text, _DETECT_CFG)
    if matchers:
        from presidio_analyzer import RecognizerResult
        for s, e in known_entities.find_known(text, matchers):
            results.append(RecognizerResult(entity_type=known_entities.ENTITY,
                                            start=s, end=e, score=1.0))
    return results


def _known_matchers(entities: str | None, near: str | None = None):
    """Compile matchers from an explicit `.obsify.entities` path, or the auto-discovered
    one. Returns None when no list is available. The names are read locally and never
    returned — only their type/location (scan) or a mask (redact) surfaces."""
    path = entities or known_entities.discover(near)
    if not path or not Path(path).exists():
        return None
    names = known_entities.load_entities(path)
    return known_entities.compile_matchers(names) if names else None


@mcp.tool()
def scan_pii(path: str, max_cells: int = 20000, entities: str | None = None) -> dict:
    """Scan a file or folder for PII and return TYPES + LOCATIONS + COUNTS only —
    never the detected values. Safe to surface to an LLM: it learns what PII exists
    and where, without the substance entering context. Recurses into subfolders;
    skips unreadable files and caps very large sheets, reporting both as notes.

    `entities` is an optional PATH to a local `.obsify.entities` file (one name per
    line) of KNOWN names to hide; matches (incl. suffix/abbreviation variants) are
    reported as KNOWN_ENTITY. If omitted, a nearby `.obsify.entities` is auto-used.
    The names are read locally and never returned."""
    root = Path(path)
    notes: list[str] = []
    if not root.exists():
        notes.append(f"path not found: {path} (nothing scanned — not the same as 'no PII')")
    files = [root] if root.is_file() else sorted(
        p for p in root.rglob("*") if p.suffix.lower() in _SUFFIXES)
    by_type: Counter = Counter()
    findings: list[dict] = []
    low_coverage: list[dict] = []
    read_ok = 0
    matchers = _known_matchers(entities, path)
    for f in files:
        segs, cov = extract_document(str(f), notes)
        if not segs and not cov:
            continue
        read_ok += 1
        if len(segs) > max_cells:
            notes.append(f"{f.name}: {len(segs)} segments > max_cells {max_cells}; "
                         f"scanned first {max_cells} (UNSCANNED REMAINDER — blind spot)")
            segs = segs[:max_cells]
        low_coverage += [{"document": c.document, "page": c.page} for c in cov if c.flag]
        for seg in segs:
            for r in _detect(seg.text, matchers):
                by_type[r.entity_type] += 1
                findings.append({"type": r.entity_type, "document": seg.document,
                                 "location": seg.locator})  # NO value
    return {
        "files_found": len(files), "files_read": read_ok,
        "counts_by_type": dict(sorted(by_type.items())),
        "findings": findings,           # type + location only
        "low_coverage_pages": low_coverage,
        "notes": notes,                 # skipped/oversized files (blind spots)
    }


@mcp.tool()
def redact_text(text: str, entities: str | None = None) -> str:
    """Return `text` with detected PII replaced by <TYPE> placeholders (e.g.
    <AU_TFN>, <PERSON>). Deterministic; checksum-validated identifiers and
    context/precision rules apply so bare numbers are not over-masked.

    `entities` is an optional PATH to a local `.obsify.entities` file of KNOWN names
    to hide; matches (incl. variants) are masked as <KNOWN_ENTITY>. If omitted, a
    nearby `.obsify.entities` is auto-used."""
    from presidio_anonymizer import AnonymizerEngine
    results = _detect(text, _known_matchers(entities))
    if not results:
        return text
    return AnonymizerEngine().anonymize(text=text, analyzer_results=results).text


@mcp.tool()
def verify_value_free(text: str, terms: list[str]) -> dict:
    """Fail-closed check that `text` contains NONE of `terms` (nor their
    suffix-normalized / distinctive-token variants). Returns {"value_free": bool}
    with zero detail on what matched — for verifying an artifact before it leaves
    the perimeter."""
    leak = redaction_self_check(text, list(terms))
    return {"value_free": not leak}


@mcp.tool()
def make_synthetic_twin(path: str, out: str, cap_rows: int = 2000) -> dict:
    """Generate a SYNTHETIC TWIN of a real Excel workbook at `path`, written to
    `out`. Schema (sheets, headers, column types, true row counts) is preserved;
    every data value is freshly FAKED — no real value is copied. Reason and write
    your analysis code against the twin; then run it on the real file with
    run_on_real. Returns the schema summary (safe shape)."""
    from obsify.twin import make_synthetic_twin as _twin
    return _twin(path, out, cap_rows=cap_rows)


_OUTPUT_CAP = 4000


@mcp.tool()
def run_on_real(code: str, data_path: str, timeout: int = 30) -> dict:
    """COMPUTE-TO-DATA: execute your Python `code` LOCALLY against the real file at
    `data_path` (bound to the variable DATA_PATH in your code); the returned `output`
    is size-capped and **best-effort** PII-masked. The data never enters your context;
    substance never leaves. **Return AGGREGATES (counts/sums/summaries) via print()** —
    output masking is defense-in-depth, NOT a guarantee (NER can miss a name in a raw
    record), so never print raw records or identifiers. The `masking` field carries this
    caveat with the result. Network is disabled and a timeout applies."""
    from obsify.sandbox import execute
    res = execute(code, data_path, timeout=timeout)
    out = redact_text(res.stdout)[:_OUTPUT_CAP] if res.stdout.strip() else ""
    err = redact_text(res.stderr)[:_OUTPUT_CAP] if res.stderr.strip() else ""
    return {
        "ok": res.exit_code == 0 and not res.timed_out,
        "exit_code": res.exit_code,
        "timed_out": res.timed_out,
        "output": out,      # best-effort PII-masked (see `masking`), truncated
        "error": err,       # best-effort PII-masked traceback/message
        "masking": "best-effort — NOT a guarantee; return AGGREGATES, never raw records",
        "truncated": len(res.stdout) > _OUTPUT_CAP or len(res.stderr) > _OUTPUT_CAP,
    }


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
