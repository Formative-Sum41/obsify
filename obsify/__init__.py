"""obsify — a local, privacy-preserving PII toolkit exposed over MCP.

Lets an AI assistant work on sensitive files without their raw values ever entering
the model's context: the model reasons over SHAPE (schemas, synthetic twins, masked
feedback) while deterministic local code touches the SUBSTANCE and returns only masked,
aggregated results. Detection is regex + checksums + dictionaries + Presidio's local
NER — no LLM calls, no network at runtime.
"""

from __future__ import annotations

import os
import sys

__version__ = "0.1.1"   # single source of truth — pyproject reads this; bump here to release


def _bootstrap_windows_runtime() -> None:
    """Make the MSVC runtime DLLs findable before spaCy/thinc are imported.

    spaCy's compiled backend (thinc's numpy_ops) links against MSVCP140.dll,
    VCRUNTIME140.dll and VCRUNTIME140_1.dll, normally provided by the Microsoft
    Visual C++ Redistributable. On Windows machines without it (and without admin
    rights to install it), copies of those DLLs can be vendored next to python.exe;
    since Python 3.8 the interpreter directory is not auto-searched for an extension
    module's dependency DLLs, so we add it to the search path explicitly here.

    No-op on non-Windows, and safe if the DLLs are absent (add_dll_directory just
    adds a search path; nothing breaks if it holds nothing relevant).
    """
    if sys.platform != "win32":
        return
    interp_dir = os.path.dirname(sys.executable)
    if os.path.isdir(interp_dir):
        try:
            os.add_dll_directory(interp_dir)
        except (OSError, AttributeError):
            pass


_bootstrap_windows_runtime()
