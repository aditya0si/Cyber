"""Cybersim CLI (docs/19 Phase 2-3, docs/21 Task 3.1, 6.2)."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cybersim")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("db-upgrade", help="apply all Alembic migrations")
    sub.add_parser("seed", help="seed demo user + free org")
    sub.add_parser("seed_knowledge", help="load knowledge fixtures into the repo")
    sub.add_parser("codegen", help="regenerate the OpenAPI lockfile")

    args = parser.parse_args(argv)

    if args.command == "db-upgrade":
        from alembic import command
        from alembic.config import Config

        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
    elif args.command == "seed":
        print(
            "[cybersim] seed: demo user requires Postgres (Phase 9); in-memory store is the MVP default."
        )
    elif args.command == "seed_knowledge":
        from cybersim.knowledge.embeddings import build_embedder
        from cybersim.knowledge.ingest import ingest_all
        from cybersim.knowledge.repo import InMemoryKnowledgeRepository

        entries = ingest_all()
        repo = InMemoryKnowledgeRepository(embedder=build_embedder(provider="hash"))
        n = repo.bulk_upsert(entries)
        print(f"[cybersim] seed_knowledge: embedded {n} entries")
    elif args.command == "codegen":
        import json

        from cybersim.api.main import create_app

        schema = create_app().openapi()
        with open("apps/web/src/lib/api/schema.lock.json", "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=2)
        print(f"[cybersim] codegen: wrote OpenAPI lockfile ({len(schema['paths'])} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
