"""`obsify init` — one-command adoption scaffold.

Sets up the obsify routing layer in a target project the polite way: it *owns* and
writes only the file that is unambiguously obsify's — `.obsify.json` (the label
manifest) — and for everything that touches the user's OWN config it prints a snippet
for them to paste rather than editing their files behind their back.

Design principle (respect the user's config):
  * `.obsify.json`            → written by init (obsify owns it; never overwritten
                                without --force).
  * `.claude/settings.json`   → NEVER auto-edited. init prints the PreToolUse hook
                                registration snippet for the operator to paste. This is
                                agent-startup config that runs code; it is the operator's
                                to change, not a tool's.
  * `CLAUDE.md`               → OPT-IN only. By default init just prints the routing
                                convention for the user to paste into their own CLAUDE.md.
                                With --with-claude-md it appends an obsify-marked block
                                (idempotent; wrapped in BEGIN/END markers so it is easy to
                                find and remove; never clobbers existing content).

CLI: python -m obsify.init [--dir PATH] [--with-claude-md] [--force] [--python PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# The guard ships inside the package and is run as a module (`python -m obsify.guard`),
# so the hook command is independent of install location (works pip-installed or from a
# clone) — no filesystem path to resolve or get wrong.
_GUARD_MODULE = "obsify.guard"

_MANIFEST_TEMPLATE = {
    "$schema": "obsify label manifest - drives the PreToolUse guard (obsify.guard)",
    "default": "public",
    "rules": [
        {"glob": "*/real/*", "label": "restricted"},
        {"glob": "*/sensitive/*", "label": "confidential"},
        {"glob": "*/corpus/*", "label": "restricted"},
        {"glob": "*/ground_truth/*", "label": "restricted"},
        {"glob": "*/data/*", "label": "confidential"},
    ],
    "labels": {
        "public": "read freely",
        "confidential": "no direct read - use obsify (scan_pii / run_on_real / make_synthetic_twin)",
        "restricted": "no direct read, no raw output - obsify with masked/aggregated results only",
    },
    "obsify_tools": ["scan_pii", "run_on_real", "make_synthetic_twin"],
    "twin_dir": "twin",
}

# Marker-wrapped block appended to CLAUDE.md only with --with-claude-md (idempotent).
_CLAUDE_BEGIN = "<!-- BEGIN obsify routing convention (managed by `obsify init`) -->"
_CLAUDE_END = "<!-- END obsify routing convention -->"
_CLAUDE_BLOCK = f"""{_CLAUDE_BEGIN}
## Routing convention (obsify) - when to use the toolkit
Sensitive files are classified by `.obsify.json` and enforced by a PreToolUse guard
(`python -m obsify.guard`). Do not treat this as a judgement call:
- **Never `Read` a file labelled `confidential` or `restricted`.** A blocked read means
  "use obsify," not "try another path."
- `scan_pii(path)` - see PII types / locations / counts only, never values.
- `make_synthetic_twin(path, out)` - develop code against a schema-faithful, faked,
  leak-verified twin.
- `run_on_real(code, path)` - compute locally; only masked, aggregated output returns.
  Return AGGREGATES; output masking is best-effort defense-in-depth, not a guarantee.
- `public` files are read normally. Full convention: `docs/obsify_routing.md`.
{_CLAUDE_END}"""


def _hook_snippet(python: str) -> str:
    """The PreToolUse registration block for .claude/settings.json (printed, not written)."""
    # Normalize an interpreter *path* to forward slashes so the command reads cleanly on
    # Windows (both separators work in hook commands). Leave non-path values (a bare
    # `python`, or a launcher with args) exactly as given.
    py = Path(python).as_posix() if Path(python).exists() else python
    block = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Read",
                    "hooks": [
                        {"type": "command",
                         "command": f"{py} -m {_GUARD_MODULE}"},
                    ],
                }
            ]
        }
    }
    return json.dumps(block, indent=2)


def _write_manifest(target: Path, force: bool) -> str:
    dest = target / ".obsify.json"
    if dest.exists() and not force:
        return f"[init] .obsify.json already exists - left untouched (use --force to overwrite): {dest}"
    dest.write_text(json.dumps(_MANIFEST_TEMPLATE, indent=2) + "\n", encoding="utf-8")
    verb = "overwrote" if dest.exists() and force else "wrote"
    return f"[init] {verb} label manifest: {dest}"


def _maybe_claude_md(target: Path) -> str:
    """Append the convention block to CLAUDE.md, idempotently. Opt-in path only."""
    dest = target / "CLAUDE.md"
    existing = dest.read_text(encoding="utf-8") if dest.exists() else ""
    if _CLAUDE_BEGIN in existing:
        return f"[init] CLAUDE.md already has the obsify block - left untouched: {dest}"
    sep = "" if existing.endswith("\n\n") or existing == "" else ("\n" if existing.endswith("\n") else "\n\n")
    dest.write_text(existing + sep + _CLAUDE_BLOCK + "\n", encoding="utf-8")
    where = "created" if not existing else "appended obsify block to"
    return f"[init] {where} CLAUDE.md (marker-wrapped, removable): {dest}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m obsify.init",
        description="Scaffold the obsify routing layer in a project (opt-in, non-destructive).")
    ap.add_argument("--dir", default=".", help="target project directory (default: cwd)")
    ap.add_argument("--with-claude-md", action="store_true",
                    help="OPT-IN: append the routing convention to the project's CLAUDE.md "
                         "(idempotent, marker-wrapped). Default is to print it for you to paste.")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing .obsify.json (default: leave it untouched)")
    ap.add_argument("--python", default=sys.executable,
                    help="interpreter path used in the hook command (default: this interpreter)")
    args = ap.parse_args(argv)

    target = Path(args.dir).resolve()
    if not target.is_dir():
        print(f"[init] error: not a directory: {target}", file=sys.stderr)
        return 2

    print(f"[init] obsify routing layer -> {target}\n")

    # 1. Manifest — obsify owns this file, safe to write.
    print(_write_manifest(target, args.force))

    # 2. CLAUDE.md — user's file. Opt-in append, else print for manual paste.
    print()
    if args.with_claude_md:
        print(_maybe_claude_md(target))
    else:
        print("[init] CLAUDE.md convention (NOT written - your file). Paste this into your "
              "CLAUDE.md, or re-run with --with-claude-md to append it automatically:\n")
        print(_CLAUDE_BLOCK)

    # 3. settings.json — user's agent config. NEVER auto-edited; print snippet to paste.
    print("\n[init] Register the guard hook: add this to `.claude/settings.json` (top level, "
          "sibling of \"permissions\"). This file is intentionally NOT edited for you - it is "
          "agent-startup config that runs code, so it is yours to change:\n")
    print(_hook_snippet(args.python))
    print("  (the guard runs as a module - `python -m obsify.guard` - so this works whether "
          "obsify is pip-installed or run from a clone, as long as `obsify` is importable "
          "by that interpreter.)")

    print("\n[init] done. Next: (1) paste the hook snippet into .claude/settings.json, "
          "(2) restart the session so the hook loads, (3) label your sensitive folders in "
          ".obsify.json. Full convention: docs/obsify_routing.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
