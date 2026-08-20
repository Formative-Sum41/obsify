# Contributing to obsify

Thanks for your interest. obsify is a small, deliberately-scoped project; contributions
are welcome via pull request.

## Setup

```bash
git clone https://github.com/Formative-Sum41/obsify.git
cd obsify
pip install -e ".[dev]"
python -m spacy download en_core_web_lg   # ~560 MB NER model, not a PyPI dep
pytest tests/
```

## The bar for a merge

- **Tests pass.** CI runs `pytest tests/` on Linux + Windows / Python 3.11–3.12; the same
  gate applies to your PR.
- **New behavior ships with a test.** Anything touching detection or masking must be covered
  — the scored eval harness (`eval/`) is the regression gate, so add/adjust cases there when
  detection changes.
- **Keep it in scope.** obsify does one thing (local, privacy-preserving PII handling over
  MCP). Out-of-scope features may be declined — open an issue to discuss before building.

## Non-negotiable invariants (please don't break these)

These are the whole point of the project; a PR that violates one won't be merged:

1. **No LLM calls in the library.** Detection is regex + checksums + dictionaries + Presidio's
   local NER. No model inference at runtime.
2. **No runtime network when processing data.** The only permitted network is the one-time
   spaCy model download at first run (a public model, no user data), disable-able with
   `OBSIFY_AUTO_DOWNLOAD=0`.
3. **No real data or client names** in code, tests, fixtures, or docs. All test data is
   synthetic; Australian identifiers are checksum-valid *fakes*. Never commit a real name,
   number, email, or document.
4. **Shape, not substance.** `scan_pii` returns types/locations/counts only; `make_synthetic_twin`
   copies no real value; `run_on_real` returns best-effort-masked aggregates. Don't add a code
   path that returns raw values to the model.

## Reporting

- Bugs / features → GitHub Issues (templates provided).
- **Security** (obsify's sandbox executes model-written code) → see [`SECURITY.md`](SECURITY.md);
  report privately, not as a public issue.

By contributing, you agree your contributions are licensed under the project's MIT license.
