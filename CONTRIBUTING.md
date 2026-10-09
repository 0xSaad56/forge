# Contributing to Forge

Thank you for considering a contribution.

## Ground rules

- Local-first and privacy-preserving defaults must remain intact unless the change is opt-in and documented.
- Do not commit model weights, Chroma indexes, SQLite databases, or personal knowledge bases.
- Do not contribute content intended solely for unauthorized computer intrusion.
- Keep changes focused; large unrelated refactors are hard to review.

## Development setup

```bash
git clone https://github.com/0xSaad56/forge.git
cd forge
./install.fish
./.venv/bin/python doctor.py
./.venv/bin/python -m py_compile config.py history.py ingest.py llm.py rag.py server.py doctor.py
```

Optional UI check: run `llama-server` separately, then `./start-chat.fish`.

## Pull requests

1. Fork the repository and create a branch from `main`.
2. Make your change with clear commits (Conventional Commit messages preferred: `feat:`, `fix:`, `docs:`, `chore:`).
3. Update documentation when behavior or configuration changes.
4. Open a PR with:
   - Summary of the change
   - Test plan (commands you ran)
   - Notes on hardware assumptions (GPU/CPU) if relevant

## Coding guidelines

- Prefer explicit errors over silent failure in ingest and retrieval paths.
- Avoid new mandatory network calls at runtime for chat.
- Vendor frontend assets under `static/vendor/` rather than adding CDN dependencies.
- Match existing module boundaries: `rag.py` retrieval/index, `llm.py` model client, `history.py` persistence, `server.py` HTTP API.

## Reporting bugs

Use GitHub Issues for defects and feature ideas. Include OS, Python version, GPU (if any), and a minimal reproduction. For security-sensitive reports, see [SECURITY.md](SECURITY.md).
