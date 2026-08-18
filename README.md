# obsify

**Let an AI assistant work on sensitive files without their raw values ever entering the model's context.**

obsify is a local, deterministic [MCP](https://modelcontextprotocol.io) server. The frontier
model reasons over **shape** — schemas, synthetic twins, masked feedback — while deterministic
local code touches the **substance** and returns only masked, aggregated results. No LLM calls,
no network at runtime: detection is regex + checksums + dictionaries + [Presidio](https://github.com/microsoft/presidio)'s
local NER.

It ships with Australian entity support (ABN / ACN / TFN, checksum-validated) and a
label-driven **routing layer** that makes "when should the assistant avoid raw data" a
deterministic, enforced decision rather than a judgement call.

> **Honest scope:** `run_on_real` executes model-written code in a *best-effort* local sandbox
> and masks its output *best-effort*. It is not a jail. Read [`SECURITY.md`](SECURITY.md) before
> pointing it at anything you cannot afford to leak. Return aggregates.

## Why

Feeding confidential documents to a hosted LLM means the substance leaves your perimeter. The
usual answers are "don't use the LLM" or "trust the provider." obsify takes a third path —
**compute-to-data**: bring the code to the data, not the data to the model.

- The model sees the **schema** of a spreadsheet, not its rows.
- The model develops against a **synthetic twin** (faked values, real structure).
- The model's analysis code runs **locally**; only masked, aggregated output returns.

The frontier model's reasoning is preserved. Only its *eyes on raw values* are removed.

## Tools

| Tool | What it does | Returns |
|---|---|---|
| `scan_pii(path)` | Scan a file/folder for PII | Types, locations, counts — **never values** |
| `make_synthetic_twin(path, out)` | Faithful fake of an Excel workbook | Schema summary; twin written to `out` (values faked, leak-verified) |
| `run_on_real(code, data_path)` | **Compute-to-data**: run your code locally against the real file (bound to `DATA_PATH`) | Only PII-masked, size-capped stdout/stderr — **return aggregates** |
| `redact_text(text)` | Mask PII in a string to `<TYPE>` tokens | The redacted string |
| `verify_value_free(text, terms)` | Fail-closed check that `text` leaks none of `terms` (or their variants) | `{"value_free": bool}` |

**Supported documents:** PDF (text + tables; complex-table fallback via `obsify[tables]`),
Excel `.xlsx`/`.xlsm`, and Word `.docx` (paragraphs + tables). Unreadable or unsupported files
are surfaced as explicit notes/blind spots, never silently dropped. (No OCR yet — scanned/image
pages are flagged as low-coverage, not transcribed.)

## Demo

![obsify's tools in the MCP Inspector, called against the synthetic corpus](docs/img/inspector.png)

*obsify's five tools in the [MCP Inspector](https://github.com/modelcontextprotocol/inspector),
called against the synthetic corpus — `scan_pii` returns types / counts / locations only, never
values.*

<!-- PLACEHOLDER: capture this with `npx @modelcontextprotocol/inspector obsify-mcp` (see
     docs/verifying.md), then save the screenshot to docs/img/inspector.png. -->

## Try it — synthetic corpus

Generate a fake-but-realistic corpus (all synthetic; ABN/ACN/TFN are checksum-valid) spanning
all three formats, then point a tool at it:

```bash
pip install "obsify[demo]"                 # reportlab, for the sample PDFs
python -m obsify.make_corpus --out ./corpus_demo
```

It writes a multi-sheet Excel ledger (a numeric false-positive minefield), a PDF engagement
letter (prose + trial-balance table), and a DOCX audit memo (paragraphs + vendor table). Great
for kicking the tyres on `scan_pii` / `make_synthetic_twin` without touching real data.

## Install & run as an MCP server

Requires Python 3.11+. obsify speaks MCP over **stdio** — the client launches it as a local
subprocess; nothing is hosted remotely. Register it with any MCP-capable client (Claude
Desktop, Claude Code, Cursor, VS Code, …) by adding one block to that client's config.

**Recommended — zero-install via [uvx](https://docs.astral.sh/uv/):**

```json
{ "mcpServers": { "obsify": { "command": "uvx", "args": ["obsify-mcp"] } } }
```

`uvx` fetches obsify from PyPI and runs it on demand — no permanent install. On **first run**,
obsify downloads the spaCy NER model (`en_core_web_lg`, ~560 MB) once and caches it; this
fetches a public model and sends no user data (set `OBSIFY_AUTO_DOWNLOAD=0` to forbid it and
install the model yourself). Later runs are instant and fully offline.

**Or install it (pip / pipx):**

```bash
pipx install obsify        # isolated, on PATH  (or: pip install obsify)
```

Then point the client at the installed command:

```json
{ "mcpServers": { "obsify": { "command": "obsify-mcp" } } }
```

Restart the client and the tools appear. Optional extras: `obsify[tables]` (complex-table PDF
fallback via camelot + Ghostscript), `obsify[compute]` (pandas, handy inside `run_on_real` code).

> **PATH gotcha (the #1 cause of "server won't connect"):** the `command` must resolve on the
> PATH the *client* sees. A GUI client may not share your venv's PATH. Fixes: use `uvx`/`pipx`
> (globally resolvable), or give an absolute path — `"/path/to/.venv/bin/obsify-mcp"` (macOS/Linux)
> or `"C:\\path\\to\\.venv\\Scripts\\obsify-mcp.exe"` (Windows).

**From this repo (before it's on PyPI):**

```bash
pip install "git+https://github.com/Formative-Sum41/obsify.git"   # gets `obsify-mcp` + `obsify`
```

## The routing layer — deterministic, not a judgement call

The hard part of "help me, but don't read the confidential file" is *deciding when to protect*.
obsify moves that decision out of the model and into the environment:

1. **`.obsify.json`** — a label manifest classifying paths (`public` / `confidential` / `restricted`).
2. **`obsify.guard`** (run as `python -m obsify.guard`) — a PreToolUse guard that blocks a direct read of a labelled file
   (exit 2) and redirects the assistant to `scan_pii` / `make_synthetic_twin` / `run_on_real`.
3. **A convention** (in `CLAUDE.md`) so the assistant *prefers* obsify before it even hits the guard.

Set it up with one command:

```bash
obsify init [--dir PATH] [--with-claude-md]
```

`obsify init` is **non-destructive by design** — it owns exactly one file and hands you snippets
for the rest:

- **`.obsify.json`** — obsify owns this; init writes it (never overwritten without `--force`).
- **`.claude/settings.json`** — *your* file: init **prints** the PreToolUse hook block to paste,
  never edits it (it runs code, so registering it is your call).
- **`CLAUDE.md`** — *your* file: the convention is **opt-in**. Default prints it; `--with-claude-md`
  appends a marker-wrapped, idempotent block that never clobbers your content.

Full convention: [`docs/obsify_routing.md`](docs/obsify_routing.md).

## How detection stays precise

- **Checksum-validated identifiers.** ABN/ACN/TFN candidates are proposed by regex and confirmed
  by their official checksums, so a random number is never reported as an identifier.
- **Context-required IDs.** A bare number is only accepted as an ABN/ACN/TFN when a label word
  ("TFN", "ABN", "BSB", …) is nearby — this kills the sequential-journal-ID false-positive flood
  on numeric ledgers.
- **Letterless / NER-with-digit suppression.** Pure numbers, amounts, dates and alnum codes are
  not flagged as names/orgs; real names, emails and addresses (which carry letters) are unaffected.
  Validated letterless PII stays exempt: checksum IDs (ABN/ACN/TFN/Medicare), Luhn cards, valid
  IPs, BSB-adjacent accounts, and phones (via context or phone shape) — while a decimal point
  still marks an amount, not a phone.

## Measured accuracy

obsify ships a scored evaluation harness (`eval/` — labelled synthetic corpus + answer key +
scorer against the *shipping* detector, plus an independent third-party cross-check). Headline
on the synthetic corpus: **100% recall** on expected-detect items, **0 false positives** on a
numeric FP-torture sheet (with a grouped-number guard), bare context-gated IDs correctly
suppressed. Independent cross-check vs Microsoft `presidio-research`: EMAIL/IBAN 100%, PERSON 94%.

**The harness earned its keep — it found real defects, which were then fixed:** credit cards and
phone numbers were being silently suppressed by the numeric-noise filter (now exempt via checksum
validation / phone shape), and Medicare, IP, date-of-birth, AU passport and driver-licence had no
recognizer (now added, checksum- or context-gated). Full method, numbers, and remaining documented
gaps (SWIFT/BIC, non-DOB dates): [`eval/README.md`](eval/README.md).

## Tests

```bash
pip install -e ".[dev]"
pytest tests/            # or run any file directly: python tests/test_obsify.py
```

Ten suites (66 tests), run in CI on Linux + Windows / Python 3.11 + 3.12:

- **mcp-protocol** — launches the real server over stdio and speaks MCP to it (the same path a
  client like Claude uses): confirms all five tools register with valid schemas and that calls
  round-trip through JSON-RPC — including `scan_pii` returning **shape only, end to end**.
- **checksums** — anchored to externally-published ABN/ACN/TFN worked examples (valid and
  corrupted), which breaks the generator↔validator circularity.
- **obsify / twin / redaction** — the privacy invariants: shape-only output, leak-free twins,
  and a fail-closed self-check.
- **precision** — the false-positive suppressors kill numeric-ledger noise while keeping real names.
- **routing** — the guard's block/allow classification and `obsify init`'s non-destructive contract.
- **corpus** — the synthetic PDF+Excel+DOCX corpus end to end: per-format detection, DOCX
  paragraph+table extraction, and shape-only output across every format.
- **model** — first-run auto-download logic (no-op when present; clear error when disabled+missing).

For interactive verification (MCP Inspector) and the live-client last-mile check, see
[`docs/verifying.md`](docs/verifying.md).

## License

MIT — see [`LICENSE`](LICENSE).
