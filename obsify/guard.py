#!/usr/bin/env python
"""obsify PreToolUse guard — the enforcement half of the routing layer.

Registered as a Claude Code PreToolUse hook on read-like tools. On every read it:
  1. reads the tool call (JSON on stdin) to get the target path,
  2. classifies the path against the nearest `.obsify.json` label manifest
     (or a conservative built-in default if none is found),
  3. if the label is CONFIDENTIAL or RESTRICTED, BLOCKS the read (exit 2) and
     writes a redirect message telling the agent to use obsify instead.

This is what makes "when does the model call obsify" deterministic: it doesn't
depend on the model's judgement — a direct read of sensitive data is refused at
the moment of need and the agent is pointed at scan_pii / run_on_real /
make_synthetic_twin. Stdlib only, no heavy imports — it runs on every tool call.

Runnable as a module so the hook command is independent of install location:
    python -m obsify.guard

Exit codes: 0 = allow, 2 = block (stderr is fed back to the agent).
"""

from __future__ import annotations

import fnmatch
import json
import sys
from pathlib import Path

# Conservative built-in default used when no manifest is present: folder names
# that are sensitive by convention. Default posture is "public" for everything
# else (label conservatively via a manifest to widen coverage).
_DEFAULT_RULES = [
    ("*/real/*", "restricted"),
    ("*/sensitive/*", "confidential"),
    ("*/corpus/*", "restricted"),
    ("*/ground_truth/*", "restricted"),
    ("*/data/*", "confidential"),
]
_BLOCKING = {"confidential", "restricted"}
_DEFAULT_TOOLS = ["scan_pii", "run_on_real", "make_synthetic_twin"]


def _find_manifest(path: Path):
    """Walk up from the target path (then cwd) to find the nearest .obsify.json."""
    for start in (path.parent, Path.cwd()):
        for base in (start, *start.parents):
            m = base / ".obsify.json"
            if m.exists():
                try:
                    return json.loads(m.read_text(encoding="utf-8"))
                except Exception:
                    return None
    return None


def _classify(path: str, manifest) -> tuple[str, list[str]]:
    posix = Path(path).as_posix().lower()
    if manifest:
        default = str(manifest.get("default", "public")).lower()
        rules = [(str(r.get("glob", "")).lower(), str(r.get("label", default)).lower())
                 for r in manifest.get("rules", [])]
        tools = manifest.get("obsify_tools", _DEFAULT_TOOLS)
    else:
        default, rules, tools = "public", _DEFAULT_RULES, _DEFAULT_TOOLS
    label = default
    for glob, lab in rules:
        if glob and fnmatch.fnmatch(posix, glob):
            label = lab  # last matching rule wins
    return label, tools


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0  # cannot parse -> never block spuriously
    tool_input = event.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("path") or ""
    if not path:
        return 0
    manifest = _find_manifest(Path(path))
    label, tools = _classify(path, manifest)
    if label in _BLOCKING:
        sys.stderr.write(
            f"BLOCKED by obsify: '{path}' is classified {label.upper()}. Do not read "
            f"it directly - the raw values must not enter your context. Use obsify "
            f"instead: {tools[0]}(path) to see PII types/locations only; "
            f"{tools[1] if len(tools) > 1 else 'run_on_real'}(code, path) to compute "
            f"locally (only masked results return); "
            f"{tools[2] if len(tools) > 2 else 'make_synthetic_twin'}(path, out) to "
            f"develop your code against a safe synthetic twin."
        )
        return 2  # block
    return 0  # allow


if __name__ == "__main__":
    sys.exit(main())
