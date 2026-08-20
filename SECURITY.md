# Security model & threat model

obsify's promise is **"the model reasons on shape; substance stays local."** This document
is the honest scope of that promise — what is enforced, what is best-effort, and what you
must add before trusting it with untrusted code or highly sensitive data. Read it before
pointing `run_on_real` at anything you cannot afford to leak.

## What obsify guarantees (by construction)

- **`scan_pii` returns shape only.** Types, locations and counts — never values. This is
  structural: the tool never puts a detected span into its return payload. Verified by
  `tests/test_obsify.py` (planted values must not appear in the output).
- **`make_synthetic_twin` copies no real value.** Column schema, types and true row counts
  are preserved; every cell value is freshly faked. Leak-verified against the source
  (`tests/test_twin.py`).
- **No network when processing your data, no LLM calls.** Detection is regex + checksums +
  dictionaries + Presidio's local NER. Presidio's domain validation is pinned to an offline
  snapshot. The only network use is a **one-time NER-model download on first run** — a public
  model, transmitting no user data, disable-able with `OBSIFY_AUTO_DOWNLOAD=0`. After setup,
  and always for your data, obsify is offline.
- **`redact_text` / `verify_value_free` fail closed.** The redaction self-check treats a
  value that coincides with a type label or locator as a leak, and matches suffix/variant
  forms, so near-miss leaks are caught (`tests/test_redaction.py`).

## What is best-effort, NOT a guarantee

### `run_on_real` output masking
`run_on_real` executes your code locally and masks stdout/stderr on the way out with
`redact_text`. **Masking recall is not perfect** — an all-caps token or an identifier the
recognizers miss can survive. Therefore:

> **Return AGGREGATES (counts, sums, summaries), never raw records or identifiers.**
> Output masking is defense-in-depth over a disciplined return value, not a substitute for it.

### The execution sandbox is a speed bump, not a jail
`run_on_real` runs model-written Python in a subprocess behind a static AST guard (denylist
of network/subprocess/eval imports and write-mode `open`) plus a runtime socket block and a
wall-clock timeout. **Confirmed residuals** (verified by adversarial tests):

- The static guard is **bypassable** (e.g. `getattr(os, 'sys'+'tem')`, dynamic import
  tricks). It stops naive/accidental escapes, not a determined author.
- The filesystem is **not jailed** — code can READ arbitrary local files.
- The runtime block covers Python sockets, but a shell escape could still reach the network.

**Do not run untrusted code against secrets without OS-level sandboxing.** For untrusted
use, add real isolation at the `obsify/sandbox.py` seam: a container / gVisor / Windows
AppContainer, a filesystem jail, and a syscall allowlist. The static guard + socket block
are layered *under* that, not a replacement for it.

### The routing guard classifies by path, not content
The guard (`obsify.guard`) blocks reads of files whose **path** matches a `confidential` /
`restricted` glob in `.obsify.json`. A sensitive file placed in a `public` path is not
protected. Label conservatively; the guard gates the assistant's tools, not your own local
processes.

## Appropriate use today

- **Good:** local analyst/developer workflows on your own machine, where you want an AI
  assistant's help without piping raw values to a model provider, and where the code being
  run is your own or the assistant's (semi-trusted).
- **Not yet:** a multi-tenant service executing untrusted third-party code against
  confidential data. That needs the OS-level hardening above first.

## Reporting a vulnerability

Report privately via GitHub: **Security → Report a vulnerability** (private vulnerability
reporting) on this repository, or email the maintainer at **Erfan.Harrd@gmail.com**. Please do
**not** file a public issue for an exploitable sandbox escape until a fix is available.
