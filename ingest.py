#!/usr/bin/env python3
"""Index knowledge/ into Chroma + FTS5."""
from __future__ import annotations

import argparse
import sys

from config import INGEST_EMBED_BATCH_SIZE, INGEST_EMBED_DEVICE
from rag import ingest, status


def main() -> int:
    ap = argparse.ArgumentParser(description="Index local knowledge base")
    ap.add_argument("--force", action="store_true", help="Fresh index version")
    ap.add_argument(
        "--device",
        choices=("cuda", "cpu"),
        default=INGEST_EMBED_DEVICE,
        help="Embedding device for this run",
    )
    args = ap.parse_args()

    print("=" * 60)
    print(" Forge Knowledge Ingest")
    print("=" * 60)
    st = status()
    print(f"Embedding model: {st.get('embed_model')}")
    print(f"Backend:         {st.get('embed_backend')}")
    print(f"Ingest device:   {args.device}")
    print(f"Ingest batch:    {INGEST_EMBED_BATCH_SIZE if args.device == 'cuda' else st.get('embed_batch_size')}")
    print(f"Dimension:       {st.get('embedding_dimension')}")
    print(f"Collection:      {st.get('collection')}")
    print(f"Force rebuild:   {args.force}")
    print()

    def progress(name: str, n: int) -> None:
        print(f"  + {name} ({n} chunks)")

    result = ingest(progress_cb=progress, force=args.force, device=args.device)
    if not result.get("ok"):
        print("FAILED:", result.get("error") or "errors present")
        for e in result.get("errors") or []:
            print("  -", e)
        if result.get("discarded_build"):
            print("  kept previous index:", result.get("active_collection"))
        return 1

    print()
    print(f"Files indexed:   {result.get('files', 0)}")
    print(f"Chunks added:    {result.get('chunks', 0)}")
    print(f"Skipped (same):  {result.get('skipped', 0)}")
    print(f"Empty files:     {result.get('empty_files', 0)}")
    print(f"Deleted stale:   {result.get('deleted', 0)}")
    print(f"Device used:     {result.get('device')}")
    print(f"Total in DB:     {result.get('total_indexed', '?')}")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
