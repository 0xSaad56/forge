#!/usr/bin/env python3
"""CLI: index knowledge/ into Chroma. Use --force to rebuild from scratch."""

import argparse
from rag import ingest, status


def main():
    ap = argparse.ArgumentParser(description="Index local knowledge base")
    ap.add_argument(
        "--force",
        action="store_true",
        help="Rebuild entire index (ignore skip-state)",
    )
    args = ap.parse_args()

    print("=" * 60)
    print(" Forge Knowledge Ingest")
    print("=" * 60)
    st = status()
    print(f"Embedding model: {st['embed_model']}")
    print(f"Collection:      {st.get('collection')}")
    print(f"Knowledge dirs:  {st['knowledge_dirs']}")
    print(f"Force rebuild:   {args.force}")
    print()

    def progress(name, n):
        print(f"  ✓ {name} ({n} chunks)")

    result = ingest(progress_cb=progress, force=args.force)
    if not result.get("ok"):
        print("FAILED:", result.get("error"))
        raise SystemExit(1)

    print()
    print(f"Files indexed:  {result['files']}")
    print(f"Chunks added:   {result['chunks']}")
    print(f"Skipped (same): {result.get('skipped', 0)}")
    print(f"Empty files:    {result.get('empty_files', 0)}")
    print(f"Deleted stale:  {result.get('deleted', 0)}")
    print(f"Total in DB:    {result.get('total_indexed', '?')}")
    if result.get("errors"):
        print("Errors:")
        for e in result["errors"]:
            print("  -", e)
    print("Done.")


if __name__ == "__main__":
    main()
