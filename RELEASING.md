# Releasing WiseQL

A PyPI version is **immutable** — once `X.Y.Z` is uploaded you can only *yank*
it, never overwrite. So bump, verify, then publish.

## 1. Bump the version (two places, keep them in sync)

- `pyproject.toml` → `version = "X.Y.Z"`
- `src/wiseql/__init__.py` → `__version__ = "X.Y.Z"`

Use semver: bug-fix → patch (`0.2.1`), backward-compatible features → minor
(`0.3.0`), breaking → major.

## 2. Verify

```bash
make test                 # full suite green
make build                # clean wheel + sdist into dist/

# smoke-install the built wheel in a throwaway venv (proves a fresh install)
TMP=$(mktemp -d) && uv venv "$TMP/v" -q
uv pip install --python "$TMP/v/bin/python" "$(pwd)/$(ls dist/*.whl)[ai]"
"$TMP/v/bin/wiseql" version     # → WiseQL X.Y.Z
rm -rf "$TMP"
```

Optional dry-run to TestPyPI first:

```bash
uv publish --publish-url https://test.pypi.org/legacy/ --token <TESTpypi-token>
```

## 3. Publish

Use a **project-scoped** PyPI API token (Account → API tokens). Keep it out of
shell history — prefer the env var:

```bash
export UV_PUBLISH_TOKEN=pypi-XXXXXXXX
make publish              # = make build + uv publish
# …or one-off:  uv publish --token pypi-XXXXXXXX
```

## 4. Tag + verify

```bash
git tag vX.Y.Z && git push --tags
uv tool install "wiseql[ai]"     # confirm the published version installs
```

## Notes

- Publish from `main` (merge the release PR first) so the published version
  matches the default branch.
- `dist/` is gitignored — the artifacts are never committed.
- Later: PyPI **Trusted Publishing** (GitHub Actions OIDC) removes the token —
  publishing becomes `git push --tags`.
