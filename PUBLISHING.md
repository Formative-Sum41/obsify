# Publishing obsify to PyPI

Publishing is what turns `pip install "git+https://…"` into the copy-paste
`uvx --from obsify obsify-mcp` experience. This is the end-to-end checklist. Do it once manually to
understand it, then let the GitHub Actions workflow (bottom) do it on every release.

## 0. One-time prerequisites

- A [PyPI account](https://pypi.org/account/register/) with **2FA enabled**.
- A [TestPyPI account](https://test.pypi.org/account/register/) (separate site, for rehearsal).
- Build/upload tools: `pip install build twine`.
- `uv` installed (to verify the `uvx` path): https://docs.astral.sh/uv/.

## 1. Pre-flight — fill placeholders & confirm green

- [ ] **Claim the name.** Search https://pypi.org/project/obsify/ — if taken, pick another
      distribution name (e.g. `obsify-mcp`) and update `[project].name` in `pyproject.toml`.
      The MCP command stays `obsify-mcp` regardless (it's a `[project.scripts]` entry).
- [x] `[project.urls]` and the README git-install line point at `github.com/Formative-Sum41/obsify`.
- [x] `authors` in `pyproject.toml` and the `LICENSE` copyright holder set to `Erfan Hardanian`.
- [x] `CHANGELOG.md` present; README badges added.
- [ ] Set the release version in `pyproject.toml` **and** `obsify/__init__.py` (`__version__`) —
      keep them in sync. Use [semver](https://semver.org/) (start at `0.1.0`).
- [ ] `pytest tests/` is green locally.
- [ ] README, SECURITY.md claims match the code (no over-promising).

## 2. Build

```bash
rm -rf dist build *.egg-info
python -m build            # produces dist/obsify-<ver>.tar.gz (sdist) + …-py3-none-any.whl
```

## 3. Validate the artifacts

```bash
twine check dist/*         # metadata/README render check
```

- [ ] **Confirm no data files leaked into the sdist.** `tar -tzf dist/obsify-*.tar.gz` and eyeball
      the file list — only source, tests, docs, packaging. No `real/`, `data/`, `reports/`, no
      `.venv`, no `__pycache__`. (obsify ships pure source, so this should be clean — verify anyway.)

## 4. Rehearse on TestPyPI

```bash
twine upload -r testpypi dist/*
# in a CLEAN venv:
pip install -i https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ obsify
python -m spacy download en_core_web_lg
obsify-mcp        # starts and waits on stdio -> Ctrl-C
```

The `--extra-index-url` lets dependencies resolve from real PyPI while obsify comes from TestPyPI.

## 5. Publish to PyPI

```bash
twine upload dist/*
```

Authenticate with a **scoped API token** (create at PyPI → Account → API tokens; use
`__token__` as the username), or use Trusted Publishing (§8).

## 6. Verify the real thing

- [ ] `pipx install obsify && obsify-mcp` works from a clean machine.
- [ ] `uvx --from obsify obsify-mcp` works with **nothing** pre-installed (first run downloads the model).
- [ ] Add the `uvx` config block to a real client (Claude Desktop / Code), restart, confirm the
      five tools appear and `scan_pii` on a sample file returns shape only.

## 7. Tag & release on GitHub

```bash
git tag v0.1.0
git push origin v0.1.0
```

Create a GitHub Release from the tag (this is also the trigger for the automated workflow below).
Write release notes; attach nothing (PyPI holds the artifacts).

## 8. Automate: Trusted Publishing (recommended, for future releases)

PyPI [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) lets GitHub Actions publish
with **no API token** (short-lived OIDC credentials). Repo side is DONE: `.github/workflows/publish.yml`
runs on every GitHub Release and the `pypi` GitHub environment exists. The **one-time PyPI step**:

1. PyPI → your `obsify` project → *Settings* → *Publishing* → **Add a new publisher** (GitHub):
   owner `Formative-Sum41`, repo `obsify`, workflow `publish.yml`, environment `pypi`.

After that, cutting a GitHub Release (§7) publishes automatically — no token.

### Releasing a new version

Three version strings must move together, or the registry ends up pinned to an old release while
PyPI moves on. Bump all three, then publish to both targets:

1. **Bump the version in all three places (keep in sync):**
   - `obsify/__init__.py` → `__version__` (single source; `pyproject.toml` reads it via hatchling).
   - `server.json` → **both** the top-level `"version"` **and** `packages[0].version`.
2. Update `CHANGELOG.md`; commit + push; ensure CI is green.
3. **PyPI (automated):** `git tag vX.Y.Z && git push origin vX.Y.Z`, then create a **GitHub Release**
   from that tag. `publish.yml` builds and uploads to PyPI via OIDC. (PyPI versions are immutable —
   always bump.)
4. **MCP Registry (manual, one command):** from the repo root, `mcp-publisher publish` (see §9).
   Registry versions are immutable too, so this must be the version you just bumped.

## 9. Publish to the official MCP Registry

The [official registry](https://registry.modelcontextprotocol.io) is the source most third-party
directories (mcp.so, Cursor, …) ingest from. obsify publishes via the `mcp-publisher` CLI, driven by
`server.json` (already present + schema-valid) and the `<!-- mcp-name: … -->` marker in `README.md`
(which proves PyPI-package ownership — keep it in the packaged description).

**One-time setup:**
1. Get the CLI: download the `mcp-publisher` binary from
   [modelcontextprotocol/registry releases](https://github.com/modelcontextprotocol/registry/releases/latest)
   (or `go install github.com/modelcontextprotocol/registry/cmd/mcp-publisher@latest`).
2. `mcp-publisher login github` — GitHub device-flow; authorize as the account that owns the repo
   (`Formative-Sum41`). This authorizes the `io.github.Formative-Sum41/*` namespace. Login persists.

**Every release (after the PyPI step above):**
```bash
mcp-publisher validate     # optional: schema-check server.json first
mcp-publisher publish       # reads ./server.json, publishes the bumped version
```
Verify: `curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=obsify"` shows the new version.

## 10. Discoverability (post-publish)

Done for 0.1.2 — recorded here as the standing checklist:

- [x] README badges (PyPI version, CI status, license).
- [x] **Official MCP Registry** — published as `io.github.Formative-Sum41/obsify` (§9).
- [x] **[punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers)** — PR
      adding obsify to the 🔒 Security category. Their bot requires a **Glama listing + score badge**
      (submit at https://glama.ai/mcp/servers; a `Dockerfile` in this repo lets Glama's start +
      introspection check pass), then the entry gets a
      `[![…](https://glama.ai/mcp/servers/OWNER/REPO/badges/score.svg)](…)` badge.
- [x] **[mcpservers.org](https://mcpservers.org/submit)** — web-form submission (free tier; the site
      backs `wong2/awesome-mcp-servers`, which does **not** take PRs).
- [ ] Auto-ingest (no action): glama.ai (from the awesome PR) and mcp.so (from the official registry).
- [x] Keep a `CHANGELOG.md`; bump the version every release (never re-upload — PyPI/registry are
      immutable per version).
