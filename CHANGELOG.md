# Changelog

All notable changes to obsify are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [0.1.0] — 2026-08-20

Initial release. A local, privacy-preserving PII toolkit over MCP: the model reasons on
**shape** (schemas, synthetic twins, masked feedback) while deterministic local code touches
the **substance** and returns only masked, aggregated results.

### Tools
- `scan_pii(path)` — PII types / locations / counts, never values.
- `make_synthetic_twin(path, out)` — schema-faithful, fully-faked Excel mirror (leak-verified).
- `run_on_real(code, data_path)` — compute-to-data: model-written code runs locally in a
  best-effort sandbox; only masked, size-capped output returns.
- `redact_text(text)` — mask detected PII to `<TYPE>` placeholders.
- `verify_value_free(text, terms)` — fail-closed, variant-aware leak check.

### Detection
- Deterministic Australian recognizers (checksum-validated): ABN, ACN, TFN, Medicare, plus
  BSB-adjacent account numbers, AU addresses, passport and driver-licence (context-gated).
- Presidio baseline: PERSON, ORGANIZATION, EMAIL, PHONE, LOCATION, CREDIT_CARD, IBAN, IP.
- Precision filter that suppresses numeric-ledger false positives (bare checksummed numbers,
  amounts-as-phones, alnum codes-as-names) while exempting validated PII.
- **Known-entity masking** — a local `.obsify.entities` list of names to hide, matched with
  suffix/abbreviation variants and reported/masked as `KNOWN_ENTITY`; the list never enters
  the model's context.

### Routing layer
- `.obsify.json` sensitivity labels + a stdlib PreToolUse guard (`python -m obsify.guard`)
  that blocks direct reads of labelled files and redirects to the tools.
- `obsify init` — non-destructive scaffolding (owns `.obsify.json`; prints snippets for your
  own config files).

### Formats & ops
- PDF (text + tables), Excel (`.xlsx`/`.xlsm`), Word (`.docx`); unreadable/oversized inputs
  surfaced as explicit blind-spot notes, never silently dropped.
- First-run spaCy model auto-download (public model, no user data; disable with
  `OBSIFY_AUTO_DOWNLOAD=0`).

### Quality
- 82 tests including an MCP-protocol integration layer; a scored evaluation harness (`eval/`)
  with an independent third-party benchmark cross-check; CI on Linux + Windows / Python 3.11–3.12.

[0.1.0]: https://github.com/Formative-Sum41/obsify/releases/tag/v0.1.0
