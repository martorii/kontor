# kontor

## Development

Prerequisites: [uv](https://docs.astral.sh/uv/) and [gitleaks](https://github.com/gitleaks/gitleaks) (`brew install gitleaks`).

```bash
uv sync
uv run pre-commit install
make lint typecheck test
```
