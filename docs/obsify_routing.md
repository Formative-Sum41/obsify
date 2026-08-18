# obsify routing layer — hook, convention, label manifest

The hard problem with "let the assistant help, but don't feed it confidential data" is
**deciding when to protect**. If that decision lives in the model's judgement, it fails
the first time the model is confident and wrong. obsify moves the decision out of the
model and into the environment: files carry **sensitivity labels**, and a **PreToolUse
guard** enforces them deterministically. The model never has to *choose* to be careful —
a direct read of sensitive data is simply refused at the moment of need, and the model is
handed the safe tools instead.

This mirrors the project's governing rule (Architecture Golden Standard, D1/s258, D3/s091):
**high-stakes constraints are enforced in code, not prompt.** The convention below guides;
the hook enforces.

---

## Quick start — `obsify init`

```
python -m src.init [--dir PATH] [--with-claude-md] [--force] [--python PATH]
```

One command scaffolds the routing layer into a project, **non-destructively**:

- **Writes `.obsify.json`** (the label manifest) — the one file obsify owns. Never
  overwritten unless you pass `--force`.
- **Prints the `.claude/settings.json` hook snippet** for you to paste. init never edits
  that file: it is agent-startup config that runs code, so it stays yours to change.
- **CLAUDE.md is opt-in.** By default init just *prints* the routing convention for you to
  paste into your own `CLAUDE.md`. Pass `--with-claude-md` to have it appended
  automatically — idempotently, wrapped in `<!-- BEGIN/END obsify … -->` markers, never
  clobbering your existing content.
- `--python` sets the interpreter path baked into the hook command (defaults to the
  current interpreter).

The tenet: **obsify owns `.obsify.json`; you own `CLAUDE.md` and `.claude/settings.json`.**
The tool scaffolds its own file and hands you snippets for yours — adoption is a paste,
never a silent edit.

---

## The three pieces

### 1. Label manifest — `.obsify.json`
A small JSON file that classifies paths by glob into sensitivity labels. Placed at the
project root (the guard walks up from the target file to find the nearest one, so
subtrees can override).

```json
{
  "default": "public",
  "rules": [
    { "glob": "*/real/*",         "label": "restricted" },
    { "glob": "*/sensitive/*",    "label": "confidential" },
    { "glob": "*/corpus/*",       "label": "restricted" },
    { "glob": "*/ground_truth/*", "label": "restricted" },
    { "glob": "*/data/*",         "label": "confidential" }
  ],
  "obsify_tools": ["scan_pii", "run_on_real", "make_synthetic_twin"],
  "twin_dir": "twin"
}
```

Labels:

| label          | meaning                                                                 | direct `Read`? |
| -------------- | ----------------------------------------------------------------------- | -------------- |
| `public`       | read freely                                                             | ✅ allowed      |
| `confidential` | no direct read — use obsify (`scan_pii` / `run_on_real` / `make_synthetic_twin`) | ⛔ blocked      |
| `restricted`   | no direct read, no raw output — obsify with masked/aggregated results only | ⛔ blocked      |

Matching is **last-rule-wins** (`fnmatch`, case-insensitive on the POSIX form of the path).
Anything not matched falls to `default`. Label conservatively: it is cheap to widen a glob,
expensive to leak.

### 2. Guard — `obsify.guard` (run as `python -m obsify.guard`)
A stdlib-only PreToolUse hook (no heavy imports — it runs on every tool call). It ships
inside the package and is invoked as a module, so the hook command is the same whether
obsify is pip-installed or run from a clone. On each read it:

1. reads the tool call JSON from stdin and pulls the target path;
2. finds the nearest `.obsify.json` (walking up from the file, then cwd) — or falls back to
   a conservative built-in ruleset if none is present;
3. classifies the path. If the label is `confidential` or `restricted`, it **exits 2**
   (block) and writes a redirect message to stderr; otherwise **exits 0** (allow).

The redirect message is the point — it doesn't just say "no," it tells the model exactly
what to call instead:

> BLOCKED by obsify: '…' is classified CONFIDENTIAL. Do not read it directly - the raw
> values must not enter your context. Use obsify instead: `scan_pii(path)` to see PII
> types/locations only; `run_on_real(code, path)` to compute locally (only masked results
> return); `make_synthetic_twin(path, out)` to develop your code against a safe synthetic twin.

### 3. Convention — `CLAUDE.md`
The prose rule that makes the model *prefer* obsify before it even hits the guard (so the
common path is cooperative, not adversarial). See the "Routing convention" section in
`CLAUDE.md`. The guard is the backstop for when the prose is ignored.

---

## Registering the guard

The guard is a Claude Code **PreToolUse hook**. Add this to `.claude/settings.json`
(`.claude/settings.json` is agent-startup config, so this edit is intentionally left to the
operator — paste it in manually):

```json
"hooks": {
  "PreToolUse": [
    {
      "matcher": "Read",
      "hooks": [
        {
          "type": "command",
          "command": "python -m obsify.guard"
        }
      ]
    }
  ]
}
```

Notes:
- `matcher: "Read"` covers the Read tool. To also gate `@`-mentions and other read-like
  tools, add their tool names as additional matchers (the guard only inspects
  `tool_input.file_path` / `tool_input.path`, so it is safe to attach broadly — it
  no-ops on calls without a path).
- `python` must resolve to the interpreter where obsify is installed. If you use a venv,
  point the command at that interpreter explicitly (e.g. `/path/to/.venv/bin/python -m
  obsify.guard`, or `...\.venv\Scripts\python.exe -m obsify.guard` on Windows). `obsify init`
  fills in the running interpreter's path for you.
- The guard is **defense in depth**, layered *over* any `permissions.deny` rules in
  `.claude/settings.json`. Deny rules are a hard, project-specific stop for named folders;
  the guard is the softer, manifest-driven convention that generalizes to any labelled
  folder and is what ships in the toolkit.

---

## How the layers compose

```
model wants to Read a file
        │
        ▼
[ CLAUDE.md convention ]  ── model prefers scan_pii/twin/run_on_real  (guides)
        │  (if ignored)
        ▼
[ permissions.deny ]      ── hard stop for corpus/ground_truth        (enforces, project-specific)
        │  (if not covered)
        ▼
[ obsify.guard hook ]     ── blocks confidential/restricted per manifest, redirects to obsify   (enforces, general)
        │  (if public)
        ▼
   Read proceeds
```

No single layer is trusted alone. The convention keeps the happy path cooperative; the deny
rules are the non-negotiable floor for the two operator-only directories; the guard makes
the rule generalize to any folder an operator labels, and turns "blocked" into "here's the
safe tool to use instead."

## Honest scope
- The guard classifies by **path**, not content. A sensitive file placed in a `public`
  path is not protected — labelling is the operator's responsibility, and the manifest
  should err toward over-labelling.
- The guard gates the assistant's **tools**; it does not govern the operator's own local
  runs of the harness (deny/hook govern tool calls, not subprocesses you launch yourself).
- `run_on_real` output masking is best-effort, not a guarantee — see `src/sandbox.py`'s
  documented residuals. Return aggregates.
```
