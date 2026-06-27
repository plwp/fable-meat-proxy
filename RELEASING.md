# Releasing

`fable-meat-proxy` publishes to PyPI via **Trusted Publishing** (OIDC) — no API
tokens are stored anywhere. Pushing a `v*` tag builds the artifacts and uploads
them through `.github/workflows/release.yml`.

## One-time setup (per project)

1. Create the project's Trusted Publisher on PyPI **before the first release**
   (the project doesn't exist on PyPI yet, so use the "pending publisher" form):

   - Go to https://pypi.org/manage/account/publishing/
   - Add a new **pending** publisher with:
     - **PyPI Project Name:** `fable-meat-proxy`
     - **Owner:** `plwp`
     - **Repository name:** `fable-meat-proxy`
     - **Workflow name:** `release.yml`
     - **Environment name:** `pypi`

2. In the GitHub repo, create an **environment** named `pypi`
   (Settings → Environments → New environment). Optionally add required reviewers
   so a human approves each publish.

## Cutting a release

1. Bump the version in `pyproject.toml` (and `__version__` in
   `src/fable_meat_proxy/__init__.py`) and update `CHANGELOG.md`.
2. Commit, then tag and push:

   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

3. The `Release` workflow builds, runs `twine check`, and publishes to PyPI.

> Versions on PyPI are immutable — you can't re-upload `0.1.0`; bump to `0.1.1`.

## Manual fallback

If you ever need to publish by hand (e.g. before Trusted Publishing is set up):

```bash
python -m build
python -m twine upload dist/*
```
