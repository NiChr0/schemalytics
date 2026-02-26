# Agent: Release & PyPI Publishing

> Load this file when the task involves cutting a new version and publishing to PyPI.
> Always read `AGENTS.md` first for full repo context.
> Always run `testing.md` validation steps before releasing.

---

## Pre-Release Checklist

Complete all of these before bumping the version:

- [ ] All changes are committed and pushed to `main`
- [ ] `ruff check schemalytics/` passes with zero errors
- [ ] End-to-end test against Northwind passes (see `docs/agents/testing.md`)
- [ ] `README.md` reflects current features and CLI flags
- [ ] `CLAUDE.md` is up to date with any structural changes
- [ ] No debugging print statements left in code

---

## Version Bump

Schemalytics uses semantic versioning: `MAJOR.MINOR.PATCH`

- **PATCH** — bug fixes, no API changes
- **MINOR** — new features, backward compatible
- **MAJOR** — breaking changes to CLI or output structure

Version is defined in one place: `pyproject.toml`

```toml
[project]
version = "0.1.1"   # ← bump this
```

Update it, then verify:

```bash
grep 'version' pyproject.toml
python -c "import schemalytics; print(schemalytics.__version__)"  # if __version__ is defined
```

---

## Build

```bash
# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Install build tools if needed
pip install build twine

# Build source distribution + wheel
python -m build

# Verify artifacts
ls dist/
# Expected: schemalytics-X.Y.Z.tar.gz + schemalytics-X.Y.Z-py3-none-any.whl

# Inspect the wheel contents
python -m zipfile -l dist/*.whl | head -30
```

---

## Publish

```bash
# Dry run first (no upload)
twine check dist/*

# Upload to PyPI (requires API token)
twine upload dist/*
# Username: __token__
# Password: pypi-<your-token>
```

After upload, verify:

```bash
# Wait ~60s for PyPI index to update, then:
pip install --index-url https://pypi.org/simple/ schemalytics==X.Y.Z
schemalytics --version
```

---

## Git Tag

After confirming the PyPI release works:

```bash
git tag v0.X.Y
git push origin v0.X.Y
```

---

## GitHub Release Notes Template

```markdown
## Schemalytics vX.Y.Z

### What's New
- <bullet point per feature>

### Bug Fixes
- <bullet point per fix>

### Breaking Changes
- <none> OR <describe breaking change>

### Installation
pip install schemalytics==X.Y.Z

### Full Changelog
https://github.com/NiChr0/schemalytics/compare/vPREV...vX.Y.Z
```

---

## Rollback

If a bad version was published:

```bash
# Yank the release on PyPI (makes it uninstallable but doesn't delete)
# Do this via PyPI web UI: pypi.org → project → Release history → Yank

# Delete local tag
git tag -d vX.Y.Z
git push origin :refs/tags/vX.Y.Z
```