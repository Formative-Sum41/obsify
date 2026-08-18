"""Tests for the first-run model auto-download (obsify/nlp.ensure_model).

Verifies the fast no-op path (model present -> no network) and the air-gapped path
(OBSIFY_AUTO_DOWNLOAD=0 + missing model -> clear RuntimeError, no download attempt).
Neither test triggers a real ~560 MB download.

Run: python tests/test_model.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import obsify.nlp as N  # noqa: E402  (import first: runs the Windows DLL bootstrap)
import spacy.util       # noqa: E402  (safe only after obsify's bootstrap has run)


def test_ensure_model_noop_when_present(monkeypatch=None):
    # The model IS installed in the test env, so ensure_model must return without
    # attempting a download. Guard that by making any subprocess call fail loudly.
    import subprocess
    orig_run = subprocess.run
    subprocess.run = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("ensure_model tried to download when the model was present"))
    try:
        N.ensure_model()  # should be a silent no-op
    finally:
        subprocess.run = orig_run


def test_ensure_model_disabled_raises_when_missing():
    # Simulate: model missing + auto-download forbidden -> raise with manual command,
    # and never shell out.
    import subprocess
    orig_is_pkg = spacy.util.is_package
    orig_run = subprocess.run
    orig_env = os.environ.get("OBSIFY_AUTO_DOWNLOAD")
    spacy.util.is_package = lambda name: False
    subprocess.run = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("must not download when OBSIFY_AUTO_DOWNLOAD=0"))
    os.environ["OBSIFY_AUTO_DOWNLOAD"] = "0"
    try:
        raised = False
        try:
            N.ensure_model()
        except RuntimeError as e:
            raised = True
            assert "spacy download" in str(e), "error should give the manual install command"
        assert raised, "missing model + auto-download disabled must raise"
    finally:
        spacy.util.is_package = orig_is_pkg
        subprocess.run = orig_run
        if orig_env is None:
            os.environ.pop("OBSIFY_AUTO_DOWNLOAD", None)
        else:
            os.environ["OBSIFY_AUTO_DOWNLOAD"] = orig_env


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
