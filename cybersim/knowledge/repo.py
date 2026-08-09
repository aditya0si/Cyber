"""KnowledgeRepository seam + in-memory impl (docs/12 §2, §5)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from cybersim.knowledge.embeddings import Embedder, HashEmbedder
from cybersim.knowledge.entries import KnowledgeEntry


@dataclass(frozen=True)
class RetrievalHit:
    entry: KnowledgeEntry
    score: float
    source: str = "hybrid"


class KnowledgeRepository(Protocol):
    """Retrieve + manage knowledge entries (docs/12 §2)."""

    def retrieve(
        self,
        *,
        org_id: str = "global",
        query: str | None = None,
        kind: str | None = None,
        k: int = 8,
        filters: dict[str, Any] | None = None,
        mitre_techniques: Sequence[str] | None = None,
    ) -> list[RetrievalHit]: ...

    def get_entry(self, entry_id: str) -> KnowledgeEntry | None: ...
    def upsert_entry(self, entry: KnowledgeEntry, embedding: list[float] | None = None) -> int: ...
    def bulk_upsert(self, entries: Iterable[KnowledgeEntry]) -> int: ...
    def all_entries(self) -> list[KnowledgeEntry]: ...
    def clear(self) -> None: ...


class InMemoryKnowledgeRepository:
    """Dict + hash-embedding in-memory repo (dev/tests; Phase 9 → pgvector)."""

    def __init__(self, embedder: Embedder | None = None) -> None:
        self._entries: dict[str, KnowledgeEntry] = {}
        self._embeddings: dict[str, list[float]] = {}
        self._embedder = embedder or HashEmbedder()

    # ---- ingestion ----------------------------------------------------------
    def upsert_entry(self, entry: KnowledgeEntry, embedding: list[float] | None = None) -> int:
        if embedding is None:
            embedding = self._embedder.embed(entry.content)
        self._entries[entry.entry_id] = entry
        self._embeddings[entry.entry_id] = embedding
        return 1

    def bulk_upsert(self, entries: Iterable[KnowledgeEntry]) -> int:
        texts = []
        batch = list(entries)
        for e in batch:
            texts.append(e.content)
        embeddings = self._embedder.embed_batch(texts)
        for e, emb in zip(batch, embeddings, strict=False):
            self._entries[e.entry_id] = e
            self._embeddings[e.entry_id] = emb
        return len(batch)

    def all_entries(self) -> list[KnowledgeEntry]:
        return list(self._entries.values())

    def clear(self) -> None:
        self._entries.clear()
        self._embeddings.clear()

    def get_entry(self, entry_id: str) -> KnowledgeEntry | None:
        return self._entries.get(entry_id)

    # ---- retrieval ----------------------------------------------------------
    def retrieve(
        self,
        *,
        org_id: str = "global",
        query: str | None = None,
        kind: str | None = None,
        k: int = 8,
        filters: dict[str, Any] | None = None,
        mitre_techniques: Sequence[str] | None = None,
    ) -> list[RetrievalHit]:
        # Scope: global + own org (docs/15 §3.2).
        pool = [e for e in self._entries.values() if e.org_id in ("global", org_id)]
        if kind:
            pool = [e for e in pool if e.kind == kind]
        if mitre_techniques:
            mt_set = set(mitre_techniques)
            pool = [e for e in pool if set(e.tags).intersection(mt_set) or e.source_id in mt_set]

        if not pool:
            return []

        query_emb = self._embedder.embed(query or "") if query else None
        scored: list[tuple[KnowledgeEntry, float]] = []
        for e in pool:
            emb = self._embeddings.get(e.entry_id)
            score = _hybrid_score(e, query_emb, query or "", emb)
            scored.append((e, score))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [RetrievalHit(entry=e, score=s) for e, s in scored[:k]]


def _hybrid_score(
    entry: KnowledgeEntry,
    query_emb: list[float] | None,
    query: str,
    entry_emb: list[float] | None,
) -> float:
    """Fused vector + keyword score (docs/12 §5.1, alpha=0.6/0.4)."""
    vector_score = 0.0
    if query_emb and entry_emb is not None:
        vector_score = _cosine(query_emb, entry_emb)
    keyword_score = _keyword_score(entry, query)
    return 0.6 * vector_score + 0.4 * keyword_score


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return float(dot / (na * nb))


def _keyword_score(entry: KnowledgeEntry, query: str) -> float:
    import re

    q_tokens = set(re.findall(r"[a-z0-9_]+", query.lower()))
    if not q_tokens:
        return 0.0
    text = f"{entry.title} {entry.summary} {entry.content} {entry.source_id}".lower()
    hits = sum(1 for t in q_tokens if t in text)
    return min(1.0, hits / max(1, len(q_tokens)))
