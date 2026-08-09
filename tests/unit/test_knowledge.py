"""Phase 6 knowledge tests (docs/12 §8): recall@5 >= 0.9 on golden queries."""

from __future__ import annotations

import pytest

from cybersim.knowledge.embeddings import HashEmbedder
from cybersim.knowledge.ingest import ingest_all
from cybersim.knowledge.repo import InMemoryKnowledgeRepository


@pytest.fixture
def knowledge() -> InMemoryKnowledgeRepository:
    repo = InMemoryKnowledgeRepository(embedder=HashEmbedder(dim=128))
    repo.bulk_upsert(ingest_all())
    return repo


#: (query, expected source_id in top-5)
GOLDEN_QUERIES = [
    ("brute force password guessing lockout", "T1110"),
    ("valid accounts credential abuse", "T1078"),
    ("exploit public facing application injection", "T1190"),
    ("supply chain malicious package dependency", "T1195"),
    ("network service discovery port scan", "T1046"),
    ("data exfiltration over command and control", "T1041"),
    ("SQL injection parameterized queries", "A03:2021"),
    ("broken access control idor", "A01:2021"),
    ("authentication failures multi factor", "A07:2021"),
    ("log4j remote code execution", "CVE-2021-44228"),
]


def test_recall_at_5_on_golden_queries(knowledge: InMemoryKnowledgeRepository) -> None:
    hits_total = 0
    for query, expected in GOLDEN_QUERIES:
        hits = knowledge.retrieve(query=query, k=5)
        ids = [h.entry.source_id for h in hits]
        assert expected in ids, f"query {query!r}: expected {expected} in top-5, got {ids}"
        hits_total += 1
    assert hits_total == len(GOLDEN_QUERIES)


def test_retrieve_scopes_org(knowledge: InMemoryKnowledgeRepository) -> None:
    """Global entries are visible to any org; private entries are tenant-only."""
    from cybersim.knowledge.entries import KnowledgeEntry

    knowledge.upsert_entry(
        KnowledgeEntry(
            entry_id="org_private:1",
            org_id="org_demo",
            source_id="PRIV1",
            kind="article",
            title="Private note",
            content="secret internal runbook about brute force protection",
        )
    )
    # Global org sees both.
    hits = knowledge.retrieve(query="brute force", k=10)
    assert any(h.entry.org_id == "global" for h in hits)
    # org_demo sees its own private note.
    hits_demo = knowledge.retrieve(org_id="org_demo", query="runbook brute force", k=10)
    assert any(h.entry.entry_id == "org_private:1" for h in hits_demo)


def test_mitre_technique_filter(knowledge: InMemoryKnowledgeRepository) -> None:
    hits = knowledge.retrieve(query="attack", k=10, mitre_techniques=["T1190"])
    assert hits
    for h in hits:
        assert h.entry.source_id == "T1190"


def test_empty_repo_returns_empty() -> None:
    repo = InMemoryKnowledgeRepository()
    assert repo.retrieve(query="anything") == []


def test_upsert_is_idempotent(knowledge: InMemoryKnowledgeRepository) -> None:
    from cybersim.knowledge.entries import KnowledgeEntry

    entry = KnowledgeEntry(entry_id="x:1", source_id="X1", title="T", content="c")
    assert knowledge.upsert_entry(entry) == 1
    assert knowledge.upsert_entry(entry) == 1
    assert len(knowledge.all_entries()) >= 1
