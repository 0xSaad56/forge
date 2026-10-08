# Forge Architecture

Forge is a local-first security research assistant. The application and the security-intelligence acquisition layer are intentionally separate.

```text
User
  |
  v
Web UI
  |
  v
FastAPI server
  |
  +--------------------> Local LLM (llama-server)
  |
  v
Hybrid retrieval
  |
  +--> Chroma vector search
  +--> SQLite FTS5 / BM25
  +--> Reciprocal Rank Fusion
  +--> score filtering
  +--> Maximal Marginal Relevance
  |
  v
Retrieved context
  |
  v
Local LLM
  |
  v
Response
```

## Knowledge boundary

Forge indexes material placed under `knowledge/`. It does not currently fetch CVEs, exploit feeds, or threat-intelligence sources itself.

A separate future project, `Forge Intel`, is intended to collect, normalize, correlate, and export security intelligence into a stable machine-readable contract that Forge can ingest.

This separation keeps Forge focused on retrieval and reasoning while allowing the intelligence project to evolve independently.
