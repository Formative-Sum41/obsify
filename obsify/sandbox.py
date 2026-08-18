"""Local execution sandbox for compute-to-data.

Runs model-written Python `code` against REAL data in an isolated subprocess, and
returns the RAW captured output to the caller (the MCP layer masks it before it
reaches the model). The data never leaves the machine; only masked results do.

Isolation (best-effort — honest scope for a portfolio build):
  * separate subprocess (its own interpreter/memory);
  * outbound network disabled (socket.create_connection / getaddrinfo blocked)
    so the code cannot exfiltrate;
  * hard wall-clock timeout;
  * a scratch working directory.
`DATA_PATH` is injected so the code can load the real file (pandas/openpyxl are
available).

CONFIRMED RESIDUALS (verified by adversarial tests — do NOT run untrusted code
against secrets without OS-level sandboxing):
  * the static guard is bypassable (e.g. `getattr(os, 'sys'+'tem')`, dynamic
    import tricks) — it stops naive/accidental escapes, not a determined author;
  * the filesystem is NOT jailed — code can READ arbitrary local files;
  * runtime network block covers Python sockets, but a shell escape (os.system)
    could still reach the network.
PRODUCTION HARDENING (containers/gVisor/AppContainer, filesystem jail, syscall
allowlist, generated-code review) is required before untrusted use — this module
is the seam where that goes. The static guard + runtime block are defense-in-depth
speed bumps, not a jail.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Static denylist — raises the bar against escape/exfiltration BEFORE code runs.
# NOT a real jail (a determined author can obfuscate around AST inspection); it is
# a cheap first gate, layered under the runtime network block and (for production)
# OS-level sandboxing.
_BLOCKED_MODULES = {
    "socket", "ssl", "urllib", "http", "ftplib", "smtplib", "poplib", "imaplib",
    "telnetlib", "requests", "httpx", "urllib3", "aiohttp", "subprocess", "ctypes",
    "multiprocessing", "webbrowser", "importlib", "pip",
}
_BLOCKED_CALLS = {"eval", "exec", "compile", "__import__", "breakpoint"}
_BLOCKED_ATTRS = {  # module.attr forms
    ("os", "system"), ("os", "popen"), ("os", "remove"), ("os", "unlink"),
    ("os", "rmdir"), ("os", "removedirs"), ("os", "execv"), ("os", "execve"),
    ("os", "spawnv"), ("shutil", "rmtree"), ("shutil", "move"), ("shutil", "copy"),
}


def static_guard(code: str) -> str | None:
    """Return a reason string if `code` is rejected, else None."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"syntax error: {exc.msg}"
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = (node.module if isinstance(node, ast.ImportFrom) else None) or ""
            names = [mod] + [a.name for a in getattr(node, "names", [])]
            for n in names:
                if n.split(".")[0] in _BLOCKED_MODULES:
                    return f"blocked import: {n.split('.')[0]}"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _BLOCKED_CALLS:
                return f"blocked call: {node.func.id}"
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if (node.value.id, node.attr) in _BLOCKED_ATTRS:
                return f"blocked op: {node.value.id}.{node.attr}"
        # file writes: open(..., 'w'/'a'/'x'/'wb'...)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                mode = str(node.args[1].value)
                if any(m in mode for m in ("w", "a", "x", "+")):
                    return "blocked op: open() in write mode"
    return None

_PREAMBLE = '''\
import socket as _socket
def _no_net(*a, **k):
    raise OSError("network is disabled in the compute-to-data sandbox")
_socket.create_connection = _no_net
_socket.getaddrinfo = _no_net
DATA_PATH = {data_path!r}
'''


@dataclass
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool


def execute(code: str, data_path: str, timeout: int = 30) -> SandboxResult:
    """Execute `code` (with DATA_PATH bound to `data_path`) in an isolated
    subprocess. Returns raw stdout/stderr — masking is the caller's job. Code that
    fails the static guard is rejected without running."""
    reason = static_guard(code)
    if reason is not None:
        return SandboxResult(-2, "", f"[sandbox] rejected by static guard: {reason}", False)
    script = _PREAMBLE.format(data_path=str(data_path)) + "\n" + code
    with tempfile.TemporaryDirectory(prefix="obsify_sbx_") as work:
        script_path = Path(work) / "job.py"
        script_path.write_text(script, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=work, capture_output=True, text=True, timeout=timeout,
            )
            return SandboxResult(proc.returncode, proc.stdout, proc.stderr, False)
        except subprocess.TimeoutExpired as exc:
            return SandboxResult(-1, exc.stdout or "", (exc.stderr or "")
                                 + f"\n[sandbox] timed out after {timeout}s", True)
