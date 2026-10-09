from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_IMPLEMENTATION", "none")
os.environ.setdefault("POSTHOG_DISABLED", "1")

import history as histore
from config import (
    ACTIVE_INDEX_FILE,
    CHROMA,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    COLLECTION_PREFIX,
    EMBED_BATCH_SIZE,
    EMBED_CACHE,
    EMBED_DIMENSION,
    EMBED_LOCAL_ONLY,
    EMBED_MODEL,
    EMBED_THREADS,
    INGEST_EMBED_BATCH_SIZE,
    KNOWLEDGE,
    MAX_CONTEXT_CHARS,
    MAX_KNOWLEDGE_FILE_BYTES,
    MIN_SIMILARITY,
    MMR_LAMBDA,
    RETRIEVAL_K,
    RRF_K,
)

log = logging.getLogger("forge.rag")

_model_lock = threading.RLock()
_collection_lock = threading.RLock()
_ingest_lock = threading.RLock()
_collection = None
_active_name: Optional[str] = None
_active_version: int = 1
_embedders: Dict[str, Any] = {}
_load_error: Optional[str] = None
_status_cache = {"ts": 0.0, "count": 0, "embed_ready": None}

FOLDER_TYPES = {
    "writeups": KNOWLEDGE / "writeups",
    "methodology": KNOWLEDGE / "methodology",
    "tools": KNOWLEDGE / "tools",
    "cves": KNOWLEDGE / "cves",
    "notes": KNOWLEDGE / "notes",
    "intel": KNOWLEDGE / "intel",
    "exploits": KNOWLEDGE / "exploits",
}
_TEXT_EXT = {".md", ".txt", ".html", ".json", ".log", ".rst", ".csv", ".jsonl"}
_H = re.compile(r"^#{1,4}\s+(.*)")


def _load_active_meta() -> Tuple[str, int]:
    global _active_name, _active_version
    if ACTIVE_INDEX_FILE.exists():
        try:
            data = json.loads(ACTIVE_INDEX_FILE.read_text(encoding="utf-8"))
            name = data.get("collection") or f"{COLLECTION_PREFIX}_v1"
            ver = int(data.get("version") or 1)
            _active_name, _active_version = name, ver
            return name, ver
        except Exception:
            pass
    _active_name, _active_version = f"{COLLECTION_PREFIX}_v1", 1
    return _active_name, _active_version


def _save_active_meta(name: str, version: int) -> None:
    global _active_name, _active_version
    ACTIVE_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"collection": name, "version": version}, indent=2)
    tmp = ACTIVE_INDEX_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, ACTIVE_INDEX_FILE)
    _active_name, _active_version = name, version


def _chroma_client():
    from chromadb import PersistentClient
    from chromadb.config import Settings

    return PersistentClient(
        path=str(CHROMA),
        settings=Settings(anonymized_telemetry=False, allow_reset=True),
    )


def _sliding(text: str, max_len: int, overlap: int) -> List[str]:
    overlap = min(max(0, overlap), max_len - 1)
    if len(text) <= max_len:
        return [text]
    step = max_len - overlap
    return [text[i : i + max_len] for i in range(0, len(text), step)]


def _blocks(text: str):
    out, buf, fence, head = [], [], False, ""
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            fence = not fence
        if not fence:
            m = _H.match(line)
            if m:
                head = m.group(1).strip()
        buf.append(line)
        if not fence and not line.strip():
            joined = "\n".join(buf).strip()
            if joined:
                out.append((joined, head))
            buf = []
    tail = "\n".join(buf).strip()
    if tail:
        out.append((tail, head))
    return out


