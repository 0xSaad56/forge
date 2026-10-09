from __future__ import annotations

import logging
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import DB_PATH

log = logging.getLogger("forge.history")
CHAT_ID_RE = re.compile(r"^[a-f0-9]{12}$")
_lock = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init_db() -> None:
    with _lock:
        c = _conn()
        try:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT 'Untitled',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id);
                CREATE INDEX IF NOT EXISTS idx_chats_updated ON chats(updated_at DESC);

                CREATE TABLE IF NOT EXISTS rag_docs (
                    chunk_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    type TEXT,
                    filename TEXT,
                    chunk_index INTEGER,
                    content TEXT NOT NULL,
                    content_hash TEXT,
                    ingested_at TEXT,
                    index_version INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_rag_docs_source ON rag_docs(source);
                CREATE INDEX IF NOT EXISTS idx_rag_docs_ver ON rag_docs(index_version);

                CREATE VIRTUAL TABLE IF NOT EXISTS rag_fts USING fts5(
                    content,
                    chunk_id UNINDEXED,
                    source UNINDEXED,
                    filename UNINDEXED,
                    type UNINDEXED,
                    index_version UNINDEXED,
                    tokenize = 'porter'
                );
                """
            )
            c.commit()
        finally:
            c.close()


init_db()


def new_chat_id() -> str:
    return uuid.uuid4().hex[:12]


def list_chats(limit: int = 120) -> List[Dict[str, Any]]:
    with _lock:
        c = _conn()
        try:
            rows = c.execute(
                """
                SELECT c.id, c.title, c.created_at, c.updated_at,
                       (SELECT COUNT(*) FROM messages m WHERE m.chat_id = c.id) AS message_count,
                       (SELECT content FROM messages m
                        WHERE m.chat_id = c.id AND m.role = 'user'
                        ORDER BY m.id ASC LIMIT 1) AS preview
                FROM chats c
                ORDER BY c.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            out = []
            for r in rows:
                preview = (r["preview"] or "").strip().replace("\n", " ")[:100]
                out.append(
                    {
                        "id": r["id"],
                        "title": r["title"] or preview or "Untitled",
                        "preview": preview,
                        "updated_at": r["updated_at"] or "",
                        "created_at": r["created_at"] or "",
                        "message_count": r["message_count"] or 0,
                    }
                )
            return out
        finally:
            c.close()


def load_chat(chat_id: str) -> Optional[Dict[str, Any]]:
    if not CHAT_ID_RE.fullmatch(chat_id or ""):
        return None
    with _lock:
        c = _conn()
        try:
            chat = c.execute(
                "SELECT id, title, created_at, updated_at FROM chats WHERE id = ?",
                (chat_id,),
            ).fetchone()
            if not chat:
                return None
            msgs = c.execute(
                "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id ASC",
                (chat_id,),
            ).fetchall()
            return {
                "id": chat["id"],
                "title": chat["title"],
                "created_at": chat["created_at"],
                "updated_at": chat["updated_at"],
                "messages": [
                    {"role": m["role"], "content": m["content"]} for m in msgs
                ],
            }
        finally:
            c.close()


def ensure_chat(chat_id: str, title: Optional[str] = None) -> None:
    if not CHAT_ID_RE.fullmatch(chat_id or ""):
        raise ValueError("invalid chat id")
    now = _now()
    with _lock:
        c = _conn()
        try:
            row = c.execute("SELECT id FROM chats WHERE id = ?", (chat_id,)).fetchone()
            if row:
                return
            c.execute(
                "INSERT INTO chats (id, title, created_at, updated_at) VALUES (?,?,?,?)",
                (chat_id, title or "Untitled", now, now),
            )
            c.commit()
        finally:
            c.close()


def append_message(
    chat_id: str,
    role: str,
    content: str,
    title: Optional[str] = None,
) -> None:
    if not CHAT_ID_RE.fullmatch(chat_id or ""):
        raise ValueError("invalid chat id")
    if role not in ("user", "assistant") or not content:
        return
    now = _now()
    with _lock:
        c = _conn()
        try:
            row = c.execute(
                "SELECT title FROM chats WHERE id = ?", (chat_id,)
            ).fetchone()
            if not row:
                t = title or (
                    content.strip().replace("\n", " ")[:80]
                    if role == "user"
                    else "Untitled"
                )
                c.execute(
                    "INSERT INTO chats (id, title, created_at, updated_at) VALUES (?,?,?,?)",
                    (chat_id, t, now, now),
                )
            else:
                new_title = title
                if not new_title and role == "user" and (row["title"] in (None, "", "Untitled")):
                    new_title = content.strip().replace("\n", " ")[:80]
                if new_title:
                    c.execute(
                        "UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
                        (new_title, now, chat_id),
                    )
                else:
                    c.execute(
                        "UPDATE chats SET updated_at = ? WHERE id = ?",
                        (now, chat_id),
                    )
            c.execute(
                "INSERT INTO messages (chat_id, role, content, created_at) VALUES (?,?,?,?)",
                (chat_id, role, content, now),
            )
            c.commit()
        finally:
            c.close()


def save_chat(
    chat_id: str,
    messages: List[Dict[str, str]],
    title: Optional[str] = None,
) -> Dict[str, Any]:
    """Compatibility: sync full message list via append-friendly replace only when needed."""
    if not CHAT_ID_RE.fullmatch(chat_id or ""):
        raise ValueError("invalid chat id")
    now = _now()
    with _lock:
        c = _conn()
        try:
            row = c.execute(
                "SELECT title, created_at FROM chats WHERE id = ?", (chat_id,)
            ).fetchone()
            if row:
                created = row["created_at"]
                title = title or row["title"]
            else:
                created = now
                if not title:
                    for m in messages:
                        if m.get("role") == "user" and m.get("content"):
                            title = m["content"].strip().replace("\n", " ")[:80]
                            break
                title = title or "Untitled"
                c.execute(
                    "INSERT INTO chats (id, title, created_at, updated_at) VALUES (?,?,?,?)",
                    (chat_id, title, created, now),
                )

            existing = c.execute(
                "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id ASC",
                (chat_id,),
            ).fetchall()
            existing_list = [(r["role"], r["content"]) for r in existing]
            new_list = [
                (m.get("role"), m.get("content") or "")
                for m in messages
                if m.get("role") in ("user", "assistant") and m.get("content")
            ]

            # Fast path: pure append
            if len(new_list) >= len(existing_list) and existing_list == new_list[: len(existing_list)]:
                for role, content in new_list[len(existing_list) :]:
                    c.execute(
                        "INSERT INTO messages (chat_id, role, content, created_at) VALUES (?,?,?,?)",
                        (chat_id, role, content, now),
                    )
            else:
                c.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
                for role, content in new_list:
                    c.execute(
                        "INSERT INTO messages (chat_id, role, content, created_at) VALUES (?,?,?,?)",
                        (chat_id, role, content, now),
                    )

            c.execute(
                "UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
                (title or "Untitled", now, chat_id),
            )
            c.commit()
            return {
                "id": chat_id,
                "title": title or "Untitled",
                "created_at": created,
                "updated_at": now,
                "messages": messages,
            }
        finally:
            c.close()


def get_last_user_message(chat_id: str) -> Optional[str]:
    if not CHAT_ID_RE.fullmatch(chat_id or ""):
        return None
    with _lock:
        c = _conn()
        try:
            row = c.execute(
                """
                SELECT content FROM messages
                WHERE chat_id = ? AND role = 'user'
                ORDER BY id DESC LIMIT 1
                """,
                (chat_id,),
            ).fetchone()
            return row["content"] if row else None
        finally:
            c.close()


def commit_regeneration(chat_id: str, new_content: str) -> bool:
    """On success only: remove previous assistant, append the new one."""
    if not CHAT_ID_RE.fullmatch(chat_id or "") or not (new_content or "").strip():
        return False
    now = _now()
    with _lock:
        c = _conn()
        try:
            last = c.execute(
                """
                SELECT id, role FROM messages
                WHERE chat_id = ?
                ORDER BY id DESC LIMIT 1
                """,
                (chat_id,),
            ).fetchone()
            if last and last["role"] == "assistant":
                c.execute("DELETE FROM messages WHERE id = ?", (last["id"],))
            c.execute(
                "INSERT INTO messages (chat_id, role, content, created_at) VALUES (?,?,?,?)",
                (chat_id, "assistant", new_content.strip(), now),
            )
            c.execute(
                "UPDATE chats SET updated_at = ? WHERE id = ?",
                (now, chat_id),
            )
            c.commit()
            return True
        finally:
            c.close()


def prepare_regeneration(chat_id: str) -> Optional[str]:
    """Non-destructive: return last user text; keep existing assistant until commit_regeneration."""
    return get_last_user_message(chat_id)


def delete_chat(chat_id: str) -> bool:
    if not CHAT_ID_RE.fullmatch(chat_id or ""):
        return False
    with _lock:
        c = _conn()
        try:
            cur = c.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
            c.commit()
            return cur.rowcount > 0
        finally:
            c.close()


def rag_fts_replace_source(
    source: str, rows: List[Dict[str, Any]], index_version: int
) -> None:
    with _lock:
        c = _conn()
        try:
            c.execute(
                "DELETE FROM rag_fts WHERE source = ? AND index_version = ?",
                (source, str(index_version)),
            )
            c.execute(
                "DELETE FROM rag_docs WHERE source = ? AND index_version = ?",
                (source, index_version),
            )
            for row in rows:
                c.execute(
                    """
                    INSERT INTO rag_docs
                    (chunk_id, source, type, filename, chunk_index, content, content_hash, ingested_at, index_version)
                    VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        row["chunk_id"],
                        row["source"],
                        row.get("type"),
                        row.get("filename"),
                        row.get("chunk_index"),
                        row["content"],
                        row.get("content_hash"),
                        row.get("ingested_at"),
                        index_version,
                    ),
                )
                c.execute(
                    """
                    INSERT INTO rag_fts (content, chunk_id, source, filename, type, index_version)
                    VALUES (?,?,?,?,?,?)
                    """,
                    (
                        row["content"],
                        row["chunk_id"],
                        row["source"],
                        row.get("filename") or "",
                        row.get("type") or "",
                        str(index_version),
                    ),
                )
            c.commit()
        finally:
            c.close()


def rag_fts_delete_source(source: str) -> None:
    with _lock:
        c = _conn()
        try:
            c.execute("DELETE FROM rag_fts WHERE source = ?", (source,))
            c.execute("DELETE FROM rag_docs WHERE source = ?", (source,))
            c.commit()
        finally:
            c.close()


def rag_fts_clear_version(index_version: int) -> None:
    with _lock:
        c = _conn()
        try:
            c.execute(
                "DELETE FROM rag_fts WHERE index_version = ?", (str(index_version),)
            )
            c.execute(
                "DELETE FROM rag_docs WHERE index_version = ?", (index_version,)
            )
            c.commit()
        finally:
            c.close()


def rag_fts_search(
    query: str, limit: int = 20, index_version: Optional[int] = None
) -> List[Dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    tokens = re.findall(r"[A-Za-z0-9_\-./]{2,}", q)
    if not tokens:
        return []
    parts = []
    for t in tokens[:12]:
        t = t.replace('"', '""')
        parts.append(f'"{t}"')
    fts_q = " OR ".join(parts)
    with _lock:
        c = _conn()
        try:
            if index_version is not None:
                rows = c.execute(
                    """
                    SELECT f.chunk_id, f.source, f.filename, f.type, d.content,
                           bm25(rag_fts) AS rank
                    FROM rag_fts f
                    JOIN rag_docs d ON d.chunk_id = f.chunk_id
                    WHERE rag_fts MATCH ? AND f.index_version = ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (fts_q, str(index_version), limit),
                ).fetchall()
            else:
                rows = c.execute(
                    """
                    SELECT f.chunk_id, f.source, f.filename, f.type, d.content,
                           bm25(rag_fts) AS rank
                    FROM rag_fts f
                    JOIN rag_docs d ON d.chunk_id = f.chunk_id
                    WHERE rag_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (fts_q, limit),
                ).fetchall()
            return [
                {
                    "chunk_id": r["chunk_id"],
                    "source": r["source"],
                    "filename": r["filename"],
                    "type": r["type"],
                    "content": r["content"],
                    "rank": float(r["rank"]),
                }
                for r in rows
            ]
        except Exception:
            log.exception("FTS retrieval failed for query=%r", q[:80])
            return []
        finally:
            c.close()


def rag_fts_sources(index_version: Optional[int] = None) -> set:
    with _lock:
        c = _conn()
        try:
            if index_version is not None:
                rows = c.execute(
                    "SELECT DISTINCT source FROM rag_docs WHERE index_version = ?",
                    (index_version,),
                ).fetchall()
            else:
                rows = c.execute("SELECT DISTINCT source FROM rag_docs").fetchall()
            return {r["source"] for r in rows}
        finally:
            c.close()
