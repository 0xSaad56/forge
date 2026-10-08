from __future__ import annotations

import logging
import re
from typing import Dict, Generator, List, Optional

from openai import OpenAI

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, MAX_HISTORY_CHARS, PRESETS

log = logging.getLogger("forge.llm")
_client: Optional[OpenAI] = None


class ThinkFilter:
    O, C = "<think>", "</think>"

    def __init__(self) -> None:
        self.buf = ""
        self.inside = False

    def feed(self, s: str) -> str:
        if not s:
            return ""
        self.buf += s
        out = ""
        while True:
            tag = self.C if self.inside else self.O
            i = self.buf.lower().find(tag)
            if i >= 0:
                if not self.inside:
                    out += self.buf[:i]
                self.buf = self.buf[i + len(tag) :]
                self.inside = not self.inside
                continue
            hold = next(
                (
                    k
                    for k in range(len(tag) - 1, 0, -1)
                    if self.buf.lower().endswith(tag[:k])
                ),
                0,
            )
            if not self.inside:
                out += self.buf[: len(self.buf) - hold] if hold else self.buf
            self.buf = (
                self.buf[len(self.buf) - hold :]
                if hold
                else (self.buf if self.inside else "")
            )
            if self.inside and not hold:
                self.buf = ""
            return out

    def end(self) -> str:
        r = "" if self.inside else self.buf
        self.buf = ""
        self.inside = False
        return r


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, timeout=180)
    return _client


def _trim_history(history: List[Dict[str, str]], budget: int) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    used = 0
    for turn in reversed(history or []):
        role = turn.get("role")
        content = re.sub(
            r"<think>[\s\S]*?</think>", "", (turn.get("content") or ""), flags=re.I
        ).strip()
        if role not in ("user", "assistant") or not content:
            continue
        remaining = budget - used
        if remaining <= 0:
            break
        if len(content) > remaining:
            content = content[:remaining]
        out.append({"role": role, "content": content})
        used += len(content)
    out.reverse()
    return out


def build_messages(
    user_message: str,
    history: List[Dict[str, str]],
    rag_context: str = "",
    preset: str = "general",
) -> List[Dict[str, str]]:
    conf = PRESETS.get(preset) or PRESETS["general"]
    messages: List[Dict[str, str]] = [{"role": "system", "content": conf["system"]}]
    messages.extend(_trim_history(history, MAX_HISTORY_CHARS))
    if rag_context.strip():
        user_content = (
            "LOCAL KNOWLEDGE (reference only):\n"
            f"{rag_context.strip()}\n\n"
            f"Question: {user_message}"
        )
    else:
        user_content = user_message
    messages.append({"role": "user", "content": user_content})
    return messages


def _create(messages, temperature: float, max_tokens: int, stream: bool):
    kwargs = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
        "extra_body": {
            "chat_template_kwargs": {"enable_thinking": False},
            "top_k": 20,
        },
    }
    try:
        return client().chat.completions.create(**kwargs)
    except Exception as e:
        msg = str(e).lower()
        if "extra_body" in msg or "chat_template" in msg or "unexpected" in msg or "unknown" in msg:
            kwargs.pop("extra_body", None)
            return client().chat.completions.create(**kwargs)
        raise


def chat_stream(
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
    rag_context: str = "",
    temperature: float = 0.6,
    max_tokens: int = 2048,
    preset: str = "general",
) -> Generator[str, None, None]:
    messages = build_messages(user_message, history or [], rag_context, preset)
    stream = _create(messages, temperature, max_tokens, True)
    filt = ThinkFilter()
    try:
        for chunk in stream:
            try:
                delta = chunk.choices[0].delta.content or ""
            except Exception:
                continue
            out = filt.feed(delta)
            if out:
                yield out
    finally:
        try:
            stream.close()
        except Exception:
            pass
        tail = filt.end()
        if tail:
            yield tail


def chat(
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
    rag_context: str = "",
    temperature: float = 0.6,
    max_tokens: int = 2048,
    preset: str = "general",
) -> str:
    messages = build_messages(user_message, history or [], rag_context, preset)
    r = _create(messages, temperature, max_tokens, False)
    text = (r.choices[0].message.content or "").strip()
    return re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.I).strip()
