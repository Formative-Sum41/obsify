"""MCP protocol integration tests — the layer the unit tests can't reach.

These launch the REAL server (`python -m obsify.mcp_server`) as a subprocess and
speak the MCP protocol to it over stdio via the official client SDK — the same path
a client like Claude uses. They confirm the server starts, registers all five tools
with valid input schemas, and that tool calls round-trip through JSON-RPC returning
correct results (including shape-only scan output end to end).

Heavier than the unit tests (each spins a subprocess; the scan test loads the NER
model once). OBSIFY_AUTO_DOWNLOAD=0 is set so a missing model fails fast instead of
downloading during a test run.

Run: python tests/test_mcp_protocol.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import obsify.make_corpus as MC          # noqa: E402  (obsify first -> DLL bootstrap)
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client             # noqa: E402

_REPO = str(Path(__file__).resolve().parents[1])
_TOOLS = {"scan_pii", "redact_text", "verify_value_free", "make_synthetic_twin", "run_on_real"}


def _server():
    env = os.environ.copy()
    env["PYTHONPATH"] = _REPO + os.pathsep + env.get("PYTHONPATH", "")
    env["OBSIFY_AUTO_DOWNLOAD"] = "0"   # never download during tests
    env["PYTHONUNBUFFERED"] = "1"
    return StdioServerParameters(command=sys.executable,
                                 args=["-m", "obsify.mcp_server"], env=env)


def _result_value(result):
    """Pull the tool's return value out of an MCP CallToolResult."""
    sc = getattr(result, "structuredContent", None)
    if sc:
        # FastMCP-style servers wrap a non-dict return under {"result": ...}
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    parts = [c.text for c in result.content if getattr(c, "type", None) == "text"]
    txt = "".join(parts)
    try:
        return json.loads(txt)
    except Exception:
        return txt


async def _list_and_light_calls():
    async with stdio_client(_server()) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            listed = await s.list_tools()
            clean = await s.call_tool("verify_value_free",
                                      {"text": "types and counts only", "terms": ["Jane Roe"]})
            leak = await s.call_tool("verify_value_free",
                                     {"text": "contact Jane Roe", "terms": ["Jane Roe"]})
            return listed, _result_value(clean), _result_value(leak)


def test_server_registers_all_tools_with_schemas():
    listed, clean, leak = asyncio.run(_list_and_light_calls())
    names = {t.name for t in listed.tools}
    assert _TOOLS <= names, f"missing tools over the protocol: {_TOOLS - names}"
    for t in listed.tools:
        schema = t.input_schema
        assert isinstance(schema, dict) and schema.get("type") == "object", \
            f"tool {t.name} has no object input schema"
        assert t.description, f"tool {t.name} has no description"
    # a real tool call round-tripped through JSON-RPC and returned the right answer
    assert clean.get("value_free") is True, clean
    assert leak.get("value_free") is False, leak


async def _scan_over_protocol(path: str):
    async with stdio_client(_server()) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            return _result_value(await s.call_tool("scan_pii", {"path": path}))


def test_scan_pii_end_to_end_shape_only():
    with tempfile.TemporaryDirectory() as d:
        info = MC.build_corpus(d)
        docx = next(f for f in info["files"] if f.endswith(".docx"))
        out = asyncio.run(_scan_over_protocol(docx))
        assert out["files_read"] == 1, out
        assert out["counts_by_type"], "scan should detect PII types in the docx"
        blob = json.dumps(out).lower()
        planted = [x for vals in info["planted"].values()
                   for x in (vals if isinstance(vals, list) else [vals])]
        for v in planted:
            assert v.lower() not in blob, f"scan_pii leaked {v!r} over the protocol"


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
