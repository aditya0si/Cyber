"""Embedder seam (docs/12 §4). Fake (deterministic) for tests; OpenAI for prod."""

from __future__ import annotations

import hashlib
from typing import Any, Protocol


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
    @property
    def dim(self) -> int: ...


class HashEmbedder:
    """Deterministic pseudo-embedding (tests + offline dev).

    Maps each token into a fixed 64-dim vector space so cosine similarity is
    meaningful for keyword overlaps without a real embedding model.
    """

    def __init__(self, dim: int = 64) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for token in _tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:2], "big") % self._dim
            vec[idx] += 1.0
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


def _tokens(text: str) -> list[str]:
    import re

    return re.findall(r"[a-z0-9_]+", text.lower())


class OpenAIEmbedder:
    """text-embedding-3-small via the OpenAI SDK (docs/12 §4)."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model

    @property
    def dim(self) -> int:
        return 1536

    def embed(self, text: str) -> list[float]:
        resp = self._client.embeddings.create(model=self._model, input=text)
        return [float(x) for x in resp.data[0].embedding]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(model=self._model, input=texts)
        return [[float(x) for x in d.embedding] for d in resp.data]


def build_embedder(*, provider: str = "hash", api_key: str = "") -> Any:
    if provider == "hash" or not api_key:
        return HashEmbedder()
    return OpenAIEmbedder(api_key=api_key)

_ST_AVAILABLE = False
try:
    from sentence_transformers import SentenceTransformer
    _ST_AVAILABLE = True
except ImportError:
    pass

class SentenceTransformerEmbedder(Embedder):
    """Uses a local sentence-transformer model for embeddings."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        if not _ST_AVAILABLE:
            raise RuntimeError("sentence-transformers is not installed")
        self._model = SentenceTransformer(model_name)

    @property
    def dim(self) -> int:
        return 384

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        embeddings = self._model.encode(texts, convert_to_numpy=True)
        return [emb.tolist() for emb in embeddings] # type: ignore

    def embed(self, text: str) -> list[float]:
        emb = self._model.encode(text, convert_to_numpy=True)
        return emb.tolist() # type: ignore


class TfidfEmbedder(Embedder):
    """Fallback embedder using TF-IDF and cosine similarity."""

    def __init__(self, corpus_texts: list[str]) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer
        self._vectorizer = TfidfVectorizer()
        if corpus_texts:
            self._vectorizer.fit(corpus_texts)
        else:
            self._vectorizer.fit(["dummy text"])

    @property
    def dim(self) -> int:
        return len(self._vectorizer.vocabulary_) if hasattr(self._vectorizer, "vocabulary_") else 0

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        embeddings = self._vectorizer.transform(texts).toarray()
        return [emb.tolist() for emb in embeddings]

    def embed(self, text: str) -> list[float]:
        emb = self._vectorizer.transform([text]).toarray()[0]
        return emb.tolist()


def get_best_embedder(corpus_texts: list[str]) -> Embedder:
    """Returns SentenceTransformer if available, else TF-IDF fallback."""
    import logging
    if _ST_AVAILABLE:
        try:
            embedder = SentenceTransformerEmbedder("all-MiniLM-L6-v2")
            logging.info("Using SentenceTransformerEmbedder for RAG.")
            return embedder
        except Exception as e:
            logging.warning(f"SentenceTransformer load failed: {e}. Falling back to TF-IDF.")
            
    logging.info("Using TfidfEmbedder for RAG (fallback).")
    return TfidfEmbedder(corpus_texts)

