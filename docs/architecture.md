# Forge architecture

## Processes

1. **llama-server** — loads a GGUF model, exposes OpenAI-compatible HTTP on loopback.
2. **uvicorn + FastAPI** — serves the UI and `/api/*`, performs retrieval, streams completions.
3. **On-disk stores** — Chroma collection(s), SQLite (`data/forge.db`) for chats and FTS.

## Request path (chat)

1. Client `POST /api/chat` with message, optional `chat_id`, preset, RAG flag.
2. Server loads authoritative history from SQLite when `chat_id` is known.
3. If RAG is enabled, `rag.retrieve()` embeds the query (CPU), queries Chroma and FTS5, fuses with RRF, filters by minimum similarity, applies MMR, and truncates to `MAX_CONTEXT_CHARS`.
4. `llm.chat_stream()` builds messages (system preset + history + knowledge block + user text) and streams from `llama-server`.
5. A `ThinkFilter` strips chain-of-thought tags if the model emits them.
6. On success, assistant text is appended to SQLite. Regeneration replaces the previous assistant turn only after a successful completion.

## Ingest path

1. Walk `knowledge/*` for text-like extensions.
2. Fingerprint files; skip unchanged files unless `--force`.
3. Chunk with structure-aware merging and overlap (`smart_chunk`).
4. Embed batches (CUDA optional, conservative batch size; CPU fallback).
5. Upsert into Chroma; replace FTS rows for that source and index version.
6. On `--force`, build a new versioned collection and activate only if no per-file errors were recorded.

## Trust boundaries

- Knowledge text is injected as **data** under an explicit system instruction not to follow instructions found inside it.
- Remote LLM base URLs require `FORGE_ALLOW_REMOTE_LLM=1`.
- UI and API default to localhost; TrustedHost and origin checks reduce casual cross-site abuse on the local port.
