# 12 — Knowledge Base & RAG

The RAG knowledge base grounds the analyst's claims in **MITRE ATT&CK**, **OWASP**, and a curated **CVE** slice. The analyst must cite at least one knowledge entry for `confidence ≥ 0.75` (`05` §6.2); hallucinated MITRE techniques are dropped (`11` §3.9). This doc defines sources, ingestion, chunking, embeddings, retrieval, citations, and the `KnowledgeRepository` seam (so a future dedicated vector store can replace pgvector behind one package, `04` §2.7).

---

## 1. Sources (v0.1)

| Source | License | Format | Coverage (v0.1) |
|--------|---------|--------|-----------------|
| **MITRE ATT&CK (Enterprise)** | Apache-2.0 / BSD | STIX/JSON | All techniques (Enterprise matrix ~200 techniques) + tactics (~14) |
| **OWASP Top 10 (2021)** | CC-BY-SA-4.0 | Markdown | 10 categories + linked cheatsheet summaries |
| **CVE (curated slice)** | public domain | JSON | ~120 curated CVEs: those whose CWE maps to attack chains we simulate (SQLi, XSS, IDOR, supply chain, auth bypass). Identifies references only; we do not redistribute NVD articles wholesale. |
| **CWE (subset)** | CC-BY-SA | XML | Top ~40 weaknesses; mapped to OWASP categories. |
| **CyberSim Remediation Notes** | ours | Markdown | Authored-by-us, OWASP/MITRE-tagged remediation blurbs for each `ThreatClass`. |

> All ingested under permissive licenses; we **never** bundle paid/proprietary sources. We credit sources on citations and link to canonical URLs (no reproduction of large bodies of text).