def smart_chunk(text: str, source: str = "", max_len: int = None, overlap: int = None) -> List[str]:
    max_len = max_len or CHUNK_SIZE
    overlap = CHUNK_OVERLAP if overlap is None else overlap
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return []

    def pack(body: str, heading: str) -> str:
        heading = heading or "body"
        prefix = f"[{source} › {heading}]\n" if source else ""
        body_limit = max(64, max_len - len(prefix))
        if len(body) > body_limit:
            body = body[:body_limit]
        return (prefix + body)[:max_len]

    merged: List[tuple] = []
    buf, buf_h, buf_n = [], "body", 0
    for blk, heading in _blocks(text):
        h = heading or "body"
        if not buf:
            buf, buf_h, buf_n = [blk], h, len(blk)
            continue
        if buf_n + 2 + len(blk) <= int(max_len * 0.85):
            buf.append(blk)
            buf_n += 2 + len(blk)
        else:
            merged.append(("\n\n".join(buf), buf_h))
            buf, buf_h, buf_n = [blk], h, len(blk)
    if buf:
        merged.append(("\n\n".join(buf), buf_h))

    chunks: List[str] = []
    for body, heading in merged:
        prefix = f"[{source} › {heading}]\n" if source else ""
        body_limit = max(64, max_len - len(prefix))
        if len(body) <= body_limit:
            chunks.append(pack(body, heading))
            continue
        for piece in _sliding(body, body_limit, min(overlap, max(0, body_limit - 1))):
            chunks.append(pack(piece, heading))
    return chunks


def _get_embedder(device: str = "cpu"):
    """device: cpu | cuda. Query path always uses CPU; ingest may use CUDA."""
    global _load_error
    key = "cuda" if device == "cuda" else "cpu"
    with _model_lock:
        if key in _embedders:
            return _embedders[key]
        try:
            from fastembed import TextEmbedding

            EMBED_CACHE.mkdir(parents=True, exist_ok=True)
            providers = (
                ["CUDAExecutionProvider", "CPUExecutionProvider"]
                if key == "cuda"
                else ["CPUExecutionProvider"]
            )
            kwargs = {
                "model_name": EMBED_MODEL,
                "cache_dir": str(EMBED_CACHE),
                "providers": providers,
                "threads": EMBED_THREADS,
            }
            if EMBED_LOCAL_ONLY:
                kwargs["local_files_only"] = True
            try:
                model = TextEmbedding(**kwargs)
            except TypeError:
                kwargs.pop("local_files_only", None)
                model = TextEmbedding(**kwargs)
            # warm + dim check
            probe = list(model.embed(["forge dim check"]))
            if not probe or len(probe[0]) != EMBED_DIMENSION:
                raise RuntimeError(
                    f"unexpected embedding dim {len(probe[0]) if probe else 0}, want {EMBED_DIMENSION}"
                )
            _embedders[key] = model
            _load_error = None
            log.info("Loaded embedder %s providers=%s", EMBED_MODEL, providers)
            return model
        except Exception as e:
            _load_error = str(e)
            log.exception("embedder load failed device=%s", key)
            if key == "cuda":
                return _get_embedder("cpu")
            return None


def _embed(texts: List[str], device: str = "cpu") -> List[List[float]]:
    """Embed texts. Long bodies are truncated only for the embedder (full text still stored).
    CUDA uses batch_size=1 to fit 8GB VRAM; OOM falls back to CPU."""
    if not texts:
        return []
    # Keep embedding inputs short — main VRAM killer is seq_len * batch
    EMBED_CHAR_CAP = 1000
    capped = [(t or "")[:EMBED_CHAR_CAP] for t in texts]

    def _run(dev: str, batch: int) -> List[List[float]]:
        model = _get_embedder(dev)
        if model is None:
            raise RuntimeError(_load_error or "embedding model unavailable")
        out: List[List[float]] = []
        with _model_lock:
            for i in range(0, len(capped), batch):
                chunk = capped[i : i + batch]
                try:
                    for vec in model.embed(chunk, batch_size=1 if dev == "cuda" else len(chunk)):
                        out.append(list(map(float, vec)))
                except TypeError:
                    for vec in model.embed(chunk):
                        out.append(list(map(float, vec)))
        return out

    if device == "cuda":
        try:
            return _run("cuda", 1)
        except Exception as e:
            log.warning("CUDA embed failed, using CPU: %s", e)
            return _run("cpu", 4)
    return _run("cpu", 8)


def _client(force: bool = False):
    global _collection
    with _collection_lock:
        if _collection is not None:
            return _collection
        if not force:
            return None
        try:
            if _get_embedder("cpu") is None:
                return None
            name, _ = _load_active_meta()
            client = _chroma_client()
            _collection = client.get_or_create_collection(
                name=name,
                embedding_function=None,
                metadata={"hnsw:space": "cosine"},
            )
            return _collection
        except Exception as e:
            global _load_error
            _load_error = str(e)
            log.exception("chroma open failed")
            return None


