# Known-entity masking

Deterministically find and mask a **known** list of sensitive names — including the
suffix/abbreviation variants that NER misses.

## Why

Presidio's NER has imperfect recall on names, especially abbreviated forms in financial
text (`BRIGHTWATER HLDGS P/L` for *Brightwater Holdings Pty Ltd*). When you can enumerate
the entities to hide — a per-engagement list of client and personnel names — a
deterministic dictionary gives **100% coverage of those known names and their variants**,
complementing NER rather than depending on it.

## The privacy model (why this is safe)

The list of names is itself sensitive substance. If it were passed as a tool argument it
would enter the model's context — defeating the point. So obsify keeps it local:

- The names live in a local **`.obsify.entities`** file, read only by local code.
- Tools take a **path** to that file (or auto-discover it), **never the names**.
- `scan_pii` reports `KNOWN_ENTITY` by **type and location only** — never a value.
- `redact_text` replaces matches with `<KNOWN_ENTITY>`.
- The file is git-ignored and labelled `restricted` in `.obsify.json`, so the guard
  blocks any attempt to read it directly.

The names never enter the model's context — consistent with obsify's "shape, not
substance" thesis.

## The `.obsify.entities` file

One name per line; `#` comments and blank lines ignored. `obsify init` scaffolds an empty
template and reminds you to git-ignore it.

```
# names to hide (kept local, never committed, never read into an assistant's context)
Brightwater Holdings Pty Ltd
Priya Nair
```

## Matching

Reuses obsify's variant normalization. Two tiers:

- **Default** — the core name tokens (with dictionary abbreviations: Holdings/Hldgs,
  Nominees/Noms, Australia/Aust, …) matched **contiguously**, with an **optional trailing
  legal suffix** (Pty Ltd / P/L / Proprietary Limited / …). Catches
  `Brightwater Holdings Pty Ltd`, `BRIGHTWATER HLDGS P/L`, and bare `Brightwater Holdings`.
  High precision — scattered tokens ("the water was bright … the holdings grew") do not match.
- **Fuzzy (opt-in)** — the same, but tolerating up to two filler tokens between core tokens
  (`Brightwater Marine Holdings Pty Ltd`). May over-mask; use when over-redaction is safer
  than a miss.

Overlapping matches are collapsed to one span (longest wins).

## Using it

```python
# via the MCP tools (paths, never names):
scan_pii("./real/ledger.xlsx", entities="./.obsify.entities")   # -> KNOWN_ENTITY counts/locations
redact_text("… BRIGHTWATER HLDGS P/L …", entities="./.obsify.entities")  # -> "… <KNOWN_ENTITY> …"

# or omit `entities` and obsify auto-discovers the nearest .obsify.entities.
```

`run_on_real`'s masked output also honours an auto-discovered `.obsify.entities`, so known
names are stripped from aggregates too.

## What it is not

- Not a replacement for NER — it's a deterministic **complement** for names you can list.
- Not fuzzy by default — the default tier is precise; broaden explicitly if you need to.
- Not a place to put values you don't already control: the file is real names, so treat it
  like any secret (local, git-ignored, `restricted`).
