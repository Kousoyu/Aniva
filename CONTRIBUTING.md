# Contributing

Thanks for helping with Aniva.

## Before you start

- Read `README.md`
- Read the relevant phase notes in `docs/`
- Keep changes diagnostic-focused unless a mechanism change is explicitly planned

## Development

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q
```

## Guidelines

- Keep experiments and summaries separate from core runtime changes when possible
- Do not commit large raw event CSVs unless they are explicitly required
- Prefer small, readable evidence-chain updates over broad refactors
- Do not change mechanisms unless the task explicitly calls for it

## Pull requests

- Summarize the intent and the evidence impact
- Include test output when relevant
- Link to the phase docs that motivated the change
