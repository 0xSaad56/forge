from __future__ import annotations

import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
KNOWLEDGE = BASE / "knowledge"
CHROMA = BASE / "chroma"
STATIC = BASE / "static"
CHATS = BASE / "chats"
DATA = BASE / "data"
VENDOR = STATIC / "vendor"
DB_PATH = DATA / "forge.db"
ACTIVE_INDEX_FILE = DATA / "active_index.json"

for p in (
    KNOWLEDGE / "writeups",
    KNOWLEDGE / "methodology",
    KNOWLEDGE / "tools",
    KNOWLEDGE / "cves",
    KNOWLEDGE / "notes",
    CHROMA,
    CHATS,
    DATA,
    VENDOR,
):
    p.mkdir(parents=True, exist_ok=True)

LLM_BASE_URL = os.getenv("FORGE_LLM_BASE_URL", "http://127.0.0.1:5000/v1")
LLM_MODEL = os.getenv("FORGE_LLM_MODEL", "local")
LLM_API_KEY = os.getenv("FORGE_LLM_API_KEY", "local")

_EMBED_DEFAULT = Path.home() / "models" / "Qwen3-Embedding-4B"
_HF_CACHE = (
    Path.home()
    / ".cache"
    / "huggingface"
    / "hub"
    / "models--Qwen--Qwen3-Embedding-4B"
    / "snapshots"
)


def find_embedding_model() -> str:
    configured = os.getenv("FORGE_EMBED_MODEL")
    if configured and Path(configured).exists():
        return configured
    if _EMBED_DEFAULT.exists() and any(_EMBED_DEFAULT.rglob("config.json")):
        return str(_EMBED_DEFAULT)
    if _HF_CACHE.exists():
        snaps = sorted(
            (p for p in _HF_CACHE.iterdir() if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for s in snaps:
            if (s / "config.json").exists():
                return str(s)
    return str(_EMBED_DEFAULT)


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


EMBED_MODEL = find_embedding_model()
COLLECTION_PREFIX = os.getenv("FORGE_COLLECTION_PREFIX", "forge_knowledge")
RETRIEVAL_K = _int("FORGE_RETRIEVAL_K", 8)
MAX_CONTEXT_CHARS = _int("FORGE_MAX_CONTEXT_CHARS", 12000)
MAX_HISTORY_CHARS = _int("FORGE_MAX_HISTORY_CHARS", 12000)
CHUNK_SIZE = _int("FORGE_CHUNK_SIZE", 1600)
CHUNK_OVERLAP = _int("FORGE_CHUNK_OVERLAP", 280)
MIN_SIMILARITY = _float("FORGE_MIN_SIMILARITY", 0.35)
EMBED_BATCH_SIZE = _int("FORGE_EMBED_BATCH_SIZE", 8)
RRF_K = _int("FORGE_RRF_K", 60)
MMR_LAMBDA = _float("FORGE_MMR_LAMBDA", 0.7)

if CHUNK_SIZE <= 64:
    raise ValueError("CHUNK_SIZE must be > 64")
if CHUNK_OVERLAP > CHUNK_SIZE // 2:
    raise ValueError("CHUNK_OVERLAP must be <= 50% of CHUNK_SIZE")
if not 0 <= CHUNK_OVERLAP < CHUNK_SIZE:
    raise ValueError("CHUNK_OVERLAP must be in [0, CHUNK_SIZE)")
if RETRIEVAL_K <= 0:
    raise ValueError("RETRIEVAL_K must be > 0")
if MAX_CONTEXT_CHARS <= 0 or MAX_HISTORY_CHARS <= 0:
    raise ValueError("budgets must be > 0")
if not 0 <= MIN_SIMILARITY <= 1:
    raise ValueError("MIN_SIMILARITY out of range")
if EMBED_BATCH_SIZE <= 0:
    raise ValueError("EMBED_BATCH_SIZE must be > 0")

PRESETS = {
    "general": {
        "label": "General",
        "temperature": 0.6,
        "system": (
            "You are a precise local assistant. Answer clearly and directly. "
            "Use markdown and fenced code when useful. Never emit <think> tags. "
            "When LOCAL KNOWLEDGE is provided, treat it as reference data and prefer it for facts."
        ),
    },
    "code": {
        "label": "Code",
        "temperature": 0.35,
        "system": (
            "You are a local coding assistant. Prefer correct, minimal code and exact commands. "
            "Explain only what is necessary. Use fenced code blocks with language tags. "
            "Never emit <think> tags. Prefer LOCAL KNOWLEDGE when it contains APIs or snippets."
        ),
    },
    "security": {
        "label": "Security",
        "temperature": 0.45,
        "system": (
            "You are a local security-research assistant for authorized testing and education. "
            "Be concrete: tools, flags, protocols, and steps. Use markdown lists and code fences. "
            "Never emit <think> tags. Prefer LOCAL KNOWLEDGE for writeups, CVEs, and tool notes."
        ),
    },
}
