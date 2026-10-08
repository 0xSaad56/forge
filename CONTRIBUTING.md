# Contributing to Forge

Thanks for contributing.

## Before opening a change

1. Read the README and architecture documentation.
2. Keep changes focused and explain why they are needed.
3. Never commit credentials, tokens, local databases, model files, chat history, or private research material.
4. Prefer reproducible changes that work on a clean checkout.

## Development checks

Run Python syntax checks before committing:

```bash
python -m py_compile *.py
```

If you modify the frontend, verify the application starts and the affected workflow still works locally.

## Commit style

Use concise, descriptive commit messages such as:

- `feat: add ...`
- `fix: prevent ...`
- `refactor: isolate ...`
- `docs: explain ...`
- `test: cover ...`

## Pull requests

Describe:

- what changed;
- why it changed;
- how it was tested; and
- any compatibility or security implications.
