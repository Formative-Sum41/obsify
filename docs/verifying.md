# Verifying obsify works

Three layers, cheapest first. The first two are self-contained; the third is the ~5-minute
"prove it in a real client" check.

## Layer 1 + 2 — automated (run this first)

```bash
pip install -e ".[dev]"
python -m spacy download en_core_web_lg     # one-time
pytest tests/ -q
```

66 tests. What they establish:

- **Internals** — extraction (PDF/Excel/DOCX), detection + precision filter, synthetic twin,
  sandbox, redaction self-check, guard classification, `obsify init` behavior.
- **The MCP protocol boundary** (`tests/test_mcp_protocol.py`) — launches the real
  `obsify-mcp` server over stdio and speaks MCP to it exactly as a client does: all five tools
  register with valid schemas, calls round-trip through JSON-RPC, and `scan_pii` returns
  **shape only, end to end** (no planted value leaks back through the protocol).

If `pytest` is green, the server genuinely works as an MCP server — not just as Python functions.

## Interactive — MCP Inspector (see it with your own eyes)

The official inspector gives you a UI to list and call the tools against the live server:

```bash
# generate some safe synthetic data to poke at
python -m obsify.make_corpus --out ./corpus_demo

# launch the inspector against the server (Node required; no install needed)
npx @modelcontextprotocol/inspector obsify-mcp
```

In the inspector: connect → **Tools** tab → you should see `scan_pii`, `redact_text`,
`verify_value_free`, `make_synthetic_twin`, `run_on_real`. Then:

- Call `scan_pii` with `path = ./corpus_demo/ledger.xlsx` → confirm you get **types + counts +
  locations only**, no values.
- Call `redact_text` with `text = "TFN 123 456 782 paid to Jane Roe"` → confirm the TFN and name
  come back masked.
- Call `make_synthetic_twin` with `path = ./corpus_demo/ledger.xlsx`, `out = ./twin.xlsx` →
  open the twin and confirm the schema matches but every value is fake.

(This is also the screenshot to put in your portfolio README.)

## Layer 3 — live in a real client (the last mile)

1. Register the server (see the main README). For Claude Code, `.mcp.json`:
   ```json
   { "mcpServers": { "obsify": { "command": "obsify-mcp" } } }
   ```
2. Restart the client. Confirm obsify's tools appear in its tool list.
3. Ask the model something that should trigger a tool, e.g.:
   *"Use scan_pii on ./corpus_demo/audit_memo.docx and tell me what PII types are present."*
   → It should call `scan_pii` and report types/counts **without** ever quoting a value.
4. (Routing) Run `obsify init`, paste the printed hook into `.claude/settings.json`, restart, then
   ask the model to directly `Read` a file under a labelled folder (e.g. `./corpus_demo` if you
   label `*/corpus_demo/*`) → the guard should **block the read and redirect** to obsify.

Success = the model uses the tools, values never appear in the transcript, and the guard fires on
a labelled read. That's the full loop confirmed.

## What is NOT covered (be honest in a demo)

- `run_on_real` output masking is best-effort — see [`SECURITY.md`](../SECURITY.md). Return
  aggregates.
- The execution sandbox is a speed bump, not a jail. Don't run untrusted code against secrets
  without OS-level isolation.
- No OCR: scanned/image PDF pages are flagged as low-coverage, not transcribed.
