# Dockerfile — lets Glama (and any container host) start obsify's MCP server so it can
# be introspected. obsify speaks MCP over stdio; a client drives it with JSON-RPC on
# stdin/stdout. The spaCy NER model is loaded LAZILY on the first tool call, so the
# `initialize` + `tools/list` handshake succeeds WITHOUT the ~560 MB model — which is all
# Glama's listing check requires ("start and respond to introspection requests").
#
# This is a convenience/introspection image, not the recommended way to run obsify: for
# real use, install from PyPI (`uvx --from obsify obsify-mcp`) so detection runs on the
# host with local file access. See README.md.
FROM python:3.11-slim

WORKDIR /app
COPY . /app

# Install obsify + its runtime deps from this repo (matches the published package).
RUN pip install --no-cache-dir .

# Speak MCP over stdio. On the first real tool call, obsify downloads the public NER
# model once and caches it (set OBSIFY_AUTO_DOWNLOAD=0 to forbid and vendor it yourself);
# introspection never triggers that, so the container starts fast.
ENTRYPOINT ["obsify-mcp"]
