# Dockerfile — a containerized run of obsify's MCP server, for hosts that prefer a
# container over uvx/pipx. obsify speaks MCP over stdio; a client drives it with JSON-RPC
# on stdin/stdout. The spaCy NER model is loaded LAZILY on the first tool call, so the
# `initialize` + `tools/list` handshake starts fast, WITHOUT the ~560 MB model.
#
# Not the recommended path for real use: install from PyPI (`uvx --from obsify obsify-mcp`)
# so detection runs on the host with local file access. See README.md.
FROM python:3.11-slim

WORKDIR /app
COPY . /app

# Install obsify + its runtime deps from this repo (matches the published package).
RUN pip install --no-cache-dir .

# Speak MCP over stdio. On the first real tool call, obsify downloads the public NER
# model once and caches it (set OBSIFY_AUTO_DOWNLOAD=0 to forbid and vendor it yourself);
# introspection never triggers that, so the container starts fast.
#
# CMD (not ENTRYPOINT) so a host that supplies its own run command maps cleanly to it;
# `docker run <image>` still starts the server on its own.
CMD ["obsify-mcp"]
