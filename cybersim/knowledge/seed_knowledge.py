"""Seed knowledge base CLI (`cybersim seed_knowledge`), docs/12 §3.6."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="seed_knowledge")
    parser.add_argument("--embedder", default="hash", choices=["hash", "openai"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    from cybersim.knowledge.embeddings import build_embedder
    from cybersim.knowledge.ingest import ingest_all
    from cybersim.knowledge.repo import InMemoryKnowledgeRepository

    entries = ingest_all()
    print(f"[seed_knowledge] loaded {len(entries)} entries from fixtures")
    if args.dry_run:
        print("[seed_knowledge] dry-run; nothing written")
        return 0

    repo = InMemoryKnowledgeRepository(embedder=build_embedder(provider=args.embedder))
    n = repo.bulk_upsert(entries)
    print(f"[seed_knowledge] embedded {n} entries (dim={repo._embedder.dim})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
