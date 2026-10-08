# Forge

> A local-first AI security research assistant with hybrid retrieval and private knowledge augmentation.

Forge runs a local language model and retrieves relevant material from a user-controlled local knowledge base. It combines semantic vector search with SQLite FTS5/BM25 retrieval, Reciprocal Rank Fusion (RRF), score filtering, and Maximal Marginal Relevance (MMR).

> **Status:** Active development / early public release.

## What Forge does

- Local GGUF inference through `llama-server`
- Local embeddings with Qwen3-Embedding-4B support
- Hybrid retrieval: Chroma + SQLite FTS5/BM25
- Reciprocal Rank Fusion (RRF)
- Maximal Marginal Relevance (MMR)
- Local SQLite conversation history
- Local frontend assets; no CDN dependency
- Security-focused assistant preset
- Extensible local knowledge directories

## Architecture

```text
                         Forge
                           |
          +----------------+----------------+
          |                                 |
          v                                 v
       FastAPI                         llama-server
          |                                 |
          v                                 v
   Hybrid Retrieval                    Local LLM
          |
   +------+------+------+------+
   |      |      |      |      |
 Chroma FTS5   RRF   Score   MMR
   |      |      |      |      |
   +------+------+------+------+
                 |
                 v
          Retrieved Context
                 |
                 v
             Local LLM
```

## Security-intelligence architecture

Forge intentionally does **not** contain a CVE/exploit feed collector. A separate project, planned as **Forge Intel**, will collect and normalize vulnerability, exploit, detection, and threat-intelligence data and export it in a stable format for Forge to ingest.

See [`docs/intelligence-contract.md`](docs/intelligence-contract.md).

## Repository layout

```text
forge/
├── config.py
├── history.py
├── ingest.py
├── llm.py
├── rag.py
├── server.py
├── static/
├── knowledge/
│   ├── cves/
│   ├── methodology/
│   ├── notes/
│   ├── tools/
│   └── writeups/
├── docs/
├── tests/
└── .github/
```

Runtime state such as Chroma indexes, SQLite databases, chat history, virtual environments, caches, and local model files is intentionally excluded from version control.

## Requirements

- Linux
- Python 3
- `llama-server`
- A compatible GGUF model
- Sufficient RAM/VRAM for the selected model
- Qwen3-Embedding-4B or another configured embedding model

## Install

```fish
cd ~
unzip forge.zip
cd ~/forge
./install.fish
./setup-swap.fish
```

The included installation script is designed around the current Linux/Arch workflow. Other environments may require equivalent package installation steps.

## Models

Forge does not ship model weights.

The current launcher expects a GGUF model under:

```text
~/models/Huihui-Qwen3-8B-abliterated-v2-Q4_K_M/
```

and supports an embedding model at:

```text
~/models/Qwen3-Embedding-4B/
```

Paths can be overridden through environment variables where supported. See [`.env.example`](.env.example).

## Run

Start the local inference server:

```fish
cd ~/forge
./start-llama.fish
```

In another terminal:

```fish
cd ~/forge
source .venv/bin/activate.fish
./start-chat.fish
```

Open:

```text
http://127.0.0.1:8765
```

## Indexing knowledge

Put supported research material into the appropriate `knowledge/` directory and run:

```fish
python ingest.py --force
```

The knowledge base remains separate from application source code so it can evolve independently.

## Configuration

Forge reads configuration from environment variables. A safe example is provided in [`.env.example`](.env.example).

Do not commit real credentials, tokens, private keys, local databases, model weights, or private research material.

## Development

Run the basic source validation before committing:

```bash
python -m py_compile *.py
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for contribution guidance and [`docs/architecture.md`](docs/architecture.md) for the current architecture.

## Roadmap

- [ ] Retrieval evaluation and regression tests
- [ ] Better document parsing and metadata extraction
- [ ] Citation-aware retrieval/output
- [ ] Forge Intel integration contract
- [ ] CVE/exploit intelligence ingestion through Forge Intel
- [ ] Security research workflows
- [ ] Improved observability and diagnostics

## Responsible use

Forge is intended for authorized security research, education, defensive analysis, and controlled laboratory environments. Do not use it to access systems or data without authorization.

## License

MIT. See [`LICENSE`](LICENSE).
