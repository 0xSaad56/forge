from __future__ import annotations

import json
import logging
import time
from typing import List, Literal, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

import history
history.init_db()
import llm
import rag
from config import CHATS, KNOWLEDGE, LLM_BASE_URL, LLM_MODEL, PRESETS, STATIC

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("forge")

app = FastAPI(title="Forge", version="2.1.0")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

_ALLOWED_ORIGINS = {None, "http://127.0.0.1:8765", "http://localhost:8765"}
_llm_health_cache = {"ts": 0.0, "ok": False}

if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.middleware("http")
async def guard(request: Request, call_next):
    origin = request.headers.get("origin")
    if (
        request.method not in ("GET", "HEAD", "OPTIONS")
        and origin is not None
        and origin not in _ALLOWED_ORIGINS
    ):
        return JSONResponse({"detail": "bad origin"}, status_code=403)
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self' data:; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=20000)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=20000)
    history: List[ChatMessage] = Field(default_factory=list, max_length=100)
    chat_id: Optional[str] = None
    use_rag: bool = True
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    preset: str = "general"
    stream: bool = True
    save: bool = True
    regenerate: bool = False


def _ping_llm() -> bool:
    now = time.time()
    if now - _llm_health_cache["ts"] < 15:
        return _llm_health_cache["ok"]
    ok = False
    try:
        base = LLM_BASE_URL.rstrip("/")
        root = base.replace("/v1", "")
        with httpx.Client(timeout=2.0) as c:
            for url in (f"{root}/health", f"{base}/models"):
                try:
                    if c.get(url).status_code < 500:
                        ok = True
                        break
                except Exception:
                    continue
    except Exception:
        ok = False
    _llm_health_cache.update(ts=now, ok=ok)
    return ok


def _resolve_history(req: ChatRequest) -> tuple[str, list[dict]]:
    chat_id = req.chat_id or history.new_chat_id()
    disk = history.load_chat(chat_id) if req.chat_id else None
    if disk and disk.get("messages"):
        hist = [
            {"role": m["role"], "content": m["content"]}
            for m in disk["messages"]
            if m.get("role") in ("user", "assistant") and m.get("content")
        ]
    else:
        hist = [{"role": m.role, "content": m.content} for m in req.history]

    if req.regenerate and hist:
        while hist and hist[-1]["role"] == "assistant":
            hist.pop()
        if hist and hist[-1]["role"] == "user":
            return chat_id, hist[:-1], hist[-1]["content"]
    return chat_id, hist, req.message


@app.get("/", response_class=HTMLResponse)
def index():
    path = STATIC / "index.html"
    if path.exists():
        return HTMLResponse(path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Forge</h1>")


@app.get("/api/health")
def health():
    return {
        "ok": _ping_llm(),
        "llm_url": LLM_BASE_URL,
        "llm_model": LLM_MODEL,
        "rag": rag.status(),
        "presets": {k: v["label"] for k, v in PRESETS.items()},
        "chats_dir": str(CHATS),
        "knowledge_dir": str(KNOWLEDGE),
    }


@app.post("/api/ingest")
def api_ingest(request: Request):
    force = request.query_params.get("force", "").lower() in ("1", "true", "yes")
    result = rag.ingest(force=force)
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "ingest failed"))
    return result


@app.get("/api/chats")
def api_list_chats():
    return {"chats": history.list_chats(120)}


@app.get("/api/chats/{chat_id}")
def api_get_chat(chat_id: str):
    data = history.load_chat(chat_id)
    if not data:
        raise HTTPException(status_code=404, detail="chat not found")
    return data


@app.delete("/api/chats/{chat_id}")
def api_delete_chat(chat_id: str):
    if not history.delete_chat(chat_id):
        raise HTTPException(status_code=404, detail="chat not found")
    return {"ok": True}


@app.post("/api/chat")
def api_chat(req: ChatRequest):
    resolved = _resolve_history(req)
    if len(resolved) == 3:
        chat_id, hist, user_message = resolved
    else:
        chat_id, hist = resolved[0], resolved[1]
        user_message = req.message

    preset = req.preset if req.preset in PRESETS else "general"
    temperature = (
        req.temperature
        if req.temperature is not None
        else PRESETS[preset]["temperature"]
    )

    if req.save:
        try:
            history.ensure_chat(chat_id)
            if not req.regenerate:
                history.append_message(chat_id, "user", user_message)
            # regenerate: keep old assistant until successful completion
        except Exception:
            log.exception("early save failed")
            raise HTTPException(status_code=500, detail="failed to persist user message")

    prior_users = [m["content"] for m in hist if m["role"] == "user"][-2:]
    rag_context = (
        rag.retrieve(user_message, extra_context="\n".join(prior_users))
        if req.use_rag
        else ""
    )

    if req.stream:
        def gen():
            full: list[str] = []
            try:
                yield f"data: {json.dumps({'chat_id': chat_id})}\n\n"
                for token in llm.chat_stream(
                    user_message,
                    history=hist,
                    rag_context=rag_context,
                    temperature=temperature,
                    preset=preset,
                ):
                    full.append(token)
                    yield f"data: {json.dumps({'token': token})}\n\n"
                answer = "".join(full).strip()
                if req.save and answer:
                    try:
                        if req.regenerate:
                            history.commit_regeneration(chat_id, answer)
                        else:
                            history.append_message(chat_id, "assistant", answer)
                    except Exception:
                        log.exception("final save failed")
                yield f"data: {json.dumps({'done': True, 'rag_used': bool(rag_context), 'chat_id': chat_id})}\n\n"
            except GeneratorExit:
                # abort: do not replace old assistant on regenerate; do not save partial as final
                raise
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    try:
        answer = llm.chat(
            user_message,
            history=hist,
            rag_context=rag_context,
            temperature=temperature,
            preset=preset,
        )
        if req.save and answer:
            if req.regenerate:
                history.commit_regeneration(chat_id, answer)
            else:
                history.append_message(chat_id, "assistant", answer)
        return {
            "answer": answer,
            "rag_used": bool(rag_context),
            "chat_id": chat_id,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
