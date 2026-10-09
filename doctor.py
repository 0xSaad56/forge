#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("POSTHOG_DISABLED", "1")

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))


def main() -> int:
    print("=== Forge doctor ===")
    ok = True
    try:
        import config

        print(f"OK  config  embed={config.EMBED_MODEL}")
        print(f"    max_file={config.MAX_KNOWLEDGE_FILE_BYTES // (1024*1024)} MB")
    except Exception as e:
        print("FAIL config:", e)
        return 1

    try:
        import onnxruntime as ort

        providers = ort.get_available_providers()
        print(f"OK  onnxruntime  {ort.__version__}  providers={providers}")
        if "CUDAExecutionProvider" in providers:
            print("    CUDA ready for ingest")
        else:
            print("    CPU-only embeddings")
    except Exception as e:
        print("WARN onnxruntime:", e)

    try:
        import chromadb  # noqa: F401
        from chromadb.config import Settings

        _ = Settings(anonymized_telemetry=False)
        print("OK  chromadb")
    except Exception as e:
        print("FAIL chromadb:", e)
        ok = False

    try:
        import history

        history.init_db()
        print(f"OK  sqlite  {config.DB_PATH}")
    except Exception as e:
        print("FAIL history:", e)
        ok = False

    for d in (config.KNOWLEDGE, config.CHROMA, config.DATA, config.STATIC):
        print(("OK  " if d.exists() else "FAIL") + f" path {d}")
        if not d.exists():
            ok = False

    cache = config.EMBED_CACHE
    print(("OK  " if cache.exists() else "WARN") + f" embed cache {cache}")

    print("===", "PASS" if ok else "FAIL", "===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
