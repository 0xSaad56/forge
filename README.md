# Forge

**Local-first AI assistant for authorized security research**, built around a private knowledge base and hybrid retrieval.

Forge pairs a local GGUF model (`llama-server`) with on-disk research material: notes, tool references, methodology, optional NVD CVE exports, and optional local [Exploit-DB](https://www.exploit-db.com/) metadata imported via `searchsploit`. Nothing in this repository is a hosted service, a commercial exploit feed, or a guarantee of exploit completeness.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Local-first](https://img.shields.io/badge/privacy-local--first-green.svg)](#security--privacy)

---

## Features

- **Local inference** through OpenAI-compatible `llama-server` (GGUF)
- **Hybrid retrieval**: Chroma (semantic) + SQLite FTS5 (lexical)
- **Rank fusion**: Reciprocal Rank Fusion (RRF), score thresholding, Maximal Marginal Relevance (MMR)
- **Offline UI**: vendored Markdown stack, no CDN requirement
- **SQLite conversation history** on disk
- **Knowledge directories** under `knowledge/` (user-controlled)
- **Optional data helpers** (not required to run chat):
  - Year-scoped NVD 2.0 JSON → Markdown parts
  - Local Exploit-DB CSV → per-entry notes for RAG
- **Security-oriented chat preset** for triage-style Q&A
- **Hardware-aware install** on Arch/BlackArch-style systems (Fish scripts)

---

## Architecture

```text
Browser (http://127.0.0.1:8765)
        │
        ▼
   FastAPI (server.py)
        │
        ├──────────────► llama-server (GGUF, GPU) ──► streamed tokens
        │
        ▼
 Hybrid retrieval (rag.py)
        │
        ├─ Chroma (vectors)
        ├─ SQLite FTS5 (keywords)
        ├─ RRF fusion
        ├─ Min similarity filter
        └─ MMR diversity
                │
                ▼
        Context window + system preset
                │
                ▼
           Local LLM answer
```

**Design choices**

| Concern | Approach |
|---------|----------|
| Privacy | Default LLM endpoint must be loopback unless explicitly overridden |
| Chat VRAM | Query embeddings on CPU; GGUF on GPU |
| Bulk index | Optional CUDA embeddings with small batches; CPU fallback |
| Knowledge | Plain files you own; re-index with `ingest.py` |
| History | SQLite; not sent to any cloud by default |

See [docs/architecture.md](docs/architecture.md) for module-level detail.

---

## Requirements

### Software

- Linux (developed against Arch / BlackArch; other distros need equivalent packages)
- Python 3.11+ (3.12–3.14 used in testing)
- [llama.cpp](https://github.com/ggml-org/llama.cpp) `llama-server` in `PATH`
- Git, curl (for optional NVD fetch)
- Optional: `exploitdb` / `searchsploit` for Exploit-DB sync

### Hardware (tested lab profile)

| Resource | Lab configuration | Notes |
|----------|-------------------|--------|
| GPU | NVIDIA RTX 4060 Laptop 8 GB | GGUF Q4_K_M ~8B class |
| System RAM | 16 GB + swap | Recommended for large ingest |
| Disk | SSD | Knowledge + Chroma + models |

Smaller GPUs work with smaller GGUFs and **CPU** ingest. Larger hosts can raise embed batch sizes via environment variables.

### Models (not included)

Forge does **not** ship weights.

| Role | Example path | Notes |
|------|----------------|-------|
| Chat GGUF | `~/models/<your-model>/*.gguf` | Configure `start-llama.fish` or env |
| Embeddings | FastEmbed `Qwen/Qwen3-Embedding-0.6B-Q` (~1024-d) | Cached under `~/models/forge-embedding` by default |

---

## Quick start

```bash
git clone https://github.com/0xSaad56/forge.git
cd forge
chmod +x *.fish scripts/*.fish scripts/*.py

./install.fish
./setup-swap.fish    # optional; helps 16 GB hosts during large ingest
```

Place a GGUF model where `start-llama.fish` expects it (edit the script if your path differs), then:

```bash
# Terminal 1 — inference
./start-llama.fish

# Terminal 2 — API + UI
./start-chat.fish
```

Open **http://127.0.0.1:8765**.

### Index local knowledge

```bash
# Add .md / .txt under knowledge/{notes,tools,methodology,writeups,cves,exploits}/
./.venv/bin/python ingest.py --force --device cpu
# or, if CUDA ONNX is working on your GPU:
./.venv/bin/python ingest.py --force --device cuda
```

---

## Optional intelligence imports

These scripts **prepare files under `knowledge/`**. They do not replace professional vulnerability management processes.

### NVD (one CVE-ID year)

```bash
fish scripts/fetch-nvd-year.fish 2025
./.venv/bin/python ingest.py --force --device cpu
```

### Exploit-DB (local tree only)

Requires the system Exploit-DB package / `searchsploit` database (commonly `/usr/share/exploitdb`).

```bash
fish scripts/sync-exploitdb.fish
./.venv/bin/python ingest.py --force --device cpu
```

Optional source excerpts (larger index):

```bash
./.venv/bin/python scripts/import-exploitdb.py --include-codes
./.venv/bin/python ingest.py --force --device cpu
```

**Scope:** public Exploit-DB content present on the machine after official updates—not a global private exploit corpus and not a substitute for vendor advisories or authorization scope.

---

## Configuration

Copy `.env.example` to `.env` for local overrides (`.env` is gitignored).

| Variable | Meaning |
|----------|---------|
| `FORGE_LLM_BASE_URL` | Default `http://127.0.0.1:5000/v1` |
| `FORGE_EMBED_MODEL` | FastEmbed model id |
| `FORGE_EMBED_CACHE` | Embedding cache directory |
| `FORGE_INGEST_EMBED_DEVICE` | `cpu` or `cuda` |
| `FORGE_CHUNK_SIZE` / `FORGE_CHUNK_OVERLAP` | Chunking |
| `FORGE_RETRIEVAL_K` | Top chunks into context |

Remote LLM endpoints are **blocked by default** unless `FORGE_ALLOW_REMOTE_LLM=1`.

---

## Repository layout

```text
forge/
├── config.py              # Paths, retrieval, presets
├── server.py              # FastAPI app + chat API
├── rag.py                 # Chunking, embed, hybrid retrieve, ingest
├── llm.py                 # llama-server client + think-tag filter
├── history.py             # SQLite chats + FTS helpers
├── ingest.py              # CLI indexer
├── doctor.py              # Environment checks
├── install.fish           # venv + dependencies
├── start-llama.fish       # GGUF server launcher
├── start-chat.fish        # UI/API launcher
├── setup-swap.fish        # Optional swap helper
├── scripts/
│   ├── fetch-nvd-year.fish
│   ├── sync-exploitdb.fish
│   └── import-exploitdb.py
├── static/                # Offline UI
├── knowledge/             # User data (content gitignored)
├── docs/
└── requirements.txt
```

Runtime directories (`chroma/`, `data/`, `chats/`) are created locally and ignored by Git.

---

## Security & privacy

- Intended for **authorized** testing, education, and lab use only.
- Default binding: **127.0.0.1** for UI and model API.
- Knowledge and chats stay on disk unless you point the LLM at a remote URL.
- Do not commit private assessments, credentials, or target data.
- See [SECURITY.md](SECURITY.md).

---

## Development

```bash
./.venv/bin/python -m py_compile config.py history.py ingest.py llm.py rag.py server.py doctor.py
./.venv/bin/python doctor.py
```

Contribution process: [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Roadmap

- Retrieval evaluation harness and regression fixtures
- Richer document parsers (PDF selectively, structured advisory formats)
- Citation surfaces in the UI (source path / chunk id)
- Optional companion “Forge Intel” exporters (stable JSON/Markdown contract)
- Packaging notes for non-Arch distributions

---

## License

MIT — see [LICENSE](LICENSE).

---

## Disclaimer

Forge is research software. Exploit and CVE material may be incomplete, outdated, or inapplicable to a given target. Always validate against primary sources and operate only within legal authorization.