def _file_fingerprint(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _chunk_id(source: str, content_hash: str, index: int) -> str:
    return hashlib.sha256(f"{source}:{content_hash}:{index}".encode()).hexdigest()


def _iter_knowledge_files():
    for source_type, folder in FOLDER_TYPES.items():
        if not folder.exists():
            continue
        for file in folder.rglob("*"):
            if file.is_file() and file.suffix.lower() in _TEXT_EXT:
                try:
                    if file.stat().st_size > MAX_KNOWLEDGE_FILE_BYTES:
                        log.warning("skip oversized file %s", file)
                        continue
                except OSError:
                    continue
                yield source_type, file


def _rrf(ranked_lists: List[List[str]], k: int = 60) -> List[Tuple[str, float]]:
    scores: Dict[str, float] = {}
    for lst in ranked_lists:
        for rank, doc_id in enumerate(lst, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def _jaccard(a: str, b: str) -> float:
    ta = set(re.findall(r"[a-z0-9]{3,}", a.lower()))
    tb = set(re.findall(r"[a-z0-9]{3,}", b.lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _mmr_select(candidates: List[Tuple[str, float, str]], k: int, lam: float):
    if not candidates:
        return []
    selected, remaining = [], candidates[:]
    while remaining and len(selected) < k:
        best_i, best_val = 0, -1e9
        for i, (cid, score, text) in enumerate(remaining):
            if not selected:
                val = score
            else:
                red = max(_jaccard(text, st) for _, _, st in selected)
                val = lam * score - (1 - lam) * red
            if val > best_val:
                best_val, best_i = val, i
        selected.append(remaining.pop(best_i))
    return selected


def ingest(
    progress_cb: Optional[Callable] = None,
    force: bool = False,
    device: Optional[str] = None,
) -> Dict[str, Any]:
    with _ingest_lock:
        device = (device or "cpu").lower()
        if device not in {"cuda", "cpu"}:
            device = "cpu"
        batch = (min(INGEST_EMBED_BATCH_SIZE, 2) if device == "cuda" else EMBED_BATCH_SIZE)

        client = _chroma_client()
        if _get_embedder(device) is None and _get_embedder("cpu") is None:
            return {"ok": False, "error": _load_error or "embed model failed", "errors": []}

        active_name, active_ver = _load_active_meta()
        if force:
            target_ver = active_ver + 1
            target_name = f"{COLLECTION_PREFIX}_v{target_ver}"
            try:
                client.delete_collection(target_name)
            except Exception:
                pass
            col = client.get_or_create_collection(
                name=target_name,
                embedding_function=None,
                metadata={"hnsw:space": "cosine"},
            )
            prev: Dict[str, str] = {}
        else:
            target_ver = active_ver
            target_name = active_name
            col = client.get_or_create_collection(
                name=target_name,
                embedding_function=None,
                metadata={"hnsw:space": "cosine"},
            )
            state_path = CHROMA / "ingest_state.json"
            prev = {}
            if state_path.exists():
                try:
                    prev = json.loads(state_path.read_text(encoding="utf-8"))
                except Exception:
                    prev = {}
            if col.count() == 0:
                prev = {}

        stats = {
            "files": 0,
            "chunks": 0,
            "skipped": 0,
            "deleted": 0,
            "errors": [],
            "empty_files": 0,
            "device": device,
        }
        new_state: Dict[str, str] = {}
        seen_keys = set()
        state_path = CHROMA / "ingest_state.json"

        for source_type, file in _iter_knowledge_files():
            key = str(file.resolve())
            seen_keys.add(key)
            try:
                fp = _file_fingerprint(file)
            except Exception as e:
                stats["errors"].append(f"{file.name}: {e}")
                continue
            if not force and prev.get(key) == fp:
                new_state[key] = fp
                stats["skipped"] += 1
                continue
            try:
                text = file.read_text(encoding="utf-8", errors="ignore")
                if not text.strip():
                    stats["empty_files"] += 1
                    new_state[key] = fp
                    continue
                rel = str(file.relative_to(KNOWLEDGE))
                chunks = smart_chunk(text, source=rel)
                if not chunks:
                    stats["empty_files"] += 1
                    continue

                ids, docs, embs, metas, fts_rows = [], [], [], [], []
                for i in range(0, len(chunks), batch):
                    batch_docs = chunks[i : i + batch]
                    batch_emb = _embed(batch_docs, device=device)
                    for j, (doc, emb) in enumerate(zip(batch_docs, batch_emb)):
                        idx = i + j
                        cid = _chunk_id(key, fp, idx)
                        ids.append(cid)
                        docs.append(doc)
                        embs.append(emb)
                        meta = {
                            "source": key,
                            "type": source_type,
                            "filename": file.name,
                            "chunk_index": idx,
                            "content_hash": fp,
                            "ingested_at": datetime.now(timezone.utc).isoformat(),
                        }
                        metas.append(meta)
                        fts_rows.append(
                            {
                                "chunk_id": cid,
                                "source": key,
                                "type": source_type,
                                "filename": file.name,
                                "chunk_index": idx,
                                "content": doc,
                                "content_hash": fp,
                                "ingested_at": meta["ingested_at"],
                            }
                        )

                with _collection_lock:
                    col.upsert(ids=ids, documents=docs, embeddings=embs, metadatas=metas)
                    try:
                        existing = col.get(where={"source": key}, include=["metadatas"])
                        old_ids = [eid for eid in (existing.get("ids") or []) if eid not in set(ids)]
                        if old_ids:
                            col.delete(ids=old_ids)
                    except Exception:
                        pass
                histore.rag_fts_replace_source(key, fts_rows, target_ver)

                new_state[key] = fp
                stats["files"] += 1
                stats["chunks"] += len(chunks)
                if progress_cb:
                    progress_cb(file.name, len(chunks))
            except Exception as e:
                stats["errors"].append(f"{file.name}: {e}")
                log.exception("ingest %s", file)

        try:
            got = col.get(include=["metadatas"])
            db_sources = set()
            for meta in got.get("metadatas") or []:
                if meta and meta.get("source"):
                    db_sources.add(meta["source"])
            for old_key in db_sources | histore.rag_fts_sources(target_ver):
                if old_key not in seen_keys:
                    try:
                        col.delete(where={"source": old_key})
                    except Exception:
                        pass
                    if force:
                        try:
                            histore.rag_fts_replace_source(old_key, [], target_ver)
                        except Exception:
                            pass
                    else:
                        histore.rag_fts_delete_source(old_key)
                    stats["deleted"] += 1
        except Exception:
            log.exception("stale cleanup")

        if force:
            if stats["errors"]:
                log.error("force reindex errors; keeping active %s", active_name)
                try:
                    client.delete_collection(target_name)
                except Exception:
                    pass
                try:
                    histore.rag_fts_clear_version(target_ver)
                except Exception:
                    pass
                stats["ok"] = False
                stats["active_collection"] = active_name
                stats["active_version"] = active_ver
                stats["discarded_build"] = target_name
                return stats
            _save_active_meta(target_name, target_ver)
            global _collection
            with _collection_lock:
                _collection = col
            if target_ver > 2:
                try:
                    histore.rag_fts_clear_version(target_ver - 2)
                except Exception:
                    pass
        else:
            with _collection_lock:
                _collection = col

        try:
            state_path.write_text(json.dumps(new_state, indent=2), encoding="utf-8")
        except Exception:
            pass

        _status_cache["count"] = col.count()
        _status_cache["ts"] = datetime.now(timezone.utc).timestamp()
        stats["ok"] = True
        stats["embed_model"] = EMBED_MODEL
        stats["collection"] = target_name
        stats["version"] = target_ver
        stats["total_indexed"] = _status_cache["count"]
        return stats


def retrieve(query: str, k: int = None, extra_context: str = "") -> str:
    k = k or RETRIEVAL_K
    q = (query or "").strip()
    if extra_context:
        q = (extra_context.strip() + "\n" + q).strip()
    if not q:
        return ""
    col = _client(force=True)
    if col is None:
        return ""
    _, active_ver = _load_active_meta()
    try:
        with _collection_lock:
            count = col.count()
        if count == 0:
            return ""

        q_emb = _embed([q], device="cpu")
        n_results = min(max(k + 8, 12), min(count, 24))
        with _collection_lock:
            res = col.query(query_embeddings=q_emb, n_results=n_results)
        v_docs = (res.get("documents") or [[]])[0]
        v_metas = (res.get("metadatas") or [[]])[0]
        v_dists = (res.get("distances") or [[]])[0]
        v_ids = (res.get("ids") or [[]])[0]

        vector_rank, by_id = [], {}
        for i, doc in enumerate(v_docs):
            cid = v_ids[i] if i < len(v_ids) else f"v{i}"
            dist = float(v_dists[i]) if i < len(v_dists) else 1.0
            sim = max(0.0, 1.0 - dist)
            if sim < MIN_SIMILARITY:
                continue
            meta = v_metas[i] if i < len(v_metas) else {}
            vector_rank.append(cid)
            by_id[cid] = {"content": doc or "", "meta": meta, "sim": sim, "bm25": 0.0}

        fts_hits = histore.rag_fts_search(q, limit=n_results, index_version=active_ver)
        fts_rank = []
        if fts_hits:
            ranks = [h["rank"] for h in fts_hits]
            rmin, rmax = min(ranks), max(ranks)
            span = (rmax - rmin) or 1.0
            for hit in fts_hits:
                cid = hit["chunk_id"]
                fts_rank.append(cid)
                bm = 1.0 - (hit["rank"] - rmin) / span
                if cid not in by_id:
                    by_id[cid] = {
                        "content": hit["content"],
                        "meta": {
                            "type": hit.get("type"),
                            "filename": hit.get("filename"),
                            "source": hit.get("source"),
                        },
                        "sim": 0.0,
                        "bm25": bm,
                    }
                else:
                    by_id[cid]["bm25"] = bm

        fused = _rrf([vector_rank, fts_rank], k=RRF_K)
        max_rrf = fused[0][1] if fused else 1.0
        if max_rrf <= 0:
            max_rrf = 1.0
        candidates = []
        for cid, rrf_score in fused:
            item = by_id.get(cid)
            if not item:
                continue
            score = (
                0.55 * item.get("sim", 0.0)
                + 0.25 * item.get("bm25", 0.0)
                + 0.20 * (rrf_score / max_rrf)
            )
            candidates.append((cid, score, item["content"]))
        candidates.sort(key=lambda x: x[1], reverse=True)
        selected = _mmr_select(candidates, k=k, lam=MMR_LAMBDA)

        parts, total = [], 0
        for cid, score, text in selected:
            meta = by_id[cid]["meta"]
            header = f"[{meta.get('type', '?')} | {meta.get('filename', '')}]"
            block = f"{header}\n{(text or '').strip()}"
            if total + len(block) > MAX_CONTEXT_CHARS:
                remain = MAX_CONTEXT_CHARS - total
                if remain > 200:
                    parts.append(block[:remain] + "\n...")
                break
            parts.append(block)
            total += len(block)
        if not parts and candidates:
            cid, score, text = candidates[0]
            meta = by_id[cid]["meta"]
            header = f"[{meta.get('type', '?')} | {meta.get('filename', '')}]"
            parts.append(f"{header}\n{(text or '').strip()}"[:MAX_CONTEXT_CHARS])
        return "\n\n---\n\n".join(parts)
    except Exception:
        log.exception("retrieve failed")
        return ""


def status() -> Dict[str, Any]:
    import time

    now = time.time()
    name, ver = _load_active_meta()
    if now - _status_cache["ts"] > 15:
        try:
            col = _client(force=False)
            if col is not None:
                with _collection_lock:
                    _status_cache["count"] = col.count()
            else:
                client = _chroma_client()
                try:
                    c = client.get_collection(name, embedding_function=None)
                    _status_cache["count"] = c.count()
                except Exception:
                    pass
        except Exception:
            pass
        _status_cache["embed_ready"] = _get_embedder("cpu") is not None
        _status_cache["ts"] = now
    return {
        "semantic_ready": bool(_status_cache.get("embed_ready")) or _status_cache["count"] > 0,
        "model_loaded": "cpu" in _embedders,
        "embed_model": EMBED_MODEL,
        "embed_backend": "fastembed-onnx",
        "embed_threads": EMBED_THREADS,
        "embed_batch_size": EMBED_BATCH_SIZE,
        "embedding_dimension": EMBED_DIMENSION,
        "chunk_count": _status_cache["count"],
        "collection": name,
        "version": ver,
        "error": _load_error,
        "retrieval_k": RETRIEVAL_K,
        "hybrid": "chroma+fts5+rrf+mmr",
        "knowledge_dirs": {n: str(p) for n, p in FOLDER_TYPES.items()},
    }
