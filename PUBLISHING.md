# Publishing obsify to PyPI

Publishing is what turns `pip install "git+https://…"` into the copy-paste
`uvx obsify-mcp` experience. This is the end-to-end checklist. Do it once manually to
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
- [ ] `uvx obsify-mcp` works with **nothing** pre-installed (first run downloads the model).
- [ ] Add the `uvx` config block to a real client (Claude Desktop / Code), restart, confirm the
      five tools appear and `scan_pii` on a sample file returns shape only.

## 7. Tag & release on GitHub

```bash
git tag v0.1.0
git push origin v0.1.0
```

Create a GitHub Release from the tag (this is also the trigger for the automated workflow below).
Write release notes; attach nothing (PyPI holds the artifacts).

## 8. Automate: Trusted Publishing (recommended)

PyPI [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) lets GitHub Actions publish
with **no API token** (short-lived OIDC credentials). One-time setup on PyPI:

1. PyPI → your project → *Publishing* → add a trusted publisher:
   owner `Formative-Sum41`, repo `obsify`, workflow `publish.yml`, environment `pypi`.
2. The included `.github/workflows/publish.yml` then publishes on every GitHub Release.

## 9. Discoverability (post-publish)

- [ ] Add badges to the README (PyPI version, CI status, license).
- [ ] Submit to MCP registries: the official
      [servers list](https://github.com/modelcontextprotocol/servers),
      [awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers), and directories like
      glama.ai / mcp.so / the Cursor MCP directory.
- [ ] Keep a `CHANGELOG.md`; bump the version for every release (never re-upload a version — PyPI
      is immutable per version).
