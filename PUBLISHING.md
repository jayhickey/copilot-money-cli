# Publishing to PyPI

## One-time setup

1. Create a PyPI account at https://pypi.org/account/register/

2. Create an API token at https://pypi.org/manage/account/token/
   - Scope: Entire account (for first upload) or project-specific after

3. Install build tools:
   ```bash
   pip install build twine
   ```

## Publishing a release

1. Update version in `pyproject.toml`:
   ```toml
   version = "0.2.0"
   ```

2. Build the package:
   ```bash
   python -m build
   ```
   This creates `dist/copilot_money_cli-0.2.0.tar.gz` and `dist/copilot_money_cli-0.2.0-py3-none-any.whl`

3. Upload to PyPI:
   ```bash
   twine upload dist/*
   ```
   Enter your username (`__token__`) and paste your API token as password.

4. Tag the release:
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```

## Testing with TestPyPI first (optional)

```bash
# Upload to test server
twine upload --repository testpypi dist/*

# Install from test server
pip install --index-url https://test.pypi.org/simple/ copilot-money-cli
```

## After publishing

Users can install with:
```bash
pip install copilot-money-cli
```

## Automating releases (GitHub Actions)

Add `.github/workflows/publish.yml`:
```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install build twine
      - run: python -m build
      - run: twine upload dist/*
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_TOKEN }}
```

Then add `PYPI_TOKEN` to your repo's secrets (Settings → Secrets → Actions).
