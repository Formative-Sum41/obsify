"""Tests for the routing layer: the PreToolUse guard (obsify/guard.py) and the
`obsify init` scaffold (obsify/init.py).

Guard: classification (manifest + built-in defaults, last-rule-wins), and the
block/allow decision end to end via main() with a temp manifest so the result does
not depend on the cwd. Init: non-destructive contract — owns .obsify.json, opt-in and
idempotent CLAUDE.md, never clobbers existing content, emits the module-form hook.

Run: python tests/test_routing.py
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import obsify.guard as G      # noqa: E402
import obsify.init as I       # noqa: E402


# ------------------------------------------------------------------- guard ----

def test_classify_builtin_defaults_block_sensitive_folders():
    # No manifest -> conservative built-in rules apply.
    assert G._classify("/x/data/y.xlsx", None)[0] == "confidential"
    assert G._classify("/x/corpus/y.pdf", None)[0] == "restricted"
    assert G._classify("/x/src/config.py", None)[0] == "public"


def test_classify_manifest_last_rule_wins():
    manifest = {
        "default": "public",
        "rules": [
            {"glob": "*/mixed/*", "label": "confidential"},
            {"glob": "*/mixed/public/*", "label": "public"},  # later, more specific
        ],
    }
    assert G._classify("/a/mixed/secret.xlsx", manifest)[0] == "confidential"
    assert G._classify("/a/mixed/public/ok.xlsx", manifest)[0] == "public"


def _run_guard(payload: dict) -> tuple[int, str]:
    """Drive guard.main() with a fake stdin/stderr; return (exit_code, stderr)."""
    old_in, old_err = sys.stdin, sys.stderr
    sys.stdin = io.StringIO(json.dumps(payload))
    sys.stderr = io.StringIO()
    try:
        rc = G.main()
        return rc, sys.stderr.getvalue()
    finally:
        sys.stdin, sys.stderr = old_in, old_err


def test_guard_blocks_restricted_and_redirects():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / ".obsify.json").write_text(json.dumps({
            "default": "public",
            "rules": [{"glob": "*/secret/*", "label": "restricted"}],
        }), encoding="utf-8")
        target = root / "secret" / "book.xlsx"
        rc, err = _run_guard({"tool_input": {"file_path": str(target)}})
        assert rc == 2, "restricted path must be blocked (exit 2)"
        assert "BLOCKED by obsify" in err
        assert "scan_pii" in err and "run_on_real" in err  # redirect to the tools


def test_guard_allows_public_silently():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / ".obsify.json").write_text(json.dumps({
            "default": "public", "rules": [{"glob": "*/secret/*", "label": "restricted"}],
        }), encoding="utf-8")
        target = root / "open" / "notes.txt"
        rc, err = _run_guard({"tool_input": {"file_path": str(target)}})
        assert rc == 0 and err == ""


def test_guard_never_blocks_on_malformed_or_pathless_input():
    assert _run_guard({})[0] == 0                       # no tool_input
    assert _run_guard({"tool_input": {}})[0] == 0       # no path


# -------------------------------------------------------------------- init ----

def test_init_owns_and_writes_manifest_idempotently():
    with tempfile.TemporaryDirectory() as d:
        target = Path(d)
        msg1 = I._write_manifest(target, force=False)
        assert (target / ".obsify.json").exists() and "wrote" in msg1
        # valid JSON with the expected shape
        m = json.loads((target / ".obsify.json").read_text(encoding="utf-8"))
        assert m["default"] == "public" and m["rules"]
        # re-run without force -> untouched
        assert "already exists" in I._write_manifest(target, force=False)
        # with force -> overwrite
        assert "overwrote" in I._write_manifest(target, force=True)


def test_init_claude_md_is_opt_in_idempotent_and_non_clobbering():
    with tempfile.TemporaryDirectory() as d:
        target = Path(d)
        existing = "# My Project\n\nExisting user rules.\n"
        (target / "CLAUDE.md").write_text(existing, encoding="utf-8")
        # first append
        I._maybe_claude_md(target)
        body = (target / "CLAUDE.md").read_text(encoding="utf-8")
        assert existing.strip() in body, "must not clobber existing content"
        assert I._CLAUDE_BEGIN in body and I._CLAUDE_END in body
        # idempotent second run
        assert "already has the obsify block" in I._maybe_claude_md(target)
        assert body.count(I._CLAUDE_BEGIN) == 1  # exactly one block


def test_init_hook_snippet_uses_module_form():
    snip = I._hook_snippet("python")
    assert "-m obsify.guard" in snip
    assert snip.strip().startswith("{") and "PreToolUse" in snip


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
            except Exception as e:  # noqa: BLE001
                failures += 1
                print(f"ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{failures} failure(s)")
    sys.exit(1 if failures else 0)