### 1.1 What we don't include (v0.1)
- Customer-specific upload (v0.2 feature; partition reserved in `09` §7.1 by `org_id != 'global'`).
- Real-time CVE streaming (we don't want our full-text corpus drifting; nightly refresh is enough for v0.1).

## 2. `KnowledgeRepository` seam (normative interface)

```python
# cybersim/knowledge/repo.py
class KnowledgeRepository(Protocol):
    def retrieve(self, *, org_id: str, query: str | None = None,
                 kind: str | None = None, k: int = 8,
                 filters: dict | None = None,
                 mitre_techniques: list[str] | None = None) -> list[RetrievalHit]: ...
    def get_entry(self, entry_id: str) -> KnowledgeEntry | None: ...
    def upsert_entry(self, entry: KnowledgeEntry, embedding: list[float]) -> None: ...
    def bulk_embed(self, entries: Iterable[KnowledgeEntry]) -> int: ...

@dataclass(frozen=True)
class RetrievalHit:
    entry: KnowledgeEntry
    score: float                # 0..1 normalized
    source: str                 # vector | keyword | hybrid
```

The analyst/view UI call only these. Embeddings, ranking, reranking live behind the impl. **Swap seam:** switching pgvector for Pinecone/Qdrant is bounded to `KnowledgeRepositoryImpl`.

## 3. Ingestion pipeline (`cybersim.knowledge.ingest`)

### 3.1 Steps
1. **Fetch + parse source adapters**:
   - MITRE: download enterprise-attack STIX; iterate `attack-pattern` (techniques), `x-mitre-tactic` (tactics), `x-mitre-matrix`. Build global entries tagged `mitre_*`.
   - OWASP: parse Top-10 markdown + cheatsheets index.
   - CVE: fetch nightly NVD JSON feeds for CVE IDs in our allow-list (~120); store only `{id, description, CWE refs, CVSS, references}` — no large bodies.
   - CWE subset: similar parse.
   - Remediation notes: ours, in-repo markdown.
2. **Extract canonical fields** (`KnowledgeEntry` proto) per source:
```python
@dataclass(frozen=True)
class KnowledgeEntry:
    entry_id: str            # ours, UUIDv7 or "mitre:T1110"
    org_id: str              # "global"
    source: str              # mitre|owasp|cve|cwe|cms_notes
    source_id: str           # T1110 / A03:2021 / CVE-…
    kind: str                # technique|tactic|weakness|vuln|article
    title: str
    summary: str             # ≤ 280 chars clean summary
    content: str             # ≤ ~1200 chars chunk
    payload: dict            # refs, detection_tips, mitigation[], platforms, data_sources
    language: str = "en"
    tags: list[str]          # ['credential_access','brute_force', ...]
```
3. **Chunking**: each source becomes 1+ entries; chunk size ≤1200 chars, sentence-aware. MITRE technique single chunk (its descriptive prose). OWASP per category one entry per "Explanation + Impact" section. CVE one chunk per entry (already small).
4. **Embed**: embeddings via `LLMClient.embed(text)` (`text-embedding-3-small` default; 1536-dim). **Cache** by `entry_id + model + content_hash`; re-embed only when content changes.
5. **Insert**: insert step is **idempotent** on `(source, source_id, content_hash)` — re-running ingestion is safe.
6. **Schedule**: management command `cybersim.knowledge.refresh` run nightly (`03` beat) and on demand from a CI step. On startup, if no rows exist, run ingestion with cached fixture snapshot (no network call in tests).

### 3.2 MITRE ATT&CK mapping table is loaded separately
The MITRE taxonomy table (`cybersim.graph.mitre.Mapping`, `05` §4.2) is **separate** from the knowledge base entries. The Mapping is the deterministic two-way mapping (ThreatClass ↔ MITRE). Knowledge entries are *the documentation* about MITRE techniques. The analyst uses the mapper to seed a query then retrieves knowledge entries for citations.

## 4. Embedding & indexing details

- **Model:** default `text-embedding-3-small` (OpenAI), 1536 dims. Behind `Embedder` interface so we can switch to `bge-large-en-v1.5` (self-host) on enterprise tier or for offline dev.
- **Index:** HNSW on `vector(1536)`, cosine ops:
```sql
CREATE INDEX knowledge_embeddings_vec_idx
  ON knowledge.knowledge_embeddings
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
```
- **Query-time:** we use `ef_search = 40` (tunable; default tuned on a recall suite — top-4 has ≥ 0.9 recall on the curated 500-entry set).

## 5. Retrieval + ranking

### 5.1 Hybrid retrieval per query
1. **Construct query** from `{threat_class (string), relevant MITRE techniques (deterministic), attack_path labels, summary-of-correlation}`. The query text is **shaped** (a brief unless prescribed by node; see `11` §3.6).
2. **Filter scope**: `org_id = 'global' OR org_id = current_org_id` (RLS already enforces); plus optional `kind` (e.g., `technique`).
3. **Vector search** (HNSW, top `k=8`) + **keyword search** (GIN trigram on `content`, top `k=8`).
4. **Rerank** via reciprocal-rank fusion of the two lists, weight `α=0.6` vector / `0.4` keyword (tunable). Optional cross-encoder `bge-reranker-base` is pluggable behind `Reranker` interface; off by default in v0.1 (added complexity not justified until we measure recall gaps).
5. **MITRE **must hit**: if `mitre_techniques` provided, ONLY keep entries whose `source_id ∈` that list of T-IDs. This is **anti-hallucination enforcement**: the validator (`11` §3.9-8) rejects MITRE IDs the LLM didn't actually retrieve; here we make sure the LLM actually retrieves the canonical techniques for the threat class.

### 5.2 Citation discipline
Each cited entry becomes a `knowledge_citation` EvidenceItem (`11` §3.5) with `entry_id`, `weight` from rerank score, and label = `entry.source_id` (e.g., `"MITRE T1110 (Brute Force)"`). The dashboard DetectionCard shows citations as footer references with deep links into `/v1/knowledge/entries/{id}` (`08` §4.7).

## 6. Anti-hallucination §: the "only if you retrieved it" rule

The brief's evidence mandate is operationalized as:
1. LLM T-IDs in a DetectionProposal must be a subset of MITRE T-IDs **retrieved via RAG during `rag_lookup`** for that detection window (tracked in `state.rag_context`).
2. Validator compares; any T-IDs not in retrieved set are stripped and confidence reduced 0.15.
3. The RAG `RagContext` captures retrieved entry IDs; the analyst service persists them as `knowledge_citations` so a frontend can verify citations.

> **Self-question:** Doesn't this cap LLM creativity? **Answer:** Intentionally yes — a SEC tool **must not invent MITRE techniques**. Hard rule. If the retrieved set excludes a real relevant T-ID, that's a RAG retrieval bug to fix, not a license for the LLM to assert.

## 7. Refresh, observability, ops

- Ingestion writes a `knowledge.refresh_log` row per run (`started_at`, `ended_at`, `entries_added`, `entries_updated`, `errors[]`).
- Grafana panel tracks: total entries, last successful refresh, embedding model, mean query latency p95 (target ≤ 80ms hybrid).
- A "knowledge freshness" doc in `/v1/knowledge/_healthz` returns version (e.g., MITRE-ATT&CK v15.1, refreshed-date).
- Dry-run flag (`--dry-run`) prints the planned changes without writing.

## 8. Retrieval quality tests (`20` accrual)

- Curated **golden set**: 20 queries (one per relevant threat_class) with expected top-5 includes the canonical MITRE technique. CI asserts the top-5 contains it (recall@5 ≥ 0.9 across the 20).
- Latency budget: p95 hybrid ≤ 80ms in CI seed-data shape; failure ⇒ investigate index/query.

## 9. Self-questioning & decisions (RAG)

| Decision | Chosen | Rejected | Why |
|----------|--------|----------|-----|
| pgvector single store | Yes | Pinecone | MVP cardinality; cheaper ops; swap seam (`04` §2.7). |
| Embeddings in separate table | Yes | inline in knowledge_entries | Re-embed w/o rewriting big content; multi-model experiments. |
| Hybrid (vector + keyword fusion) | Yes | vector-only | MITRE OWASP candy by ID + semantic similarities; mitigation text benefits from keyword. |
| Force MITRE T-ID filter when providing T-IDs | Yes | top-k open | Anti-hallucination §6. |
| Citation as Evidence kind | Yes | free text | Same evidence discipline as events; uniform validator. |
| Remediation authored by us | Yes | rely on OWASP cheatsheet only | Lets us distill ≤280 chars per threat; OWASP is the *source* citation, ours is the *dashboard* text. |
| Nightly refresh + idempotent upsert | Yes | streaming ingestion | Drift control + cost; `CVE` allowlist is small. |
| Curated CVE slice, ~120 | Yes | full NVD | Domain focus; manageable scope; refreshed cheaply. |
| Reranker pluggable, off default | Yes | always-cross-encoder | v0.1(measured-recall ≥0.9) suffices with fusion; we keep the seam for v0.2. |

---

End of `12-rag-knowledge-base.md`. Next: `13-frontend-architecture.md`.
